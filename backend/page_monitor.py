"""
DOR Page Monitor: detect content changes on WA Department of Revenue pages.

Crawls 65+ specific DOR pages, converts to markdown, hashes content,
compares against previous crawl state in Supabase, and auto-ingests changes.

Inspired by WATaxDesk/automation/monitor_dor.py but uses Supabase for state
and Claude Haiku for AI filtering instead of local JSON + GPT-4o-mini.
"""

import difflib
import hashlib
import logging
import os
import re
import time
from datetime import datetime, timezone
from typing import Callable, Optional
from urllib.parse import urlparse

import anthropic
import html2text
import httpx
from bs4 import BeautifulSoup

from config import settings
from db import get_supabase
from ingest import chunk_text, get_embedding, ingest_pdf
from scraper import scrape_page, categorize_url, _build_citation

logger = logging.getLogger(__name__)

USER_AGENT = "RAG-Platform-Monitor/1.0 (+https://github.com/rag-platform)"

# ---------------------------------------------------------------------------
# Monitored URLs — ported from WATaxDesk/automation/monitor_dor.py
# ---------------------------------------------------------------------------

MONITORED_URLS = [
    # --- Main pages ---
    "https://dor.wa.gov",
    "https://dor.wa.gov/taxes-rates",
    "https://dor.wa.gov/forms-publications",
    "https://dor.wa.gov/about/news-releases",

    # --- Tax types ---
    "https://dor.wa.gov/taxes-rates/business-occupation-tax",
    "https://dor.wa.gov/taxes-rates/use-tax",
    "https://dor.wa.gov/taxes-rates/property-tax",
    "https://dor.wa.gov/taxes-rates/other-taxes",

    # --- Tax rates ---
    "https://dor.wa.gov/taxes-rates/sales-use-tax-rates",
    "https://dor.wa.gov/taxes-rates/retail-sales-tax/marketplace-fairness-leveling-playing-field",

    # --- B&O tax specifics ---
    "https://dor.wa.gov/taxes-rates/business-occupation-tax/business-occupation-tax-classifications",

    # --- ESSB 5814 — Services newly subject to retail sales tax ---
    "https://dor.wa.gov/taxes-rates/retail-sales-tax/services-newly-subject-retail-sales-tax",
    "https://dor.wa.gov/taxes-rates/retail-sales-tax/services-newly-subject-retail-sales-tax/why-am-i-being-charged-sales-tax-now",
    "https://dor.wa.gov/taxes-rates/retail-sales-tax/services-newly-subject-retail-sales-tax/frequently-asked-questions-about-essb-5814",
    "https://dor.wa.gov/taxes-rates/retail-sales-tax/services-newly-subject-retail-sales-tax/essb-5814-interim-guidance-and-upcoming-rule-making",
    "https://dor.wa.gov/taxes-rates/retail-sales-tax/services-newly-subject-retail-sales-tax/advertising-services",
    "https://dor.wa.gov/taxes-rates/retail-sales-tax/services-newly-subject-retail-sales-tax/information-technology-services-0",
    "https://dor.wa.gov/taxes-rates/retail-sales-tax/services-newly-subject-retail-sales-tax/custom-website-development",
    "https://dor.wa.gov/taxes-rates/retail-sales-tax/services-newly-subject-retail-sales-tax/live-presentations",
    "https://dor.wa.gov/taxes-rates/retail-sales-tax/services-newly-subject-retail-sales-tax/investigation-security-and-armored-car-services",
    "https://dor.wa.gov/taxes-rates/retail-sales-tax/services-newly-subject-retail-sales-tax/temporary-staffing-services",
    "https://dor.wa.gov/taxes-rates/retail-sales-tax/services-newly-subject-retail-sales-tax/sales-custom-software-and-customization-prewritten-software",

    # --- ESSB 5814 — Interim Guidance Statements ---
    "https://dor.wa.gov/laws-rules/interim_guidance_statements/interim-guidance-statement-regarding-changes-made-essb-5814-information-technology-services",
    "https://dor.wa.gov/laws-rules/interim-guidance-statement-regarding-contracts-existing-prior-october-1-2025-and-changes-made-essb",
    "https://dor.wa.gov/laws-rules/interim_guidance_statements/interim-guidance-statement-regarding-changes-made-essb-5814-advertising-services",
    "https://dor.wa.gov/laws-rules/interim_guidance_statements/interim-guidance-statement-regarding-changes-made-essb-5814-custom-software",
    "https://dor.wa.gov/laws-rules/interim_guidance_statements/interim-guidance-statement-regarding-changes-made-essb-5814-live-presentations",
    "https://dor.wa.gov/laws-rules/interim_guidance_statements/interim-guidance-statement-regarding-changes-made-essb-5814-temporary-staffing-services",

    # --- ESSB 5814 — Tools ---
    "https://dor.wa.gov/taxes-rates/retail-sales-tax/sales-and-use-tax-tools",

    # --- Industry guides ---
    "https://dor.wa.gov/education/industry-guides",
    "https://dor.wa.gov/education/industry-guides/construction",
    "https://dor.wa.gov/education/industry-guides/real-estate-industry",
    "https://dor.wa.gov/education/industry-guides/nonprofit-organizations",

    # --- Publications & forms ---
    "https://dor.wa.gov/forms-publications/publications-subject",
    "https://dor.wa.gov/get-form-or-publication",

    # --- Laws & rules ---
    "https://dor.wa.gov/laws-rules",

    # --- Tax credits & incentives ---
    "https://dor.wa.gov/taxes-rates/tax-incentives",
    "https://dor.wa.gov/taxes-rates/tax-incentives/credits",

    # --- REET ---
    "https://dor.wa.gov/taxes-rates/other-taxes/real-estate-excise-tax",

    # --- WTDs (for detecting new determination PDFs) ---
    "https://dor.wa.gov/washington-tax-decisions",
]

# Boilerplate patterns to strip from crawled content (from WATaxDesk)
BOILERPLATE_PATTERNS = [
    r"Skip to main content.*?(?=\n\n|\n#)",
    r"\[English\]\(/\).*?\[Language Help\]\(/language-services\)",
    r"\*\s*\[English\].*?\[Ti[e\u1ebf]ng Vi[e\u1ec7]t\].*?(?=\n)",
    r"Sales tax now applies to some services.*?(?=\n\n)",
    r"\[Home\]\(/\s*\"Home\"\s*\).*?(?=\n)",
    r"Search Form - Mindbreeze.*?(?=\n)",
    r"\* \[Laws & rules\].*?\* \[Log in\].*?(?=\n)",
    r"^\s*\d+\.\s*\[Home\].*?(?=\n)",
]


# ---------------------------------------------------------------------------
# Page Monitor
# ---------------------------------------------------------------------------

class PageMonitor:
    def __init__(self, project_id: str | None = None):
        self.project_id = project_id
        self.sb = get_supabase()
        self.converter = html2text.HTML2Text()
        self.converter.ignore_links = False
        self.converter.ignore_images = True

    # ----- Crawl a single page -----

    def crawl_page(self, url: str) -> dict:
        """Fetch a URL, extract main content as markdown, compute MD5 hash."""
        try:
            resp = httpx.get(
                url,
                headers={"User-Agent": USER_AGENT},
                follow_redirects=True,
                timeout=30.0,
            )
            resp.raise_for_status()
        except Exception as e:
            return {"url": url, "error": str(e), "markdown": "", "hash": "", "title": ""}

        # Extract Last-Modified header if available
        last_modified = resp.headers.get("Last-Modified", "")

        soup = BeautifulSoup(resp.content, "html.parser")

        # Also check for <time> tags in the content (e.g. news releases)
        if not last_modified:
            time_tag = soup.find("time", attrs={"datetime": True})
            if time_tag:
                last_modified = time_tag.get("datetime", "")

        # Extract title
        title = ""
        if soup.title:
            title = soup.title.get_text(strip=True)
            title = re.sub(
                r"\s*[\|—]\s*(Washington Department of Revenue).*$", "", title
            ).strip()

        # Remove boilerplate elements
        for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
            tag.decompose()

        # Remove skip links
        for skip in soup.find_all(string=lambda t: t and "Skip to main content" in t):
            if skip.parent:
                skip.parent.decompose()

        # Extract main content
        main = soup.find("main") or soup.find("article") or soup.find(id="main-content")
        html_content = str(main) if main else (str(soup.body) if soup.body else str(soup))

        # Convert to markdown
        markdown = self.converter.handle(html_content)

        # Strip boilerplate patterns
        for pattern in BOILERPLATE_PATTERNS:
            markdown = re.sub(pattern, "", markdown, flags=re.IGNORECASE | re.DOTALL)

        # Clean whitespace
        markdown = re.sub(r"\n{3,}", "\n\n", markdown).strip()

        content_hash = hashlib.md5(markdown.encode()).hexdigest()

        return {
            "url": url,
            "title": title,
            "markdown": markdown,
            "hash": content_hash,
            "last_modified": last_modified,
        }

    # ----- Change detection against Supabase state -----

    def _get_previous_state(self) -> dict[str, dict]:
        """Load previous page state from Supabase. Returns {url: row}."""
        q = self.sb.table("monitor_page_state").select("*")
        if self.project_id:
            q = q.eq("project_id", self.project_id)
        r = q.execute()
        return {row["url"]: row for row in (r.data or [])}

    def _upsert_page_state(self, url: str, title: str, content_hash: str, category: str):
        """Insert or update a page's state in Supabase."""
        now = datetime.now(timezone.utc).isoformat()
        row = {
            "url": url,
            "title": title,
            "content_hash": content_hash,
            "category": category,
            "last_checked_at": now,
            "last_changed_at": now,
            "status": "active",
            "error_message": None,
        }
        if self.project_id:
            row["project_id"] = self.project_id

        try:
            self.sb.table("monitor_page_state").upsert(
                row, on_conflict="url,project_id"
            ).execute()
        except Exception as e:
            logger.warning(f"Upsert page state failed for {url}: {e}")

    def _update_page_checked(self, url: str, content_hash: str | None = None, error: str | None = None):
        """Update last_checked_at (and optionally hash/error) for a page."""
        now = datetime.now(timezone.utc).isoformat()
        update = {"last_checked_at": now}
        if content_hash:
            update["content_hash"] = content_hash
            update["last_changed_at"] = now
            update["status"] = "active"
            update["error_message"] = None
        if error:
            update["status"] = "error"
            update["error_message"] = error

        q = self.sb.table("monitor_page_state").update(update).eq("url", url)
        if self.project_id:
            q = q.eq("project_id", self.project_id)
        try:
            q.execute()
        except Exception as e:
            logger.warning(f"Update page state failed for {url}: {e}")

    def _log_change(self, url: str, change_type: str, title: str, summary: str,
                    is_substantive: bool, additions: int = 0, deletions: int = 0,
                    auto_ingested: bool = False, page_state_id: str | None = None,
                    last_modified: str | None = None):
        """Insert a change log entry."""
        row = {
            "url": url,
            "change_type": change_type,
            "title": title,
            "summary": summary,
            "is_substantive": is_substantive,
            "diff_additions": additions,
            "diff_deletions": deletions,
            "auto_ingested": auto_ingested,
        }
        if last_modified:
            row["last_modified"] = last_modified
        if page_state_id:
            row["page_state_id"] = page_state_id
        if self.project_id:
            row["project_id"] = self.project_id
        try:
            self.sb.table("monitor_change_log").insert(row).execute()
        except Exception as e:
            logger.warning(f"Log change failed for {url}: {e}")

    # ----- Diff helpers -----

    @staticmethod
    def _compute_diff(old_md: str, new_md: str) -> tuple[int, int, list[str], list[str]]:
        """Compare two markdown strings. Returns (additions, deletions, added_lines, removed_lines)."""
        old_lines = old_md.splitlines()
        new_lines = new_md.splitlines()
        diff = list(difflib.Differ().compare(old_lines, new_lines))
        added = [line[2:].strip() for line in diff if line.startswith("+ ") and line[2:].strip()]
        removed = [line[2:].strip() for line in diff if line.startswith("- ") and line[2:].strip()]
        return len(added), len(removed), added[:10], removed[:10]

    # ----- AI substantive change filter -----

    def is_substantive_change(self, title: str, url: str, summary: str, additions: int, deletions: int) -> bool:
        """Use Claude Haiku to decide if a page change is substantive."""
        # Quick filters
        if additions == 0 and deletions <= 2:
            return False
        if additions <= 2 and deletions <= 2:
            return False

        if not settings.ANTHROPIC_API_KEY:
            return True  # Default to include if no API key

        try:
            client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
            prompt = f"""Evaluate if this Washington Department of Revenue webpage change contains SUBSTANTIVE NEW CONTENT that tax professionals should know about.

Page: {title}
URL: {url}
Change Summary: {summary}
Additions: {additions}, Deletions: {deletions}

Answer with ONLY "YES" or "NO" followed by a brief reason.

Answer YES if:
- New tax rates, rules, or policy information was added
- New guidance, exemptions, or requirements were published
- Important dates or deadlines were updated
- New forms or procedures were announced

Answer NO if:
- Old news items simply rotated off a listing page
- Only formatting, typos, or navigation elements changed
- The change is just removing outdated content with nothing new
- It's a listing page where items are tracked separately"""

            resp = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=60,
                temperature=0,
                messages=[{"role": "user", "content": prompt}],
            )
            answer = resp.content[0].text.strip().upper()
            is_sub = answer.startswith("YES")
            logger.info(f"AI filter for '{title}': {'INCLUDE' if is_sub else 'SKIP'} — {answer[:50]}")
            return is_sub
        except Exception as e:
            logger.warning(f"AI filter error: {e}, defaulting to include")
            return True

    # ----- Specialized scrapers -----

    def scrape_news_releases(self) -> list[dict]:
        """Scrape news releases with publication dates from dor.wa.gov."""
        url = "https://dor.wa.gov/about/news-releases"
        try:
            resp = httpx.get(url, headers={"User-Agent": USER_AGENT}, follow_redirects=True, timeout=30)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.content, "html.parser")
            main = soup.find("main") or soup

            items = []
            seen = set()
            for link in main.find_all("a", href=True):
                href = link.get("href", "")
                if "/about/news-releases/" not in href or href == "/about/news-releases":
                    continue
                parent = link.find_parent(["p", "div", "li"])
                if not parent:
                    continue
                date_match = re.search(r"(\d{2}/\d{2}/\d{4})", parent.get_text(strip=True))
                if not date_match:
                    continue
                try:
                    pub_date = datetime.strptime(date_match.group(1), "%m/%d/%Y").strftime("%Y-%m-%d")
                except ValueError:
                    continue

                full_url = href if href.startswith("http") else f"https://dor.wa.gov{href}"
                if full_url in seen:
                    continue
                seen.add(full_url)

                items.append({
                    "title": link.get_text(strip=True),
                    "url": full_url,
                    "published_date": pub_date,
                    "source": "News Release",
                })

            logger.info(f"Found {len(items)} news releases")
            return items
        except Exception as e:
            logger.warning(f"Error scraping news releases: {e}")
            return []

    def scrape_special_notices(self) -> list[dict]:
        """Scrape special notices with dates from the table on dor.wa.gov."""
        url = "https://dor.wa.gov/forms-publications/publications-subject/special-notices"
        try:
            resp = httpx.get(url, headers={"User-Agent": USER_AGENT}, follow_redirects=True, timeout=30)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.content, "html.parser")

            items = []
            seen = set()
            table = soup.find("table")
            if not table:
                return items

            for row in table.find_all("tr")[1:]:  # skip header
                cells = row.find_all("td")
                if len(cells) < 2:
                    continue
                link_tag = cells[0].find("a", href=True)
                date_text = cells[1].get_text(strip=True)
                if not link_tag or not date_text:
                    continue
                date_match = re.search(r"(\d{1,2}/\d{1,2}/\d{4})", date_text)
                if not date_match:
                    continue
                try:
                    pub_date = datetime.strptime(date_match.group(1), "%m/%d/%Y").strftime("%Y-%m-%d")
                except ValueError:
                    continue

                href = link_tag["href"]
                full_url = href if href.startswith("http") else f"https://dor.wa.gov{href}"
                if full_url in seen:
                    continue
                seen.add(full_url)

                subject = cells[3].get_text(strip=True) if len(cells) > 3 else ""
                title = link_tag.get_text(strip=True)

                items.append({
                    "title": title,
                    "url": full_url,
                    "published_date": pub_date,
                    "subject": subject,
                    "source": "Special Notice",
                })

            logger.info(f"Found {len(items)} special notices")
            return items
        except Exception as e:
            logger.warning(f"Error scraping special notices: {e}")
            return []

    def check_new_wtds(self) -> list[dict]:
        """Check dor.wa.gov/washington-tax-decisions for new WTD PDFs not yet in our DB."""
        url = "https://dor.wa.gov/washington-tax-decisions"
        try:
            resp = httpx.get(url, headers={"User-Agent": USER_AGENT}, follow_redirects=True, timeout=60)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            # Collect all WTD PDF links from the page
            all_pdfs: dict[str, str] = {}  # filename -> url
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if not href.lower().endswith(".pdf") or "wtd" not in href.lower():
                    continue
                if not href.startswith("http"):
                    href = f"https://dor.wa.gov{href}"
                base_name = os.path.basename(urlparse(href).path).split("?")[0]
                all_pdfs[base_name] = href

            if not all_pdfs:
                return []

            # Batch-check which filenames already exist in DB
            existing_files: set[str] = set()
            filenames = list(all_pdfs.keys())
            batch_size = 50
            for i in range(0, len(filenames), batch_size):
                batch = filenames[i:i + batch_size]
                q = self.sb.table("knowledge_documents").select("source_file").in_("source_file", batch)
                if self.project_id:
                    q = q.eq("project_id", self.project_id)
                r = q.execute()
                for row in (r.data or []):
                    existing_files.add(row["source_file"])

            new_pdfs = [
                {"url": all_pdfs[fn], "filename": fn}
                for fn in filenames
                if fn not in existing_files
            ]

            logger.info(f"Found {len(new_pdfs)} new WTD PDFs (checked {len(all_pdfs)} total)")
            return new_pdfs
        except Exception as e:
            logger.warning(f"Error checking new WTDs: {e}")
            return []

    # ----- Auto-ingestion -----

    def _reingest_page(self, url: str) -> bool:
        """Re-scrape and re-ingest a page, replacing old chunks."""
        try:
            # Delete existing document + chunks for this URL
            existing = (
                self.sb.table("knowledge_documents")
                .select("id")
                .eq("source_url", url)
            )
            if self.project_id:
                existing = existing.eq("project_id", self.project_id)
            existing_docs = existing.execute()

            for doc in (existing_docs.data or []):
                self.sb.table("tax_law_chunks").delete().eq("document_id", doc["id"]).execute()
                self.sb.table("knowledge_documents").delete().eq("id", doc["id"]).execute()

            # Re-scrape and ingest
            with httpx.Client(
                headers={"User-Agent": USER_AGENT},
                timeout=30.0,
                follow_redirects=True,
            ) as client:
                page = scrape_page(url, client)

            if page.get("error") or not page.get("text") or len(page.get("text", "")) < 100:
                return False

            text = page["text"]
            chunks = chunk_text(text)
            if not chunks:
                return False

            title = page.get("title") or url
            category = categorize_url(url)
            citation = _build_citation(url, title, category)

            doc_row = {
                "title": title,
                "document_type": "tax_law",
                "source_type": "web_scrape",
                "source_file": url,
                "source_url": url,
                "citation": citation,
                "law_category": category,
                "total_chunks": len(chunks),
                "processing_status": "processing",
            }
            if self.project_id:
                doc_row["project_id"] = self.project_id

            doc_result = self.sb.table("knowledge_documents").insert(doc_row).execute()
            doc_id = doc_result.data[0]["id"]

            inserted = 0
            for j, chunk_content in enumerate(chunks):
                embedding = get_embedding(chunk_content)
                if not embedding:
                    continue
                chunk_row = {
                    "document_id": doc_id,
                    "chunk_text": chunk_content,
                    "chunk_number": j,
                    "citation": citation,
                    "law_category": category,
                    "source_url": url,
                    "embedding": embedding,
                }
                if self.project_id:
                    chunk_row["project_id"] = self.project_id
                self.sb.table("tax_law_chunks").insert(chunk_row).execute()
                inserted += 1

            self.sb.table("knowledge_documents").update({
                "processing_status": "complete",
                "total_chunks": inserted,
            }).eq("id", doc_id).execute()

            logger.info(f"Re-ingested {url}: {inserted} chunks")
            return True
        except Exception as e:
            logger.warning(f"Re-ingest failed for {url}: {e}")
            return False

    def _ingest_wtd_pdf(self, url: str, filename: str) -> bool:
        """Download and ingest a new WTD PDF."""
        try:
            resp = httpx.get(url, follow_redirects=True, timeout=60)
            resp.raise_for_status()

            vol_match = re.match(r"(\d+)\s*WTD\s*(\d+)", filename, re.IGNORECASE)
            citation = f"{vol_match.group(1)} WTD {vol_match.group(2)}" if vol_match else filename.replace(".pdf", "")

            result = ingest_pdf(
                resp.content,
                filename,
                category="Tax Determination (WTD)",
                citation=citation,
                project_id=self.project_id,
            )
            return result.get("status") == "success"
        except Exception as e:
            logger.warning(f"WTD ingest failed for {filename}: {e}")
            return False

    # ----- Main orchestrator -----

    def run_full_crawl(
        self,
        auto_ingest: bool = True,
        skip_wtd_ingest: bool = False,
        on_progress: Callable[[dict], None] | None = None,
        stop_flag: Callable[[], bool] | None = None,
    ) -> dict:
        """
        Full monitoring pipeline:
        1. Crawl all monitored pages
        2. Detect changes via MD5 hash comparison
        3. AI-filter substantive changes
        4. Auto-ingest changed pages
        5. Check for new WTD PDFs
        6. Scrape news releases & special notices
        """
        started_at = time.time()
        stats = {
            "status": "running",
            "total_pages": len(MONITORED_URLS),
            "pages_crawled": 0,
            "pages_new": 0,
            "pages_modified": 0,
            "pages_unchanged": 0,
            "pages_error": 0,
            "substantive_changes": 0,
            "auto_ingested": 0,
            "new_wtds_found": 0,
            "new_wtds_ingested": 0,
            "news_releases": 0,
            "special_notices": 0,
            "current_url": "",
            "elapsed_seconds": 0,
            "changes": [],
            "errors": [],
        }

        previous_state = self._get_previous_state()

        # Phase 1: Crawl all pages and detect changes
        for i, url in enumerate(MONITORED_URLS):
            if stop_flag and stop_flag():
                stats["status"] = "stopped"
                break

            stats["current_url"] = url
            stats["pages_crawled"] = i
            stats["elapsed_seconds"] = time.time() - started_at
            _report(on_progress, stats)

            result = self.crawl_page(url)

            if result.get("error"):
                stats["pages_error"] += 1
                stats["errors"].append({"url": url, "error": result["error"]})
                self._update_page_checked(url, error=result["error"])
                time.sleep(0.3)
                continue

            new_hash = result["hash"]
            title = result["title"]
            last_modified = result.get("last_modified", "")
            category = categorize_url(url)
            prev = previous_state.get(url)

            if not prev:
                # First time seeing this page
                stats["pages_new"] += 1
                self._upsert_page_state(url, title, new_hash, category)
                summary = f"New page added to monitor: {title}"
                self._log_change(url, "NEW", title, summary, is_substantive=True, last_modified=last_modified)
                stats["changes"].append({
                    "url": url, "type": "NEW", "title": title, "summary": summary,
                    "last_modified": last_modified,
                })

                # Auto-ingest new pages
                if auto_ingest:
                    ingested = self._reingest_page(url)
                    if ingested:
                        stats["auto_ingested"] += 1

            elif new_hash != prev.get("content_hash"):
                # Content changed
                stats["pages_modified"] += 1

                # Compute diff for summary
                old_md = ""  # We don't store full markdown, just hash
                additions, deletions = 0, 0
                summary = f"Content changed on {title} (hash mismatch)"

                # Check if substantive
                is_sub = self.is_substantive_change(title, url, summary, additions=5, deletions=5)
                if is_sub:
                    stats["substantive_changes"] += 1

                self._update_page_checked(url, content_hash=new_hash)
                self._log_change(
                    url, "MODIFIED", title, summary,
                    is_substantive=is_sub,
                    additions=additions, deletions=deletions,
                    page_state_id=prev.get("id"),
                    last_modified=last_modified,
                )
                stats["changes"].append({
                    "url": url, "type": "MODIFIED", "title": title,
                    "summary": summary, "is_substantive": is_sub,
                    "last_modified": last_modified,
                })

                # Auto-ingest substantive changes
                if auto_ingest and is_sub:
                    ingested = self._reingest_page(url)
                    if ingested:
                        stats["auto_ingested"] += 1

            else:
                # No change
                stats["pages_unchanged"] += 1
                now = datetime.now(timezone.utc).isoformat()
                q = self.sb.table("monitor_page_state").update({
                    "last_checked_at": now,
                }).eq("url", url)
                if self.project_id:
                    q = q.eq("project_id", self.project_id)
                try:
                    q.execute()
                except Exception:
                    pass

            time.sleep(0.3)  # Rate limit

        stats["pages_crawled"] = len(MONITORED_URLS)

        # Phase 2: Check for new WTD PDFs
        if not (stop_flag and stop_flag()):
            stats["current_url"] = "Checking for new WTDs..."
            _report(on_progress, stats)

            new_wtds = self.check_new_wtds()
            stats["new_wtds_found"] = len(new_wtds)

            if auto_ingest and not skip_wtd_ingest:
                for wtd in new_wtds:
                    if stop_flag and stop_flag():
                        break
                    stats["current_url"] = f"Ingesting WTD: {wtd['filename']}"
                    _report(on_progress, stats)

                    if self._ingest_wtd_pdf(wtd["url"], wtd["filename"]):
                        stats["new_wtds_ingested"] += 1
                    time.sleep(0.2)

        # Phase 3: Scrape news releases & special notices (metadata only, no ingestion)
        if not (stop_flag and stop_flag()):
            stats["current_url"] = "Scraping news releases..."
            _report(on_progress, stats)
            news = self.scrape_news_releases()
            stats["news_releases"] = len(news)

            stats["current_url"] = "Scraping special notices..."
            _report(on_progress, stats)
            notices = self.scrape_special_notices()
            stats["special_notices"] = len(notices)

        # Done
        if stats["status"] == "running":
            stats["status"] = "complete"
        stats["elapsed_seconds"] = time.time() - started_at
        stats["current_url"] = ""
        _report(on_progress, stats)

        return stats


def _report(callback: Callable | None, stats: dict):
    if callback:
        callback(stats.copy())

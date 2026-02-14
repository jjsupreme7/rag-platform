"""Website scraper: discover URLs via sitemap, scrape HTML/PDF, chunk, embed, store."""

import hashlib
import io
import logging
import re
import time
from typing import Callable
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree

import httpx
from bs4 import BeautifulSoup

from config import settings
from db import get_supabase
from ingest import chunk_text, extract_pdf_text, get_embedding

logger = logging.getLogger(__name__)

USER_AGENT = "RAG-Platform-Scraper/1.0 (+https://github.com/rag-platform)"

# Sitemap XML namespace
SITEMAP_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}

# Domain-specific include patterns for URL filtering
DOMAIN_INCLUDE_PATTERNS = {
    "dor.wa.gov": [
        "/laws-rules/",
        "/taxes-rates/",
        "/education/",
        "/forms-publications/",
        ".pdf",
    ],
    "app.leg.wa.gov": [
        "/rcw/",
        "/wac/",
        "/RCW/",
        "/WAC/",
    ],
    "taxpedia.dor.wa.gov": [
        "/wtd/",
        "/eta/",
        "/WTD/",
        "/ETA/",
        ".pdf",
    ],
}

# Default patterns (dor.wa.gov, backward compatible)
DEFAULT_INCLUDE_PATTERNS = DOMAIN_INCLUDE_PATTERNS["dor.wa.gov"]

DEFAULT_EXCLUDE_PATTERNS = [
    "/admin/",
    "/user/",
    "/node/add/",
    "/contact/",
    "/about/",
    "/careers/",
    "/news/",
    "/search/",
    "/filter/",
    "?page=",
    "/comment/",
]


# ---------------------------------------------------------------------------
# URL Discovery
# ---------------------------------------------------------------------------

def discover_urls(base_url: str, client: httpx.Client) -> list[str]:
    """Parse sitemap.xml to discover all page URLs. Falls back to homepage links."""
    base_url = base_url.rstrip("/")
    sitemap_url = f"{base_url}/sitemap.xml"

    urls: set[str] = set()

    try:
        resp = client.get(sitemap_url, follow_redirects=True)
        resp.raise_for_status()
        root = ElementTree.fromstring(resp.content)

        # Check if this is a sitemap index (contains <sitemap> entries)
        sitemaps = root.findall("sm:sitemap/sm:loc", SITEMAP_NS)
        if sitemaps:
            logger.info(f"Found sitemap index with {len(sitemaps)} sub-sitemaps")
            for sitemap_loc in sitemaps:
                sub_url = sitemap_loc.text.strip()
                try:
                    sub_resp = client.get(sub_url, follow_redirects=True)
                    sub_resp.raise_for_status()
                    sub_root = ElementTree.fromstring(sub_resp.content)
                    for loc in sub_root.findall("sm:url/sm:loc", SITEMAP_NS):
                        if loc.text:
                            urls.add(loc.text.strip())
                    time.sleep(0.2)  # Be polite between sitemap fetches
                except Exception as e:
                    logger.warning(f"Failed to fetch sub-sitemap {sub_url}: {e}")
        else:
            # Direct sitemap with <url> entries
            for loc in root.findall("sm:url/sm:loc", SITEMAP_NS):
                if loc.text:
                    urls.add(loc.text.strip())
    except Exception as e:
        logger.warning(f"Sitemap fetch failed ({e}), falling back to homepage links")
        urls = _discover_from_homepage(base_url, client)

    logger.info(f"Discovered {len(urls)} URLs from sitemap")
    return sorted(urls)


def _discover_from_homepage(base_url: str, client: httpx.Client) -> set[str]:
    """Fallback: extract links from the homepage."""
    urls: set[str] = set()
    try:
        resp = client.get(base_url, follow_redirects=True)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
        domain = urlparse(base_url).netloc
        for a in soup.find_all("a", href=True):
            href = urljoin(base_url, a["href"])
            if urlparse(href).netloc == domain:
                urls.add(href.split("#")[0])
    except Exception as e:
        logger.error(f"Homepage fallback failed: {e}")
    return urls


# ---------------------------------------------------------------------------
# URL Filtering
# ---------------------------------------------------------------------------

def filter_urls(
    urls: list[str],
    include_patterns: list[str] | None = None,
    exclude_patterns: list[str] | None = None,
) -> list[str]:
    """Filter URLs to keep only relevant content pages."""
    include = include_patterns or DEFAULT_INCLUDE_PATTERNS
    exclude = exclude_patterns or DEFAULT_EXCLUDE_PATTERNS

    filtered = []
    for url in urls:
        path = urlparse(url).path.lower()
        full = url.lower()

        # Must match at least one include pattern
        if not any(p in path or p in full for p in include):
            continue

        # Must not match any exclude pattern
        if any(p in path or p in full for p in exclude):
            continue

        filtered.append(url)

    return filtered


def categorize_url(url: str) -> str:
    """Map a URL to a law_category based on its domain and path pattern."""
    parsed = urlparse(url)
    netloc = parsed.netloc.lower()
    path = parsed.path.lower()
    full = url.lower()

    # Legislature domain (app.leg.wa.gov) — RCW statutes and WAC rules
    if "app.leg.wa.gov" in netloc:
        if "/rcw/" in path:
            return "RCW Statute"
        if "/wac/" in path:
            return "WAC Rule"
        return "Legislative Source"

    # Taxpedia domain (taxpedia.dor.wa.gov) — WTDs and ETAs
    if "taxpedia.dor.wa.gov" in netloc:
        if "wtd" in path or "tax-decision" in path or "determination" in path:
            return "Tax Determination (WTD)"
        if "eta" in path or "excise-tax-advisor" in path:
            return "Excise Tax Advisory (ETA)"
        return "DOR Taxpedia"

    # DOR domain (dor.wa.gov) — existing patterns
    if "/tax-research-index/wac-" in path or "/wac-" in path:
        return "WAC Rule"
    if "excise-tax-advisor" in path or "/eta" in path:
        return "Excise Tax Advisory (ETA)"
    if re.search(r"eta.*\.pdf", full) or re.search(r"\d{4}\.pdf", full):
        if "taxpedia" in full or "eta" in full:
            return "Excise Tax Advisory (ETA)"
    if "wtd" in path or "tax-decision" in path:
        return "Tax Determination (WTD)"
    if "/forms-publications/" in path or "/publications" in path:
        return "Tax Publication"
    if "/industry-guides/" in path or "/education/" in path:
        return "Industry Guide"
    if "/taxes-rates/" in path:
        return "Tax Rate Info"
    if "/laws-rules/" in path:
        return "Tax Law/Rule"
    return "DOR Guidance"


# ---------------------------------------------------------------------------
# Page Scraping
# ---------------------------------------------------------------------------

def scrape_page(url: str, client: httpx.Client) -> dict:
    """
    Fetch and extract text from a single URL.
    Returns {url, title, text, content_type, word_count} or {url, error}.
    """
    try:
        resp = client.get(url, follow_redirects=True, timeout=30.0)
        resp.raise_for_status()
    except Exception as e:
        return {"url": url, "error": str(e), "text": "", "title": "", "word_count": 0}

    content_type = resp.headers.get("content-type", "").lower()

    # PDF
    if url.lower().endswith(".pdf") or "application/pdf" in content_type:
        return _extract_pdf(url, resp.content)

    # HTML
    if "text/html" in content_type:
        return _extract_html(url, resp.text)

    return {"url": url, "error": f"Unsupported content type: {content_type}", "text": "", "title": "", "word_count": 0}


def _extract_html(url: str, html: str) -> dict:
    """Extract main content text from an HTML page."""
    soup = BeautifulSoup(html, "lxml")

    # Get title
    title = ""
    if soup.title and soup.title.string:
        title = soup.title.string.strip()
        # Remove common suffixes
        title = re.sub(r"\s*[\|—]\s*(Washington Department of Revenue|Washington State Legislature).*$", "", title).strip()

    # Remove non-content elements
    for tag in soup.find_all(["nav", "header", "footer", "script", "style", "noscript", "aside"]):
        tag.decompose()

    # Try to find main content area
    main = (
        soup.find("main")
        or soup.find("article")
        or soup.find("div", {"role": "main"})
        or soup.find("div", class_=re.compile(r"content|main|body", re.I))
    )

    # Fallback for legislature ASP.NET pages (app.leg.wa.gov)
    if not main and "leg.wa.gov" in url:
        main = (
            soup.find("div", id="contentWrapper")
            or soup.find("div", class_="legContent")
            or soup.find("div", id=re.compile(r"ContentPlaceHolder", re.I))
        )

    if main:
        text = main.get_text(separator="\n", strip=True)
    else:
        text = soup.get_text(separator="\n", strip=True)

    # Clean up whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = text.strip()

    words = len(text.split())
    return {"url": url, "title": title, "text": text, "content_type": "html", "word_count": words}


def _extract_pdf(url: str, content: bytes) -> dict:
    """Extract text from a PDF document."""
    try:
        text = extract_pdf_text(content)
        title = urlparse(url).path.split("/")[-1].replace(".pdf", "").replace("_", " ")
        words = len(text.split()) if text else 0
        return {"url": url, "title": title, "text": text, "content_type": "pdf", "word_count": words}
    except Exception as e:
        return {"url": url, "error": f"PDF extraction failed: {e}", "text": "", "title": "", "word_count": 0}


# ---------------------------------------------------------------------------
# Main Orchestrator
# ---------------------------------------------------------------------------

def scrape_website(
    base_url: str,
    project_id: str | None = None,
    include_patterns: list[str] | None = None,
    on_progress: Callable[[dict], None] | None = None,
    stop_flag: Callable[[], bool] | None = None,
) -> dict:
    """
    Full scrape pipeline: discover URLs -> filter -> scrape -> chunk -> embed -> store.

    Args:
        base_url: Website to scrape (e.g. "https://dor.wa.gov")
        project_id: Optional project to scope documents under
        include_patterns: URL patterns to include (defaults to tax content)
        on_progress: Callback with progress dict after each page
        stop_flag: Callable returning True to stop early

    Returns: Summary dict with stats.
    """
    stats = {
        "status": "running",
        "base_url": base_url,
        "total_discovered": 0,
        "total_filtered": 0,
        "scraped": 0,
        "failed": 0,
        "skipped_short": 0,
        "documents_created": 0,
        "chunks_created": 0,
        "current_url": "",
        "started_at": time.time(),
        "errors": [],
    }

    sb = get_supabase()

    # Get existing source_urls to skip duplicates
    existing_urls = _get_existing_source_urls(sb, project_id)

    with httpx.Client(
        headers={"User-Agent": USER_AGENT},
        timeout=30.0,
        follow_redirects=True,
    ) as client:
        # 1. Discover URLs
        stats["current_url"] = "Discovering URLs from sitemap..."
        _report(on_progress, stats)

        all_urls = discover_urls(base_url, client)
        stats["total_discovered"] = len(all_urls)

        # 2. Filter
        filtered = filter_urls(all_urls, include_patterns=include_patterns)
        stats["total_filtered"] = len(filtered)

        logger.info(f"Discovered {len(all_urls)} URLs, filtered to {len(filtered)}")
        _report(on_progress, stats)

        # 3. Scrape each URL
        max_pages = settings.SCRAPE_MAX_PAGES
        rate_limit = settings.SCRAPE_RATE_LIMIT

        for i, url in enumerate(filtered[:max_pages]):
            # Check stop flag
            if stop_flag and stop_flag():
                stats["status"] = "stopped"
                break

            # Skip already-ingested URLs
            if url in existing_urls:
                stats["scraped"] += 1
                continue

            stats["current_url"] = url
            _report(on_progress, stats)

            # Scrape page
            page = scrape_page(url, client)

            if page.get("error"):
                stats["failed"] += 1
                stats["errors"].append({"url": url, "error": page["error"]})
                logger.warning(f"Failed: {url} - {page['error']}")
                time.sleep(rate_limit)
                continue

            text = page.get("text", "")
            if not text or len(text) < 100:
                stats["skipped_short"] += 1
                stats["scraped"] += 1
                time.sleep(rate_limit)
                continue

            # 4. Chunk text
            chunks = chunk_text(text)
            if not chunks:
                stats["skipped_short"] += 1
                stats["scraped"] += 1
                time.sleep(rate_limit)
                continue

            # 5. Create document record
            title = page.get("title") or url
            category = categorize_url(url)
            citation = _build_citation(url, title, category)

            try:
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
                if project_id:
                    doc_row["project_id"] = project_id

                doc_result = sb.table("knowledge_documents").insert(doc_row).execute()
                doc_id = doc_result.data[0]["id"]
            except Exception as e:
                stats["failed"] += 1
                stats["errors"].append({"url": url, "error": f"DB insert: {e}"})
                logger.warning(f"Doc insert failed for {url}: {e}")
                time.sleep(rate_limit)
                continue

            # 6. Embed and store chunks
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
                if project_id:
                    chunk_row["project_id"] = project_id

                try:
                    sb.table("tax_law_chunks").insert(chunk_row).execute()
                    inserted += 1
                except Exception as e:
                    logger.warning(f"Chunk insert error for {url} chunk {j}: {e}")

            # Update document status
            try:
                sb.table("knowledge_documents").update({
                    "processing_status": "complete",
                    "total_chunks": inserted,
                }).eq("id", doc_id).execute()
            except Exception:
                pass

            stats["scraped"] += 1
            stats["documents_created"] += 1
            stats["chunks_created"] += inserted
            existing_urls.add(url)

            _report(on_progress, stats)
            time.sleep(rate_limit)

    if stats["status"] == "running":
        stats["status"] = "complete"

    stats["elapsed_seconds"] = time.time() - stats["started_at"]
    stats["current_url"] = ""
    _report(on_progress, stats)

    return stats


# ---------------------------------------------------------------------------
# Discovery-only endpoint (for preview before scraping)
# ---------------------------------------------------------------------------

def discover_and_filter(
    base_url: str,
    include_patterns: list[str] | None = None,
) -> dict:
    """Discover and filter URLs without scraping. For preview/counting."""
    with httpx.Client(
        headers={"User-Agent": USER_AGENT},
        timeout=30.0,
        follow_redirects=True,
    ) as client:
        all_urls = discover_urls(base_url, client)
        filtered = filter_urls(all_urls, include_patterns=include_patterns)

        # Categorize for breakdown
        categories: dict[str, int] = {}
        for url in filtered:
            cat = categorize_url(url)
            categories[cat] = categories.get(cat, 0) + 1

        return {
            "base_url": base_url,
            "total_discovered": len(all_urls),
            "total_filtered": len(filtered),
            "categories": categories,
            "sample_urls": filtered[:20],
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_existing_source_urls(sb, project_id: str | None) -> set[str]:
    """Get source_urls already in the database to skip duplicates."""
    existing: set[str] = set()
    try:
        q = sb.table("knowledge_documents").select("source_url")
        if project_id:
            q = q.eq("project_id", project_id)
        # Paginate
        offset = 0
        while True:
            r = q.range(offset, offset + 999).execute()
            rows = r.data or []
            for row in rows:
                url = row.get("source_url")
                if url:
                    existing.add(url)
            if len(rows) < 1000:
                break
            offset += 1000
    except Exception:
        pass  # Column might not exist yet
    return existing


def _build_citation(url: str, title: str, category: str) -> str:
    """Build a human-readable citation from URL and title."""
    from urllib.parse import parse_qs
    parsed = urlparse(url)
    path = parsed.path
    netloc = parsed.netloc.lower()

    # Legislature URLs use ?cite= or ?Cite= query parameter
    qs = parse_qs(parsed.query)
    cite_val = (qs.get("cite") or qs.get("Cite", [None]))[0]
    if cite_val and "app.leg.wa.gov" in netloc:
        if "/rcw/" in path.lower():
            return f"RCW {cite_val}"
        if "/wac/" in path.lower():
            return f"WAC {cite_val}"

    # WAC citations from DOR site
    wac_match = re.search(r"wac-(\d+)", path, re.I)
    if wac_match:
        return f"WAC 458-20-{wac_match.group(1)}"

    # ETA citations
    eta_match = re.search(r"(\d{4})\.pdf", path)
    if eta_match and ("eta" in url.lower() or "taxpedia" in url.lower()):
        return f"ETA {eta_match.group(1)}"

    # WTD citations
    wtd_match = re.search(r"(\d+)wtd(\d+)", path, re.I)
    if wtd_match:
        return f"WTD {wtd_match.group(1)}-{wtd_match.group(2)}"

    # Use title or URL path
    if title and len(title) < 100:
        return title

    return path.split("/")[-1] or url


def _report(callback: Callable | None, stats: dict):
    """Call progress callback if provided."""
    if callback:
        callback(stats.copy())

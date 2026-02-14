"""Website monitor: detect new/updated content on WA tax authority sites via Perplexity Sonar API."""

import logging
import time
from typing import Callable
from urllib.parse import urlparse

import httpx

from config import settings
from db import get_supabase
from scraper import scrape_page, categorize_url, _build_citation, _get_existing_source_urls
from ingest import chunk_text, get_embedding

logger = logging.getLogger(__name__)

PERPLEXITY_BASE_URL = "https://api.perplexity.ai"

# All authoritative WA tax domains
WA_TAX_DOMAINS = ["dor.wa.gov", "app.leg.wa.gov", "taxpedia.dor.wa.gov"]

# Predefined search queries covering ALL WA tax content areas from research doc
MONITOR_QUERIES = [
    # --- Statutes (RCW) - Most authoritative ---
    {
        "id": "rcw_82_04",
        "label": "RCW 82.04 B&O Tax",
        "query": "List all sections of RCW 82.04 (Business & Occupation tax) on app.leg.wa.gov.",
    },
    {
        "id": "rcw_82_08",
        "label": "RCW 82.08 Retail Sales Tax",
        "query": "List all sections of RCW 82.08 (Retail Sales Tax) on app.leg.wa.gov.",
    },
    {
        "id": "rcw_82_12",
        "label": "RCW 82.12 Use Tax",
        "query": "List all sections of RCW 82.12 (Use Tax) on app.leg.wa.gov.",
    },
    {
        "id": "rcw_82_other",
        "label": "RCW 82 Other Chapters",
        "query": "List all RCW Title 82 chapters on app.leg.wa.gov beyond 82.04, 82.08, 82.12, including 82.29A leasehold excise tax and 82.14 local taxes.",
    },
    # --- Regulations (WAC) ---
    {
        "id": "wac_458_20",
        "label": "WAC 458-20 Excise Tax Rules",
        "query": "List all WAC 458-20 excise tax rule sections on app.leg.wa.gov. These are the most used tax regulations.",
    },
    {
        "id": "wac_458_other",
        "label": "WAC 458 Other (61A, etc.)",
        "query": "What other WAC 458 rules exist on app.leg.wa.gov beyond 458-20? Include WAC 458-61A real estate excise tax and any others.",
    },
    # --- Determinations (WTD) ---
    {
        "id": "tax_determinations",
        "label": "Tax Determinations (WTD)",
        "query": "What Washington tax determinations (WTDs) are published on dor.wa.gov/washington-tax-decisions and taxpedia.dor.wa.gov? List recent determinations.",
    },
    # --- Excise Tax Advisories (ETA) ---
    {
        "id": "excise_tax_advisories",
        "label": "Excise Tax Advisories (ETA)",
        "query": "What excise tax advisories (ETAs) are available on dor.wa.gov/laws-rules/excise-tax-advisories-eta and taxpedia.dor.wa.gov?",
    },
    # --- Interim Guidance Statements ---
    {
        "id": "interim_guidance",
        "label": "Interim Guidance Statements",
        "query": "What interim guidance statements are published on dor.wa.gov/laws-rules/interim_guidance_statements? List all current interim guidance.",
    },
    # --- Special Notices ---
    {
        "id": "special_notices",
        "label": "Special Notices",
        "query": "What special notices are published on dor.wa.gov/forms-publications/publications-subject/special-notices? List all current special notices.",
    },
    # --- Industry Guides ---
    {
        "id": "industry_guides",
        "label": "Industry Tax Guides",
        "query": "What industry-specific tax guides are on dor.wa.gov/education/industry-guides? Include the apportionment guide and all industry guides.",
    },
    # --- Tax Topics ---
    {
        "id": "tax_topics",
        "label": "Tax Topics",
        "query": "What tax topics are published on dor.wa.gov/forms-publications/publications-subject/tax-topics? Include digital products, nexus, and all topic pages.",
    },
    # --- Forms & Publications ---
    {
        "id": "publications",
        "label": "Forms & Publications",
        "query": "What tax publications, forms, and PDF guides are available on dor.wa.gov/forms-publications?",
    },
    # --- Tax Rates ---
    {
        "id": "tax_rates",
        "label": "Tax Rates & Changes",
        "query": "What are the current tax rate pages and rate change updates on dor.wa.gov?",
    },
    # --- Laws & Rules landing ---
    {
        "id": "laws_rules",
        "label": "Laws & Rules Overview",
        "query": "What content is available on dor.wa.gov/laws-rules? List all subpages including the tax research index.",
    },
    # --- Recent Updates (catch-all) ---
    {
        "id": "recent_updates",
        "label": "Recent Updates (All Sources)",
        "query": "What new tax guidance, rules, statutes, determinations, or publications has Washington State recently published on dor.wa.gov, app.leg.wa.gov, or taxpedia.dor.wa.gov?",
    },
]


def get_monitor_queries() -> list[dict]:
    """Return the list of predefined search queries for the UI."""
    return [{"id": q["id"], "label": q["label"]} for q in MONITOR_QUERIES]


# ---------------------------------------------------------------------------
# Perplexity API calls
# ---------------------------------------------------------------------------

def perplexity_search(query: str, recency_filter: str = "month") -> list[dict]:
    """
    Search WA tax authority sites via Perplexity sonar chat completions.
    Uses the citations array to discover URLs from dor.wa.gov,
    app.leg.wa.gov (RCW/WAC), and taxpedia.dor.wa.gov (WTDs/ETAs).
    Returns list of {url, title, snippet}.
    """
    headers = {
        "Authorization": f"Bearer {settings.PERPLEXITY_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "sonar",
        "messages": [
            {
                "role": "system",
                "content": (
                    "List all relevant URLs from Washington State tax authority websites. "
                    "Cite pages from dor.wa.gov, app.leg.wa.gov (RCW statutes, WAC rules), "
                    "and taxpedia.dor.wa.gov (WTDs, ETAs)."
                ),
            },
            {"role": "user", "content": query},
        ],
        "web_search_options": {
            "search_domain_filter": WA_TAX_DOMAINS,
            "search_recency_filter": recency_filter,
        },
    }

    with httpx.Client(timeout=30.0) as client:
        resp = client.post(
            f"{PERPLEXITY_BASE_URL}/chat/completions",
            json=payload,
            headers=headers,
        )
        resp.raise_for_status()
        data = resp.json()

    # Extract URLs from citations array
    citations = data.get("citations", [])
    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")

    results = []
    seen = set()
    for citation_url in citations:
        # Post-filter: only keep WA tax authority URLs
        netloc = urlparse(citation_url).netloc
        if not any(domain in netloc for domain in WA_TAX_DOMAINS):
            continue
        normalized = citation_url.rstrip("/")
        if normalized in seen:
            continue
        seen.add(normalized)
        # Extract title from URL path or query params
        parsed = urlparse(citation_url)
        title = _title_from_url(parsed)
        results.append({
            "url": citation_url,
            "title": title,
            "snippet": content[:200] if content else "",
        })
    return results


def _title_from_url(parsed) -> str:
    """Extract a human-readable title from a parsed URL."""
    from urllib.parse import parse_qs
    # Legislature URLs use ?cite= query param
    qs = parse_qs(parsed.query)
    if "cite" in qs or "Cite" in qs:
        cite_val = (qs.get("cite") or qs.get("Cite", [""]))[0]
        path_lower = parsed.path.lower()
        if "/rcw/" in path_lower:
            return f"RCW {cite_val}"
        if "/wac/" in path_lower:
            return f"WAC {cite_val}"
        return cite_val
    # Standard path-based title
    path = parsed.path
    title = path.split("/")[-1].replace("-", " ").replace("_", " ").replace(".pdf", "").strip()
    return title.title() if title else ""


def generate_change_summary(new_urls: list[dict]) -> str | None:
    """Use Perplexity sonar to summarize new content found."""
    if not new_urls:
        return None

    url_list = "\n".join(
        f"- {u['title'] or u['url']} ({u['url']})" for u in new_urls[:20]
    )

    headers = {
        "Authorization": f"Bearer {settings.PERPLEXITY_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "sonar",
        "messages": [
            {
                "role": "user",
                "content": (
                    "Summarize what is new or updated on Washington State tax authority "
                    "websites (dor.wa.gov, app.leg.wa.gov, taxpedia.dor.wa.gov) based on "
                    "these recently found pages. Focus on statute changes, new WAC rules, "
                    "tax determinations, guidance updates, and regulatory changes. "
                    "Be concise.\n\n"
                    f"Pages found:\n{url_list}"
                ),
            }
        ],
        "web_search_options": {
            "search_domain_filter": WA_TAX_DOMAINS,
        },
    }

    try:
        with httpx.Client(timeout=60.0) as client:
            resp = client.post(
                f"{PERPLEXITY_BASE_URL}/chat/completions",
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        logger.warning(f"Sonar summary failed: {e}")
        return None


def perplexity_chat_search(query: str) -> list[dict]:
    """
    Search WA tax authority sites for a user's chat question via Perplexity sonar.
    Covers dor.wa.gov, app.leg.wa.gov (RCW/WAC), and taxpedia.dor.wa.gov (WTDs).
    Returns list of {citation, chunk_text, source_url, similarity} in the same
    format as local RAG chunks so they can be merged directly.
    """
    if not settings.PERPLEXITY_API_KEY:
        return []

    headers = {
        "Authorization": f"Bearer {settings.PERPLEXITY_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "sonar",
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a Washington State tax law research assistant. "
                    "Answer using official WA state sources including dor.wa.gov, "
                    "app.leg.wa.gov (RCW statutes, WAC rules), and taxpedia.dor.wa.gov (WTDs). "
                    "Cite specific pages and triangulate across source types when possible."
                ),
            },
            {"role": "user", "content": query},
        ],
        "web_search_options": {
            "search_domain_filter": WA_TAX_DOMAINS,
        },
    }

    try:
        with httpx.Client(timeout=20.0) as client:
            resp = client.post(
                f"{PERPLEXITY_BASE_URL}/chat/completions",
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()

        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        citations = data.get("citations", [])

        # Build chunks from Perplexity response, one per citation
        results = []
        seen = set()
        for citation_url in citations:
            netloc = urlparse(citation_url).netloc
            if not any(domain in netloc for domain in WA_TAX_DOMAINS):
                continue
            normalized = citation_url.rstrip("/")
            if normalized in seen:
                continue
            seen.add(normalized)

            # Build a citation label from the URL
            parsed = urlparse(citation_url)
            label = _title_from_url(parsed)
            if not label:
                label = parsed.netloc

            results.append({
                "citation": label if len(label) < 80 else label[:80],
                "chunk_text": content[:1500],
                "source_url": citation_url,
                "similarity": 0.0,  # No similarity score from Perplexity
                "source": "perplexity",
            })

        return results
    except Exception as e:
        logger.warning(f"Perplexity chat search failed: {e}")
        return []


# ---------------------------------------------------------------------------
# Main Orchestrator
# ---------------------------------------------------------------------------

def run_monitor_check(
    project_id: str | None = None,
    recency_filter: str = "month",
    auto_ingest: bool = False,
    generate_summary: bool = True,
    on_progress: Callable[[dict], None] | None = None,
    stop_flag: Callable[[], bool] | None = None,
) -> dict:
    """
    Full monitoring pipeline:
    1. Run predefined Perplexity searches
    2. Deduplicate found URLs
    3. Compare against existing source_url in DB
    4. Optionally scrape and ingest new URLs
    5. Optionally generate change summary via sonar
    """
    started_at = time.time()
    stats = {
        "status": "running",
        "total_queries": len(MONITOR_QUERIES),
        "queries_completed": 0,
        "urls_found": 0,
        "new_urls": 0,
        "existing_urls": 0,
        "ingested": 0,
        "ingest_failed": 0,
        "current_query": "",
        "elapsed_seconds": 0,
        "new_url_list": [],
        "summary": None,
        "errors": [],
    }

    sb = get_supabase()
    existing = _get_existing_source_urls(sb, project_id)

    # Phase 1: Run all search queries
    all_found: dict[str, dict] = {}  # url -> {title, snippet, date}

    for i, q in enumerate(MONITOR_QUERIES):
        if stop_flag and stop_flag():
            stats["status"] = "stopped"
            break

        stats["current_query"] = q["label"]
        stats["queries_completed"] = i
        _report(on_progress, stats)

        try:
            results = perplexity_search(q["query"], recency_filter)
            for r in results:
                url = r["url"].rstrip("/")
                if url not in all_found:
                    all_found[url] = r
        except Exception as e:
            logger.warning(f"Search failed for '{q['label']}': {e}")
            stats["errors"].append({"query": q["label"], "error": str(e)})

        time.sleep(0.5)  # Rate limit between queries

    stats["urls_found"] = len(all_found)
    stats["queries_completed"] = len(MONITOR_QUERIES)

    # Phase 2: Compare against existing URLs
    new_urls = []
    for url, info in all_found.items():
        if url in existing:
            stats["existing_urls"] += 1
        else:
            category = categorize_url(url)
            new_urls.append({
                "url": url,
                "title": info.get("title", ""),
                "snippet": info.get("snippet", ""),
                "date": info.get("date"),
                "category": category,
                "status": "new",
            })

    stats["new_urls"] = len(new_urls)
    stats["new_url_list"] = new_urls
    _report(on_progress, stats)

    # Phase 3: Auto-ingest new URLs (if enabled)
    if auto_ingest and new_urls:
        stats["current_query"] = "Ingesting new content..."
        _report(on_progress, stats)

        with httpx.Client(
            headers={"User-Agent": "RAG-Platform-Monitor/1.0"},
            timeout=30.0,
            follow_redirects=True,
        ) as client:
            for entry in new_urls:
                if stop_flag and stop_flag():
                    stats["status"] = "stopped"
                    break

                url = entry["url"]
                stats["current_query"] = f"Ingesting: {url}"
                _report(on_progress, stats)

                page = scrape_page(url, client)
                if page.get("error") or not page.get("text") or len(page.get("text", "")) < 100:
                    entry["status"] = "failed"
                    stats["ingest_failed"] += 1
                    time.sleep(settings.SCRAPE_RATE_LIMIT)
                    continue

                text = page["text"]
                chunks = chunk_text(text)
                if not chunks:
                    entry["status"] = "skipped"
                    time.sleep(settings.SCRAPE_RATE_LIMIT)
                    continue

                title = page.get("title") or url
                category = entry["category"]
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
                    entry["status"] = "db_error"
                    stats["ingest_failed"] += 1
                    stats["errors"].append({"url": url, "error": str(e)})
                    time.sleep(settings.SCRAPE_RATE_LIMIT)
                    continue

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
                    except Exception:
                        pass

                try:
                    sb.table("knowledge_documents").update({
                        "processing_status": "complete",
                        "total_chunks": inserted,
                    }).eq("id", doc_id).execute()
                except Exception:
                    pass

                entry["status"] = "ingested"
                entry["chunks_created"] = inserted
                stats["ingested"] += 1
                _report(on_progress, stats)
                time.sleep(settings.SCRAPE_RATE_LIMIT)

    # Phase 4: Generate summary (if enabled)
    if generate_summary and new_urls:
        stats["current_query"] = "Generating summary..."
        _report(on_progress, stats)
        stats["summary"] = generate_change_summary(new_urls)

    if stats["status"] == "running":
        stats["status"] = "complete"

    stats["elapsed_seconds"] = time.time() - started_at
    stats["current_query"] = ""
    _report(on_progress, stats)

    return stats


def _report(callback: Callable | None, stats: dict):
    """Call progress callback if provided."""
    if callback:
        callback(stats.copy())

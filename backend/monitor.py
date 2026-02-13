"""Website monitor: detect new/updated content on dor.wa.gov via Perplexity Sonar API."""

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

# Predefined search queries covering major DOR content areas
MONITOR_QUERIES = [
    {
        "id": "wac_rules",
        "label": "WAC Tax Rules",
        "query": "What are the current WAC 458 tax rules published on dor.wa.gov? List all pages.",
    },
    {
        "id": "excise_tax_advisories",
        "label": "Excise Tax Advisories",
        "query": "What excise tax advisories (ETAs) are available on dor.wa.gov and taxpedia.dor.wa.gov?",
    },
    {
        "id": "tax_determinations",
        "label": "Tax Determinations (WTD)",
        "query": "What Washington tax determinations (WTDs) are published on dor.wa.gov?",
    },
    {
        "id": "tax_rates",
        "label": "Tax Rates & Changes",
        "query": "What are the current tax rate pages and rate change updates on dor.wa.gov?",
    },
    {
        "id": "publications",
        "label": "Forms & Publications",
        "query": "What tax publications and guides are available as PDFs on dor.wa.gov?",
    },
    {
        "id": "industry_guides",
        "label": "Industry Guides",
        "query": "What industry-specific tax guides are on dor.wa.gov? List all education and industry guide pages.",
    },
    {
        "id": "bno_sales_tax",
        "label": "B&O and Sales Tax",
        "query": "What B&O tax and sales tax exemption guidance pages exist on dor.wa.gov?",
    },
    {
        "id": "recent_updates",
        "label": "Recent DOR Updates",
        "query": "What new tax guidance, rules, or publications has Washington DOR recently published on dor.wa.gov?",
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
    Search dor.wa.gov via Perplexity sonar chat completions.
    Uses the citations array to discover URLs. The /search endpoint
    returns too few results, but sonar's citations reliably surface
    real dor.wa.gov pages.
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
                    "List all relevant URLs from dor.wa.gov for this query. "
                    "Cite as many specific dor.wa.gov pages as possible."
                ),
            },
            {"role": "user", "content": query},
        ],
        "web_search_options": {
            "search_domain_filter": ["dor.wa.gov"],
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
        # Post-filter: only keep dor.wa.gov URLs
        if "dor.wa.gov" not in urlparse(citation_url).netloc:
            continue
        normalized = citation_url.rstrip("/")
        if normalized in seen:
            continue
        seen.add(normalized)
        # Extract title from URL path
        path = urlparse(citation_url).path
        title = path.split("/")[-1].replace("-", " ").replace("_", " ").replace(".pdf", "").strip()
        results.append({
            "url": citation_url,
            "title": title.title() if title else "",
            "snippet": content[:200] if content else "",
        })
    return results


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
                    "Summarize what is new or updated on the Washington State "
                    "Department of Revenue website based on these recently found pages. "
                    "Focus on tax law changes, new guidance, and regulatory updates. "
                    "Be concise.\n\n"
                    f"Pages found:\n{url_list}"
                ),
            }
        ],
        "web_search_options": {
            "search_domain_filter": ["dor.wa.gov"],
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
    Search dor.wa.gov for a user's chat question via Perplexity sonar.
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
                    "Answer the question using only official WA state sources. "
                    "Cite specific dor.wa.gov pages."
                ),
            },
            {"role": "user", "content": query},
        ],
        "web_search_options": {
            "search_domain_filter": ["dor.wa.gov"],
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
            if "dor.wa.gov" not in urlparse(citation_url).netloc:
                continue
            normalized = citation_url.rstrip("/")
            if normalized in seen:
                continue
            seen.add(normalized)

            # Build a citation label from the URL
            path = urlparse(citation_url).path
            label = path.split("/")[-1].replace("-", " ").replace("_", " ").replace(".pdf", "").strip()
            if not label:
                label = urlparse(citation_url).netloc

            results.append({
                "citation": label.title() if len(label) < 80 else label[:80],
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

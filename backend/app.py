import json
import logging
import threading
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI, Query, Request, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
from openai import OpenAI
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from config import settings
from db import get_supabase
from model_router import get_anthropic, route_model
from retrieval import retrieve
from ingest import ingest_pdf
from scraper import scrape_website, discover_and_filter
from monitor import run_monitor_check, get_monitor_queries, perplexity_chat_search
from page_monitor import PageMonitor, MONITORED_URLS
from notifications import send_change_notification


# ---------------------------------------------------------------------------
# Scheduler for automated daily crawls
# ---------------------------------------------------------------------------

scheduler = BackgroundScheduler(daemon=True)


def _scheduled_crawl():
    """Run by APScheduler on the configured daily schedule."""
    logger.info("Scheduled daily crawl starting...")
    sb = get_supabase()

    # Read schedule config to get project_id and auto_ingest
    try:
        cfg = sb.table("monitor_schedule_config").select("*").limit(1).execute()
        config = cfg.data[0] if cfg.data else {}
        logger.info(f"Schedule config loaded, id={config.get('id')}")
    except Exception as e:
        logger.error(f"Failed to load schedule config: {e}")
        config = {}

    project_id = config.get("project_id")
    auto_ingest = config.get("auto_ingest", True)

    # Run the crawl — don't auto-ingest; changes go to pending review
    config_id = config.get("id")
    status = "unknown"
    total_changes = 0
    try:
        monitor = PageMonitor(project_id=project_id)
        result = monitor.run_full_crawl(auto_ingest=False, skip_wtd_ingest=True)
        status = result.get("status", "unknown")
        total_changes = result.get("pages_new", 0) + result.get("pages_modified", 0)
        logger.info(f"Scheduled crawl complete: {status}, {total_changes} changes")

        # Send email notification if there are changes
        changes = result.get("changes", [])
        if changes:
            # Fetch the change log entries with IDs for the email
            try:
                recent = sb.table("monitor_change_log").select("id, url, change_type, title, summary").order(
                    "detected_at", desc=True
                ).limit(len(changes)).execute()
                email_changes = recent.data or changes
            except Exception:
                email_changes = changes
            send_change_notification(email_changes, result)
    except Exception as e:
        status = f"error: {str(e)[:200]}"
        logger.error(f"Scheduled crawl failed: {e}")
    finally:
        # Always update last_run info, even if crawl errored
        logger.info(f"Scheduled crawl finally block: config_id={config_id}, status={status}, changes={total_changes}")
        if config_id:
            try:
                sb2 = get_supabase()  # Fresh client in case the old one timed out
                sb2.table("monitor_schedule_config").update({
                    "last_run_at": datetime.now(timezone.utc).isoformat(),
                    "last_run_status": status,
                    "last_run_changes": total_changes,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }).eq("id", config_id).execute()
                logger.info("Schedule config updated successfully")
            except Exception as ue:
                logger.error(f"Failed to update schedule config: {ue}")
        else:
            logger.warning("No config_id found, skipping status update")


def _ensure_schedule_table():
    """Create the schedule config table and default row if they don't exist."""
    try:
        sb = get_supabase()
        # Try reading — if the table exists, this works
        sb.table("monitor_schedule_config").select("id").limit(1).execute()
    except Exception:
        # Table doesn't exist — create it via raw SQL
        try:
            sb = get_supabase()
            sb.rpc("exec_sql", {"query": """
                CREATE TABLE IF NOT EXISTS monitor_schedule_config (
                    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
                    enabled BOOLEAN DEFAULT false,
                    hour_utc INT DEFAULT 14,
                    minute_utc INT DEFAULT 0,
                    runs_per_day INT DEFAULT 2,
                    auto_ingest BOOLEAN DEFAULT true,
                    project_id UUID REFERENCES projects(id),
                    last_run_at TIMESTAMPTZ,
                    last_run_status TEXT,
                    last_run_changes INT DEFAULT 0,
                    created_at TIMESTAMPTZ DEFAULT now(),
                    updated_at TIMESTAMPTZ DEFAULT now()
                )
            """}).execute()
        except Exception as e:
            logger.warning(f"Could not auto-create schedule table: {e}")
            logger.info("Please run migrations/004_monitor_schedule.sql in Supabase SQL editor")
            return

    # Ensure default row exists
    try:
        sb = get_supabase()
        existing = sb.table("monitor_schedule_config").select("id").limit(1).execute()
        if not existing.data:
            sb.table("monitor_schedule_config").insert({
                "enabled": False,
                "hour_utc": 14,
                "minute_utc": 0,
                "runs_per_day": 2,
                "auto_ingest": True,
            }).execute()
            logger.info("Created default schedule config row")
    except Exception as e:
        logger.warning(f"Could not seed schedule config: {e}")


def _sync_scheduler_from_db():
    """Read schedule config from Supabase and sync the APScheduler job."""
    try:
        sb = get_supabase()
        cfg = sb.table("monitor_schedule_config").select("*").limit(1).execute()
        if not cfg.data:
            return
        config = cfg.data[0]

        # Remove existing scheduled job if any
        if scheduler.get_job("daily_crawl"):
            scheduler.remove_job("daily_crawl")

        if config.get("enabled"):
            hour = config.get("hour_utc", 14)
            minute = config.get("minute_utc", 0)
            runs_per_day = config.get("runs_per_day", 2)

            if runs_per_day >= 2:
                second_hour = (hour + 12) % 24
                cron_hours = f"{hour},{second_hour}"
            else:
                cron_hours = str(hour)

            scheduler.add_job(
                _scheduled_crawl,
                CronTrigger(hour=cron_hours, minute=minute),
                id="daily_crawl",
                replace_existing=True,
            )
            logger.info(f"Scheduled crawl at hours [{cron_hours}]:{minute:02d} UTC ({runs_per_day}x/day)")
        else:
            logger.info("Daily crawl schedule is disabled")
    except Exception as e:
        logger.warning(f"Failed to sync scheduler from DB: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start the scheduler on app startup, stop on shutdown."""
    scheduler.start()
    _ensure_schedule_table()
    _sync_scheduler_from_db()
    yield
    scheduler.shutdown(wait=False)

_openai: OpenAI | None = None


def get_openai() -> OpenAI:
    global _openai
    if _openai is None:
        _openai = OpenAI(api_key=settings.OPENAI_API_KEY)
    return _openai


limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"])
app = FastAPI(title="RAG Platform API", version="0.3.0", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Sources"],
)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    return {
        "status": "ok",
        "supabase_configured": bool(settings.SUPABASE_URL),
        "openai_configured": bool(settings.OPENAI_API_KEY),
        "anthropic_configured": bool(settings.ANTHROPIC_API_KEY),
        "perplexity_configured": bool(settings.PERPLEXITY_API_KEY),
        "scraper_available": True,
    }


# ---------------------------------------------------------------------------
# Projects CRUD
# ---------------------------------------------------------------------------

class ProjectCreate(BaseModel):
    name: str
    description: str = ""
    system_prompt: str = ""
    chat_model: str = ""
    embedding_model: str = "text-embedding-3-small"


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    system_prompt: Optional[str] = None
    chat_model: Optional[str] = None
    embedding_model: Optional[str] = None


@app.get("/api/projects")
def list_projects():
    sb = get_supabase()
    r = sb.table("projects").select("*").order("created_at", desc=True).execute()
    return r.data or []


@app.post("/api/projects")
def create_project(req: ProjectCreate):
    sb = get_supabase()
    r = sb.table("projects").insert(req.model_dump()).execute()
    return r.data[0]


@app.get("/api/projects/{project_id}")
def get_project(project_id: str):
    sb = get_supabase()
    r = sb.table("projects").select("*").eq("id", project_id).single().execute()
    return r.data


@app.patch("/api/projects/{project_id}")
def update_project(project_id: str, req: ProjectUpdate):
    sb = get_supabase()
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    if not updates:
        return get_project(project_id)
    r = sb.table("projects").update(updates).eq("id", project_id).execute()
    return r.data[0]


@app.delete("/api/projects/{project_id}")
def delete_project(project_id: str):
    sb = get_supabase()
    sb.table("projects").delete().eq("id", project_id).execute()
    return {"status": "deleted"}


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

@app.get("/api/stats")
def get_stats(project_id: str | None = Query(None)):
    sb = get_supabase()
    counts = {}
    for table in ["knowledge_documents", "tax_law_chunks", "vendor_background_chunks", "rcw_chunks"]:
        try:
            q = sb.table(table).select("id", count="exact")
            if project_id:
                q = q.eq("project_id", project_id)
            r = q.limit(0).execute()
            counts[table] = r.count or 0
        except Exception:
            counts[table] = None
    return counts


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------

@app.get("/api/documents")
def list_documents(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    category: str | None = Query(None),
    source_type: str | None = Query(None),
    project_id: str | None = Query(None),
    tag: str | None = Query(None),
):
    sb = get_supabase()
    query = sb.table("knowledge_documents").select(
        "id, document_type, source_type, title, source_file, source_url, citation, law_category, "
        "total_chunks, processing_status, created_at, topic_tags",
        count="exact",
    )
    if project_id:
        query = query.eq("project_id", project_id)
    if category:
        query = query.eq("law_category", category)
    if source_type:
        query = query.eq("source_type", source_type)
    if tag:
        query = query.contains("topic_tags", [tag])
    query = query.order("created_at", desc=True).range(offset, offset + limit - 1)
    r = query.execute()
    return {"documents": r.data, "total": r.count}


@app.get("/api/documents/categories")
def get_categories(project_id: str | None = Query(None)):
    sb = get_supabase()
    counts: dict[str, int] = {}
    offset = 0
    batch = 1000
    while True:
        q = sb.table("knowledge_documents").select("law_category")
        if project_id:
            q = q.eq("project_id", project_id)
        r = q.range(offset, offset + batch - 1).execute()
        rows = r.data or []
        for row in rows:
            cat = row.get("law_category") or "Other"
            counts[cat] = counts.get(cat, 0) + 1
        if len(rows) < batch:
            break
        offset += batch
    return {"categories": counts}


@app.get("/api/documents/source-types")
def get_source_types(project_id: str | None = Query(None)):
    sb = get_supabase()
    counts: dict[str, int] = {}
    offset = 0
    batch = 1000
    while True:
        q = sb.table("knowledge_documents").select("source_type")
        if project_id:
            q = q.eq("project_id", project_id)
        r = q.range(offset, offset + batch - 1).execute()
        rows = r.data or []
        for row in rows:
            st = row.get("source_type") or "unknown"
            counts[st] = counts.get(st, 0) + 1
        if len(rows) < batch:
            break
        offset += batch
    return {"source_types": counts}


@app.get("/api/documents/tags")
def get_tags(
    project_id: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    """Return the most common topic tags with their document counts."""
    sb = get_supabase()
    counts: dict[str, int] = {}
    offset = 0
    batch = 1000
    while True:
        q = sb.table("knowledge_documents").select("topic_tags")
        if project_id:
            q = q.eq("project_id", project_id)
        r = q.range(offset, offset + batch - 1).execute()
        rows = r.data or []
        for row in rows:
            tags = row.get("topic_tags") or []
            for tag in tags:
                counts[tag] = counts.get(tag, 0) + 1
        if len(rows) < batch:
            break
        offset += batch
    sorted_tags = sorted(counts.items(), key=lambda x: x[1], reverse=True)[:limit]
    return {"tags": [{"tag": t, "count": c} for t, c in sorted_tags]}


@app.get("/api/chat/recent")
def get_recent_chats(
    limit: int = Query(5, ge=1, le=20),
    project_id: str | None = Query(None),
):
    sb = get_supabase()
    q = sb.table("chat_usage_log").select(
        "id, question, chat_model, response_time_ms, sources_count, is_error, created_at"
    )
    if project_id:
        q = q.eq("project_id", project_id)
    r = q.order("created_at", desc=True).limit(limit).execute()
    return {"chats": r.data or []}


@app.get("/api/documents/{doc_id}")
def get_document(doc_id: str):
    sb = get_supabase()
    r = sb.table("knowledge_documents").select("*").eq("id", doc_id).single().execute()
    chunks = sb.table("tax_law_chunks").select(
        "id, chunk_number, chunk_text, citation, section_title, law_category"
    ).eq("document_id", doc_id).order("chunk_number").execute()
    return {"document": r.data, "chunks": chunks.data}


# ---------------------------------------------------------------------------
# Ingest
# ---------------------------------------------------------------------------

@app.post("/api/ingest/pdf")
@limiter.limit("10/minute")
async def upload_pdf(
    request: Request,
    file: UploadFile = File(...),
    category: str = Form("Other"),
    citation: str = Form(""),
    project_id: str = Form(""),
):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        return {"status": "error", "error": "Only PDF files are supported"}
    file_bytes = await file.read()
    result = ingest_pdf(
        file_bytes, file.filename, category, citation or None,
        project_id=project_id or None,
    )
    return result


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

class SearchRequest(BaseModel):
    query: str
    top_k: int = 5
    threshold: float = 0.3
    project_id: str | None = None
    tags: list[str] | None = None


@app.post("/api/search")
@limiter.limit("60/minute")
def search(request: Request, req: SearchRequest):
    results = retrieve(req.query, req.top_k, project_id=req.project_id, tags=req.tags)
    return {
        "query": req.query,
        "results": results,
        "count": len(results),
    }


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------

class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[ChatMessage] = []
    top_k: int = 6
    project_id: str | None = None
    model_override: str | None = None
    tags: list[str] | None = None


DEFAULT_SYSTEM_PROMPT = """You are an expert Washington State tax law assistant with access to a knowledge base of legal documents, WAC/RCW codes, Excise Tax Advisories, and WA Department of Revenue guidance. You also have access to live web search results from dor.wa.gov, app.leg.wa.gov (RCW statutes, WAC regulations), and taxpedia.dor.wa.gov (tax determinations).

CITATION RULES (MANDATORY):
1. Cite every factual claim using [N] where N matches the source numbers provided in the context.
2. Place citations immediately after the statement they support, e.g. "Manufacturing equipment is exempt under the M&E exemption [2]."
3. When referencing a specific law, include the code inline, e.g. "as specified in RCW 82.08.02565 [3]."
4. When a statement draws from multiple sources, cite all of them: [1][3].
5. Never make tax law claims without a source citation.
6. If the provided sources are insufficient to answer, state this clearly.
7. Sources may come from the local knowledge base or live web search — treat both equally.

TRIANGULATION AND AUTHORITY:
When possible, support answers by citing multiple agreeing source types. For example, cite the RCW statute, the implementing WAC rule, AND any relevant ETA or WTD. Source tags in the context indicate the type: [RCW], [WAC], [ETA], [WTD], [DOR].

Authority hierarchy (strongest to weakest):
1. Court cases (rarely available)
2. RCW Statutes — most authoritative statutory law
3. WAC Regulations — implementing rules with force of law
4. Tax Determinations (WTD) — administrative precedent
5. Excise Tax Advisories (ETA) — official DOR interpretation
6. Interim Guidance Statements — temporary, eventually replaced
7. Special Notices, Industry Guides, Tax Topics — helpful but can be oversimplified

Identify when sources agree and note any tension between statute and interpretation.

Be concise, accurate, and always ground your answers in the provided sources."""


def _authority_tag(chunk: dict) -> str:
    """Return a short tag for the source authority type."""
    citation = (chunk.get("citation") or "").upper()
    category = (chunk.get("law_category") or "").upper()
    if "RCW" in citation or "RCW" in category:
        return "RCW"
    if "WAC" in citation or "WAC" in category or "ADMINISTRATIVE CODE" in category:
        return "WAC"
    if "ETA" in citation or "EXCISE TAX ADVISORY" in category:
        return "ETA"
    if "WTD" in citation or "DETERMINATION" in category:
        return "WTD"
    if "INTERIM" in category:
        return "IGS"
    if "SPECIAL NOTICE" in category:
        return "SN"
    if "TAX TOPIC" in category:
        return "TT"
    if "INDUSTRY" in category:
        return "IG"
    return "DOR"


def _build_rag_prompt(chunks: list[dict]) -> str:
    """Format retrieved chunks into a context block for the LLM."""
    if not chunks:
        return "No relevant documents were found."
    parts = []
    for i, chunk in enumerate(chunks, 1):
        citation = chunk.get("citation", "Unknown")
        source_url = chunk.get("source_url", "")
        text = chunk.get("chunk_text", "")[:1500]
        similarity = chunk.get("similarity", 0)
        source_type = chunk.get("source", "local")
        web_tag = "Web" if source_type == "perplexity" else "KB"
        auth_tag = _authority_tag(chunk)
        header = f"[{i}] [{web_tag}] [{auth_tag}] ({citation}"
        if source_url:
            header += f" | {source_url}"
        if isinstance(similarity, (int, float)) and similarity > 0:
            header += f", relevance: {similarity:.0%}"
        header += ")"
        parts.append(f"{header}\n{text}")
    return "\n\n---\n\n".join(parts)


@app.post("/api/chat")
@limiter.limit("20/minute")
def chat(request: Request, req: ChatRequest):
    sb = get_supabase()

    # Load project-specific settings
    system_prompt = DEFAULT_SYSTEM_PROMPT
    chat_model = None  # Will be set by router, project override, or user override
    complexity = None

    # 1. User-selected model override (from chat dropdown) takes priority
    if req.model_override:
        chat_model = req.model_override
        complexity = "manual"

    # 2. Check project-level model setting
    if req.project_id:
        try:
            project = sb.table("projects").select(
                "system_prompt, chat_model"
            ).eq("id", req.project_id).single().execute()
            if project.data.get("system_prompt"):
                system_prompt = project.data["system_prompt"]
            if chat_model is None:
                proj_model = project.data.get("chat_model", "")
                if proj_model and proj_model not in ("gpt-5.2", ""):
                    chat_model = proj_model
                    complexity = "override"
        except Exception:
            pass

    # 3. Automatic model routing if no override
    if chat_model is None:
        chat_model, complexity = route_model(req.message, len(req.history))

    # 1. Retrieve relevant chunks via hybrid search + reranking
    chunks = retrieve(req.message, req.top_k, project_id=req.project_id, tags=req.tags)

    # 1b. Augment with Perplexity live web search (parallel source)
    try:
        pplx_chunks = perplexity_chat_search(req.message)
        if pplx_chunks:
            chunks = chunks + pplx_chunks
    except Exception:
        pass  # Perplexity failure should never break chat

    # 2. Build context
    context = _build_rag_prompt(chunks)

    # Detect provider based on model name
    use_openai = chat_model.startswith("gpt-")

    # 3. Build messages
    if use_openai:
        messages = [{"role": "system", "content": system_prompt + "\n\nRetrieved sources:\n\n" + context}]
        for msg in req.history:
            messages.append({"role": msg.role, "content": msg.content})
        messages.append({"role": "user", "content": req.message})
    else:
        anthropic_system = system_prompt + "\n\nRetrieved sources:\n\n" + context
        anthropic_messages = []
        for msg in req.history:
            anthropic_messages.append({"role": msg.role, "content": msg.content})
        anthropic_messages.append({"role": "user", "content": req.message})

    # 4. Stream response and log to DB
    local_count = sum(1 for c in chunks if c.get("source", "local") == "local")
    pplx_count = sum(1 for c in chunks if c.get("source") == "perplexity")
    started_at = time.time()
    logger.info(f"Chat routing: model={chat_model}, complexity={complexity}, provider={'openai' if use_openai else 'anthropic'}")

    def generate():
        full_response: list[str] = []
        is_error = False
        try:
            if use_openai:
                client = get_openai()
                stream = client.chat.completions.create(
                    model=chat_model,
                    max_completion_tokens=2048,
                    messages=messages,
                    stream=True,
                )
                for chunk in stream:
                    text = chunk.choices[0].delta.content
                    if text:
                        full_response.append(text)
                        yield text
            else:
                client = get_anthropic()
                with client.messages.stream(
                    model=chat_model,
                    max_tokens=2048,
                    system=anthropic_system,
                    messages=anthropic_messages,
                ) as stream:
                    for text in stream.text_stream:
                        full_response.append(text)
                        yield text
        except Exception as e:
            is_error = True
            error_text = f"\n\n[Error: {e}]"
            full_response.append(error_text)
            yield error_text
        finally:
            # Log chat to database
            response_text = "".join(full_response)
            elapsed_ms = int((time.time() - started_at) * 1000)
            try:
                log_row = {
                    "question": req.message[:2000],
                    "question_length": len(req.message),
                    "answer_length": len(response_text),
                    "assistant_response": response_text[:10000],
                    "sources_count": len(chunks),
                    "sources_json": sources,
                    "chat_model": chat_model,
                    "complexity": complexity,
                    "endpoint": "chat",
                    "response_time_ms": elapsed_ms,
                    "is_error": is_error,
                    "error_message": response_text[:500] if is_error else None,
                }
                if req.project_id:
                    log_row["project_id"] = req.project_id
                sb.table("chat_usage_log").insert(log_row).execute()
            except Exception:
                logger.warning("Failed to log chat to database")

    # 5. Return sources metadata in header
    sources = [
        {
            "citation": c.get("citation", ""),
            "similarity": c.get("similarity", 0),
            "source_url": c.get("source_url"),
            "source": c.get("source", "local"),
        }
        for c in chunks
    ]
    headers = {"X-Sources": json.dumps(sources)}

    return StreamingResponse(
        generate(),
        media_type="text/plain",
        headers=headers,
    )


# ---------------------------------------------------------------------------
# Web Scraping
# ---------------------------------------------------------------------------

# In-memory job tracking (simple; lost on restart)
_scrape_jobs: dict[str, dict] = {}
_scrape_stop_flags: dict[str, bool] = {}


class ScrapeRequest(BaseModel):
    url: str
    project_id: str | None = None
    include_patterns: list[str] | None = None


class DiscoverRequest(BaseModel):
    url: str
    include_patterns: list[str] | None = None


@app.post("/api/scrape/discover")
@limiter.limit("10/minute")
def scrape_discover(request: Request, req: DiscoverRequest):
    """Preview: discover and count URLs without scraping."""
    try:
        result = discover_and_filter(req.url, include_patterns=req.include_patterns)
        return result
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.post("/api/scrape/start")
@limiter.limit("5/minute")
def scrape_start(request: Request, req: ScrapeRequest):
    """Start a background scrape job."""
    job_id = str(uuid.uuid4())[:8]

    _scrape_jobs[job_id] = {
        "job_id": job_id,
        "status": "starting",
        "base_url": req.url,
        "total_discovered": 0,
        "total_filtered": 0,
        "scraped": 0,
        "failed": 0,
        "documents_created": 0,
        "chunks_created": 0,
        "current_url": "",
        "elapsed_seconds": 0,
        "started_at": time.time(),
    }
    _scrape_stop_flags[job_id] = False

    def on_progress(stats: dict):
        _scrape_jobs[job_id].update(stats)
        _scrape_jobs[job_id]["job_id"] = job_id
        _scrape_jobs[job_id]["elapsed_seconds"] = time.time() - _scrape_jobs[job_id].get("started_at", time.time())

    def run():
        try:
            result = scrape_website(
                base_url=req.url,
                project_id=req.project_id,
                include_patterns=req.include_patterns,
                on_progress=on_progress,
                stop_flag=lambda: _scrape_stop_flags.get(job_id, False),
            )
            _scrape_jobs[job_id].update(result)
            _scrape_jobs[job_id]["job_id"] = job_id
        except Exception as e:
            _scrape_jobs[job_id]["status"] = "error"
            _scrape_jobs[job_id]["error"] = str(e)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()

    return {"job_id": job_id, "status": "started"}


@app.get("/api/scrape/status/{job_id}")
def scrape_status(job_id: str):
    """Get the current status of a scrape job."""
    job = _scrape_jobs.get(job_id)
    if not job:
        return JSONResponse(status_code=404, content={"error": "Job not found"})
    # Compute elapsed if still running
    if job.get("status") == "running":
        job["elapsed_seconds"] = time.time() - job.get("started_at", time.time())
    return job


@app.get("/api/scrape/jobs")
def scrape_jobs():
    """List all scrape jobs."""
    jobs = sorted(_scrape_jobs.values(), key=lambda j: j.get("started_at", 0), reverse=True)
    return jobs


@app.post("/api/scrape/stop/{job_id}")
def scrape_stop(job_id: str):
    """Request a running scrape job to stop."""
    if job_id not in _scrape_jobs:
        return JSONResponse(status_code=404, content={"error": "Job not found"})
    _scrape_stop_flags[job_id] = True
    return {"job_id": job_id, "status": "stop_requested"}


# ---------------------------------------------------------------------------
# Website Monitor (Perplexity)
# ---------------------------------------------------------------------------

_monitor_jobs: dict[str, dict] = {}
_monitor_stop_flags: dict[str, bool] = {}


class MonitorRequest(BaseModel):
    project_id: str | None = None
    recency_filter: str = "month"
    auto_ingest: bool = False
    generate_summary: bool = True


@app.get("/api/monitor/queries")
def monitor_queries():
    """List predefined search queries."""
    return get_monitor_queries()


@app.post("/api/monitor/start")
@limiter.limit("5/minute")
def monitor_start(request: Request, req: MonitorRequest):
    """Start a background monitor check job."""
    if not settings.PERPLEXITY_API_KEY:
        return JSONResponse(status_code=400, content={"error": "PERPLEXITY_API_KEY not configured"})

    job_id = str(uuid.uuid4())[:8]

    _monitor_jobs[job_id] = {
        "job_id": job_id,
        "status": "starting",
        "total_queries": 0,
        "queries_completed": 0,
        "urls_found": 0,
        "new_urls": 0,
        "existing_urls": 0,
        "ingested": 0,
        "ingest_failed": 0,
        "current_query": "",
        "elapsed_seconds": 0,
        "started_at": time.time(),
        "new_url_list": [],
        "summary": None,
    }
    _monitor_stop_flags[job_id] = False

    def on_progress(stats: dict):
        _monitor_jobs[job_id].update(stats)
        _monitor_jobs[job_id]["job_id"] = job_id
        _monitor_jobs[job_id]["elapsed_seconds"] = (
            time.time() - _monitor_jobs[job_id].get("started_at", time.time())
        )

    def run():
        try:
            result = run_monitor_check(
                project_id=req.project_id,
                recency_filter=req.recency_filter,
                auto_ingest=req.auto_ingest,
                generate_summary=req.generate_summary,
                on_progress=on_progress,
                stop_flag=lambda: _monitor_stop_flags.get(job_id, False),
            )
            _monitor_jobs[job_id].update(result)
            _monitor_jobs[job_id]["job_id"] = job_id
        except Exception as e:
            _monitor_jobs[job_id]["status"] = "error"
            _monitor_jobs[job_id]["error"] = str(e)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return {"job_id": job_id, "status": "started"}


@app.get("/api/monitor/status/{job_id}")
def monitor_status(job_id: str):
    """Get monitor job status."""
    job = _monitor_jobs.get(job_id)
    if not job:
        return JSONResponse(status_code=404, content={"error": "Job not found"})
    if job.get("status") == "running":
        job["elapsed_seconds"] = time.time() - job.get("started_at", time.time())
    return job


@app.get("/api/monitor/jobs")
def monitor_jobs_list():
    """List all monitor jobs."""
    jobs = sorted(
        _monitor_jobs.values(),
        key=lambda j: j.get("started_at", 0),
        reverse=True,
    )
    return jobs


@app.post("/api/monitor/stop/{job_id}")
def monitor_stop(job_id: str):
    """Stop a running monitor job."""
    if job_id not in _monitor_jobs:
        return JSONResponse(status_code=404, content={"error": "Job not found"})
    _monitor_stop_flags[job_id] = True
    return {"job_id": job_id, "status": "stop_requested"}


# ---------------------------------------------------------------------------
# Page Monitor (DOR page-change detection)
# ---------------------------------------------------------------------------

_crawl_jobs: dict[str, dict] = {}
_crawl_stop_flags: dict[str, bool] = {}


class CrawlRequest(BaseModel):
    project_id: str | None = None
    auto_ingest: bool = True


class AddPageRequest(BaseModel):
    url: str
    category: str | None = None
    project_id: str | None = None


@app.post("/api/monitor/crawl")
@limiter.limit("3/minute")
def crawl_start(request: Request, req: CrawlRequest):
    """Start a full page crawl + change detection job."""
    job_id = str(uuid.uuid4())[:8]

    _crawl_jobs[job_id] = {
        "job_id": job_id,
        "status": "starting",
        "total_pages": len(MONITORED_URLS),
        "pages_crawled": 0,
        "pages_new": 0,
        "pages_modified": 0,
        "pages_unchanged": 0,
        "pages_error": 0,
        "substantive_changes": 0,
        "auto_ingested": 0,
        "new_wtds_found": 0,
        "current_url": "",
        "elapsed_seconds": 0,
        "started_at": time.time(),
        "changes": [],
        "errors": [],
    }
    _crawl_stop_flags[job_id] = False

    def on_progress(stats: dict):
        _crawl_jobs[job_id].update(stats)
        _crawl_jobs[job_id]["job_id"] = job_id
        _crawl_jobs[job_id]["elapsed_seconds"] = (
            time.time() - _crawl_jobs[job_id].get("started_at", time.time())
        )

    def run():
        try:
            monitor = PageMonitor(project_id=req.project_id)
            result = monitor.run_full_crawl(
                auto_ingest=req.auto_ingest,
                on_progress=on_progress,
                stop_flag=lambda: _crawl_stop_flags.get(job_id, False),
            )
            _crawl_jobs[job_id].update(result)
            _crawl_jobs[job_id]["job_id"] = job_id
        except Exception as e:
            _crawl_jobs[job_id]["status"] = "error"
            _crawl_jobs[job_id]["error"] = str(e)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return {"job_id": job_id, "status": "started"}


@app.get("/api/monitor/crawl/status/{job_id}")
def crawl_status(job_id: str):
    """Get crawl job status."""
    job = _crawl_jobs.get(job_id)
    if not job:
        return JSONResponse(status_code=404, content={"error": "Job not found"})
    if job.get("status") == "running":
        job["elapsed_seconds"] = time.time() - job.get("started_at", time.time())
    return job


@app.get("/api/monitor/crawl/jobs")
def crawl_jobs_list():
    """List all crawl jobs."""
    jobs = sorted(
        _crawl_jobs.values(),
        key=lambda j: j.get("started_at", 0),
        reverse=True,
    )
    return jobs


@app.post("/api/monitor/crawl/stop/{job_id}")
def crawl_stop(job_id: str):
    """Stop a running crawl job."""
    if job_id not in _crawl_jobs:
        return JSONResponse(status_code=404, content={"error": "Job not found"})
    _crawl_stop_flags[job_id] = True
    return {"job_id": job_id, "status": "stop_requested"}


@app.get("/api/monitor/pages")
def list_monitored_pages(project_id: str | None = Query(None)):
    """List all monitored pages with their last check status."""
    sb = get_supabase()
    q = sb.table("monitor_page_state").select("*")
    if project_id:
        q = q.eq("project_id", project_id)
    r = q.order("last_checked_at", desc=True).execute()
    return {"pages": r.data or [], "total": len(r.data or [])}


@app.post("/api/monitor/pages")
def add_monitored_page(req: AddPageRequest):
    """Add a new URL to the monitored pages list."""
    sb = get_supabase()
    from scraper import categorize_url
    row = {
        "url": req.url,
        "category": req.category or categorize_url(req.url),
        "status": "active",
    }
    if req.project_id:
        row["project_id"] = req.project_id
    try:
        r = sb.table("monitor_page_state").insert(row).execute()
        return r.data[0]
    except Exception as e:
        return JSONResponse(status_code=400, content={"error": str(e)})


@app.delete("/api/monitor/pages/{page_id}")
def remove_monitored_page(page_id: str):
    """Remove a monitored page."""
    sb = get_supabase()
    sb.table("monitor_page_state").delete().eq("id", page_id).execute()
    return {"status": "deleted"}


@app.get("/api/monitor/changes")
def list_changes(
    project_id: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    change_type: str | None = Query(None),
    substantive_only: bool = Query(False),
):
    """List detected changes with filtering."""
    sb = get_supabase()
    q = sb.table("monitor_change_log").select("*", count="exact")
    if project_id:
        q = q.eq("project_id", project_id)
    if change_type:
        q = q.eq("change_type", change_type)
    if substantive_only:
        q = q.eq("is_substantive", True)
    r = q.order("detected_at", desc=True).range(offset, offset + limit - 1).execute()
    return {"changes": r.data or [], "total": r.count}


@app.post("/api/monitor/changes/{change_id}/approve")
def approve_change(change_id: str):
    """Approve a pending change — ingest/re-ingest the page into the knowledge base."""
    sb = get_supabase()
    try:
        r = sb.table("monitor_change_log").select("*").eq("id", change_id).single().execute()
        change = r.data
    except Exception:
        return JSONResponse(status_code=404, content={"error": "Change not found"})

    if change.get("review_status") == "approved":
        return {"status": "already_approved", "change_id": change_id}

    # Ingest the page
    url = change["url"]
    project_id = change.get("project_id")
    monitor = PageMonitor(project_id=project_id)
    ingested = monitor._reingest_page(url)

    # Update change status
    sb.table("monitor_change_log").update({
        "review_status": "approved",
        "auto_ingested": ingested,
    }).eq("id", change_id).execute()

    return {"status": "approved", "ingested": ingested, "change_id": change_id}


@app.post("/api/monitor/changes/{change_id}/dismiss")
def dismiss_change(change_id: str):
    """Dismiss a pending change — skip ingestion."""
    sb = get_supabase()
    try:
        sb.table("monitor_change_log").update({
            "review_status": "dismissed",
        }).eq("id", change_id).execute()
        return {"status": "dismissed", "change_id": change_id}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/api/monitor/changes/recent")
def recent_changes(
    project_id: str | None = Query(None),
    limit: int = Query(10, ge=1, le=50),
):
    """Dashboard widget: last N substantive changes."""
    sb = get_supabase()
    q = sb.table("monitor_change_log").select("*").eq("is_substantive", True)
    if project_id:
        q = q.eq("project_id", project_id)
    r = q.order("detected_at", desc=True).limit(limit).execute()
    return {"changes": r.data or []}


# ---------------------------------------------------------------------------
# Schedule Management (automated daily crawls)
# ---------------------------------------------------------------------------

class ScheduleUpdate(BaseModel):
    enabled: Optional[bool] = None
    hour_utc: Optional[int] = None
    minute_utc: Optional[int] = None
    runs_per_day: Optional[int] = None
    auto_ingest: Optional[bool] = None
    project_id: Optional[str] = None


@app.get("/api/monitor/schedule")
def get_schedule():
    """Get the current daily crawl schedule config."""
    sb = get_supabase()
    try:
        r = sb.table("monitor_schedule_config").select("*").limit(1).execute()
        if r.data:
            config = r.data[0]
            # Add next run time from scheduler
            job = scheduler.get_job("daily_crawl")
            config["next_run_at"] = (
                job.next_run_time.isoformat() if job and job.next_run_time else None
            )
            return config
        return {"enabled": False, "hour_utc": 14, "minute_utc": 0, "auto_ingest": True}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.post("/api/monitor/schedule")
def update_schedule(req: ScheduleUpdate):
    """Update the daily crawl schedule and sync the scheduler."""
    sb = get_supabase()
    try:
        # Get existing config
        existing = sb.table("monitor_schedule_config").select("*").limit(1).execute()
        if not existing.data:
            # Create default row
            row = {
                "enabled": req.enabled if req.enabled is not None else False,
                "hour_utc": req.hour_utc if req.hour_utc is not None else 14,
                "minute_utc": req.minute_utc if req.minute_utc is not None else 0,
                "auto_ingest": req.auto_ingest if req.auto_ingest is not None else True,
            }
            if req.project_id:
                row["project_id"] = req.project_id
            sb.table("monitor_schedule_config").insert(row).execute()
        else:
            config_id = existing.data[0]["id"]
            updates = {"updated_at": datetime.now(timezone.utc).isoformat()}
            if req.enabled is not None:
                updates["enabled"] = req.enabled
            if req.hour_utc is not None:
                updates["hour_utc"] = req.hour_utc
            if req.minute_utc is not None:
                updates["minute_utc"] = req.minute_utc
            if req.runs_per_day is not None:
                updates["runs_per_day"] = req.runs_per_day
            if req.auto_ingest is not None:
                updates["auto_ingest"] = req.auto_ingest
            if req.project_id is not None:
                updates["project_id"] = req.project_id
            sb.table("monitor_schedule_config").update(updates).eq("id", config_id).execute()

        # Sync scheduler to pick up new config
        _sync_scheduler_from_db()

        return get_schedule()
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.post("/api/monitor/schedule/run-now")
def schedule_run_now():
    """Trigger an immediate scheduled crawl (same as the daily job would do)."""
    thread = threading.Thread(target=_scheduled_crawl, daemon=True)
    thread.start()
    return {"status": "started", "message": "Scheduled crawl triggered immediately"}

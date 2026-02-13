import json
import logging
import threading
import time
import uuid
from typing import Optional

logger = logging.getLogger(__name__)

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
from retrieval import retrieve
from ingest import ingest_pdf
from scraper import scrape_website, discover_and_filter
from monitor import run_monitor_check, get_monitor_queries, perplexity_chat_search

_openai: OpenAI | None = None


def get_openai() -> OpenAI:
    global _openai
    if _openai is None:
        _openai = OpenAI(api_key=settings.OPENAI_API_KEY)
    return _openai


limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"])
app = FastAPI(title="RAG Platform API", version="0.3.0")
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
    chat_model: str = "gpt-5.2"
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


@app.post("/api/search")
@limiter.limit("60/minute")
def search(request: Request, req: SearchRequest):
    results = retrieve(req.query, req.top_k, project_id=req.project_id)
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


DEFAULT_SYSTEM_PROMPT = """You are an expert Washington State tax law assistant with access to a knowledge base of legal documents, WAC/RCW codes, Excise Tax Advisories, and WA Department of Revenue guidance. You also have access to live web search results from dor.wa.gov.

CITATION RULES (MANDATORY):
1. Cite every factual claim using [N] where N matches the source numbers provided in the context.
2. Place citations immediately after the statement they support, e.g. "Manufacturing equipment is exempt under the M&E exemption [2]."
3. When referencing a specific law, include the code inline, e.g. "as specified in RCW 82.08.02565 [3]."
4. When a statement draws from multiple sources, cite all of them: [1][3].
5. Never make tax law claims without a source citation.
6. If the provided sources are insufficient to answer, state this clearly.
7. Sources may come from the local knowledge base or live web search — treat both equally.

Be concise, accurate, and always ground your answers in the provided sources."""


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
        tag = "Web" if source_type == "perplexity" else "KB"
        header = f"[{i}] [{tag}] ({citation}"
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
    chat_model = settings.CHAT_MODEL
    if req.project_id:
        try:
            project = sb.table("projects").select(
                "system_prompt, chat_model"
            ).eq("id", req.project_id).single().execute()
            if project.data.get("system_prompt"):
                system_prompt = project.data["system_prompt"]
            if project.data.get("chat_model"):
                chat_model = project.data["chat_model"]
        except Exception:
            pass

    # 1. Retrieve relevant chunks via hybrid search + reranking
    chunks = retrieve(req.message, req.top_k, project_id=req.project_id)

    # 1b. Augment with Perplexity live web search (parallel source)
    try:
        pplx_chunks = perplexity_chat_search(req.message)
        if pplx_chunks:
            chunks = chunks + pplx_chunks
    except Exception:
        pass  # Perplexity failure should never break chat

    # 2. Build context
    context = _build_rag_prompt(chunks)

    # 3. Build messages for OpenAI
    messages = [{"role": "system", "content": system_prompt + "\n\nRetrieved sources:\n\n" + context}]
    for msg in req.history:
        messages.append({"role": msg.role, "content": msg.content})
    messages.append({"role": "user", "content": req.message})

    # 4. Stream response from OpenAI and log to DB
    client = get_openai()
    local_count = sum(1 for c in chunks if c.get("source", "local") == "local")
    pplx_count = sum(1 for c in chunks if c.get("source") == "perplexity")
    started_at = time.time()

    def generate():
        full_response: list[str] = []
        is_error = False
        try:
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

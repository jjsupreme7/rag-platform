import json
from typing import Optional

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
    r = sb.table("projects").select("*").order("created_at").execute()
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
    project_id: str | None = Query(None),
):
    sb = get_supabase()
    query = sb.table("knowledge_documents").select(
        "id, document_type, title, source_file, citation, law_category, "
        "total_chunks, processing_status, created_at, topic_tags",
        count="exact",
    )
    if project_id:
        query = query.eq("project_id", project_id)
    if category:
        query = query.eq("law_category", category)
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


DEFAULT_SYSTEM_PROMPT = """You are a helpful AI assistant with access to a knowledge base. Answer questions based on the provided source documents. If sources are insufficient, say so clearly. Cite sources using [Source N] notation. Be concise and direct."""


def _build_rag_prompt(chunks: list[dict]) -> str:
    """Format retrieved chunks into a context block for the LLM."""
    if not chunks:
        return "No relevant documents were found."
    parts = []
    for i, chunk in enumerate(chunks, 1):
        citation = chunk.get("citation", "Unknown")
        text = chunk.get("chunk_text", "")[:1500]
        similarity = chunk.get("similarity", 0)
        if isinstance(similarity, (int, float)):
            parts.append(f"[Source {i}] ({citation}, relevance: {similarity:.0%})\n{text}")
        else:
            parts.append(f"[Source {i}] ({citation})\n{text}")
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

    # 2. Build context
    context = _build_rag_prompt(chunks)

    # 3. Build messages for OpenAI
    messages = [{"role": "system", "content": system_prompt + "\n\nRetrieved sources:\n\n" + context}]
    for msg in req.history:
        messages.append({"role": msg.role, "content": msg.content})
    messages.append({"role": "user", "content": req.message})

    # 4. Stream response from OpenAI
    client = get_openai()

    def generate():
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
                    yield text
        except Exception as e:
            yield f"\n\n[Error: {e}]"

    # 5. Return sources metadata in header
    sources = [
        {"citation": c.get("citation", ""), "similarity": c.get("similarity", 0)}
        for c in chunks
    ]
    headers = {"X-Sources": json.dumps(sources)}

    return StreamingResponse(
        generate(),
        media_type="text/plain",
        headers=headers,
    )

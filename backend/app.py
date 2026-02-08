import json

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from openai import OpenAI

from config import settings
from db import get_supabase
from retrieval import retrieve

_openai: OpenAI | None = None


def get_openai() -> OpenAI:
    global _openai
    if _openai is None:
        _openai = OpenAI(api_key=settings.OPENAI_API_KEY)
    return _openai


app = FastAPI(title="RAG Platform API", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Sources"],
)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "supabase_configured": bool(settings.SUPABASE_URL),
        "openai_configured": bool(settings.OPENAI_API_KEY),
        "anthropic_configured": bool(settings.ANTHROPIC_API_KEY),
    }


@app.get("/api/stats")
def get_stats():
    sb = get_supabase()
    counts = {}
    for table in ["knowledge_documents", "tax_law_chunks", "vendor_background_chunks", "rcw_chunks"]:
        try:
            r = sb.table(table).select("id", count="exact").limit(0).execute()
            counts[table] = r.count or 0
        except Exception:
            counts[table] = None
    return counts


@app.get("/api/documents")
def list_documents(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    category: str | None = Query(None),
):
    sb = get_supabase()
    query = sb.table("knowledge_documents").select(
        "id, document_type, title, source_file, citation, law_category, "
        "total_chunks, processing_status, created_at, topic_tags",
        count="exact",
    )
    if category:
        query = query.eq("law_category", category)
    query = query.order("created_at", desc=True).range(offset, offset + limit - 1)
    r = query.execute()
    return {"documents": r.data, "total": r.count}


@app.get("/api/documents/{doc_id}")
def get_document(doc_id: str):
    sb = get_supabase()
    r = sb.table("knowledge_documents").select("*").eq("id", doc_id).single().execute()
    chunks = sb.table("tax_law_chunks").select(
        "id, chunk_number, chunk_text, citation, section_title, law_category"
    ).eq("document_id", doc_id).order("chunk_number").execute()
    return {"document": r.data, "chunks": chunks.data}


class SearchRequest(BaseModel):
    query: str
    top_k: int = 5
    threshold: float = 0.3


@app.post("/api/search")
def search(req: SearchRequest):
    results = retrieve(req.query, req.top_k)
    return {
        "query": req.query,
        "results": results,
        "count": len(results),
    }


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[ChatMessage] = []
    top_k: int = 6


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


SYSTEM_PROMPT = """You are a Washington State tax law expert assistant. You help users understand WA tax law including B&O tax, retail sales tax, use tax, and related exemptions.

Your knowledge base contains:
- Revised Code of Washington (RCW) chapters 82.04, 82.08, 82.12
- Washington Administrative Code (WAC) Title 458
- Excise Tax Advisories (ETAs) from the Department of Revenue
- Tax Determinations (WTDs) from the Appeals Division
- Special Notices, Tax Topics, and Industry Guides

Rules:
- Base your answers on the provided source documents. If sources are insufficient, say so clearly.
- Cite sources using [Source N] notation. Always include the specific RCW, WAC, or ETA number when available.
- Distinguish between statutes (RCW), regulations (WAC), and agency guidance (ETA/WTD). Statutes are the highest authority.
- When discussing exemptions, specify whether they apply to retail sales tax (RCW 82.08), use tax (RCW 82.12), or both.
- Note when law has changed over time. ESSB 5814 (effective October 1, 2025) significantly changed taxation of services.
- Be precise with legal terminology. For example, distinguish "digital automated services" from "custom software" as they have different tax treatments.
- Be concise and direct."""


@app.post("/api/chat")
def chat(req: ChatRequest):
    # 1. Retrieve relevant chunks via hybrid search + reranking
    chunks = retrieve(req.message, req.top_k)

    # 2. Build context
    context = _build_rag_prompt(chunks)

    # 3. Build messages for OpenAI
    messages = [{"role": "system", "content": SYSTEM_PROMPT + "\n\nRetrieved sources:\n\n" + context}]
    for msg in req.history:
        messages.append({"role": msg.role, "content": msg.content})
    messages.append({"role": "user", "content": req.message})

    # 4. Stream response from OpenAI
    client = get_openai()

    def generate():
        try:
            stream = client.chat.completions.create(
                model=settings.CHAT_MODEL,
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

    # 6. Return sources metadata in header
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

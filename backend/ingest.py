"""PDF ingestion: parse, chunk, embed, and store in Supabase."""

import re
import io
from typing import Optional

import pdfplumber
from openai import OpenAI

from config import settings
from db import get_supabase


def _get_openai() -> OpenAI:
    return OpenAI(api_key=settings.OPENAI_API_KEY)


# ---------------------------------------------------------------------------
# Text chunking (adapted from WATaxDesk/scripts/ingest_dor_documents.py)
# ---------------------------------------------------------------------------

def chunk_text(text: str, max_chars: int = 2000) -> list[str]:
    """Split text into chunks using paragraph → sentence → char splitting."""
    max_token_chars = 18000  # ~6000 tokens * 3 chars/token safety margin

    def split_by_sentences(t: str) -> list[str]:
        parts = re.split(r"(?<=[.!?])\s+", t)
        return [s.strip() for s in parts if s.strip()]

    def split_long(t: str, limit: int) -> list[str]:
        if len(t) <= limit:
            return [t]
        sentences = split_by_sentences(t)
        if len(sentences) > 1:
            result, current = [], ""
            for sent in sentences:
                if len(sent) > limit:
                    if current:
                        result.append(current.strip())
                        current = ""
                    for i in range(0, len(sent), limit):
                        result.append(sent[i : i + limit].strip())
                elif len(current) + len(sent) + 1 <= limit:
                    current = f"{current} {sent}" if current else sent
                else:
                    if current:
                        result.append(current.strip())
                    current = sent
            if current:
                result.append(current.strip())
            return result
        return [t[i : i + limit].strip() for i in range(0, len(t), limit)]

    chunks: list[str] = []
    current = ""

    for para in text.split("\n\n"):
        para = para.strip()
        if not para:
            continue
        if len(para) > max_token_chars:
            for pc in split_long(para, max_token_chars):
                if len(current) + len(pc) + 2 <= max_chars:
                    current = f"{current}\n\n{pc}" if current else pc
                else:
                    if current:
                        chunks.append(current.strip())
                    current = pc
        elif len(current) + len(para) + 2 <= max_chars:
            current = f"{current}\n\n{para}" if current else para
        else:
            if current:
                chunks.append(current.strip())
            current = para

    if current:
        chunks.append(current.strip())

    # Filter short chunks, then safety-split any still too long
    chunks = [c for c in chunks if len(c) > 50]
    final: list[str] = []
    for c in chunks:
        if len(c) > max_token_chars:
            final.extend(split_long(c, max_token_chars))
        else:
            final.append(c)
    return final


# ---------------------------------------------------------------------------
# Embedding
# ---------------------------------------------------------------------------

def get_embedding(text: str) -> Optional[list[float]]:
    """Generate embedding via OpenAI."""
    try:
        client = _get_openai()
        resp = client.embeddings.create(model=settings.EMBEDDING_MODEL, input=text)
        return resp.data[0].embedding
    except Exception as e:
        print(f"Embedding error: {e}")
        return None


# ---------------------------------------------------------------------------
# Ingestion pipeline
# ---------------------------------------------------------------------------

def extract_pdf_text(file_bytes: bytes) -> str:
    """Extract text from PDF bytes using pdfplumber."""
    text_parts: list[str] = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)
    return "\n\n".join(text_parts)


def ingest_pdf(
    file_bytes: bytes,
    filename: str,
    category: str = "Other",
    citation: str | None = None,
    project_id: str | None = None,
) -> dict:
    """
    Full ingestion pipeline: PDF → text → chunks → embeddings → Supabase.

    Returns: {document_id, title, chunks_created, status, error?}
    """
    # 1. Extract text
    text = extract_pdf_text(file_bytes)
    if not text or len(text) < 50:
        return {"document_id": None, "title": filename, "chunks_created": 0,
                "status": "error", "error": "Could not extract text from PDF"}

    # 2. Chunk
    chunks = chunk_text(text)
    if not chunks:
        return {"document_id": None, "title": filename, "chunks_created": 0,
                "status": "error", "error": "No chunks generated from text"}

    # 3. Create document record
    title = citation or filename.replace(".pdf", "").replace("_", " ")
    sb = get_supabase()

    doc_row = {
        "title": title,
        "document_type": "tax_law",
        "source_file": filename,
        "citation": citation or title,
        "law_category": category,
        "total_chunks": len(chunks),
        "processing_status": "processing",
    }
    if project_id:
        doc_row["project_id"] = project_id
    try:
        doc_result = sb.table("knowledge_documents").insert(doc_row).execute()
        doc_id = doc_result.data[0]["id"]
    except Exception as e:
        return {"document_id": None, "title": title, "chunks_created": 0,
                "status": "error", "error": f"Failed to create document: {e}"}

    # 4. Embed and insert chunks
    inserted = 0
    for i, chunk_content in enumerate(chunks):
        embedding = get_embedding(chunk_content)
        if not embedding:
            continue
        chunk_row = {
            "document_id": doc_id,
            "chunk_text": chunk_content,
            "chunk_number": i,
            "citation": citation or title,
            "law_category": category,
            "embedding": embedding,
        }
        if project_id:
            chunk_row["project_id"] = project_id
        try:
            sb.table("tax_law_chunks").insert(chunk_row).execute()
            inserted += 1
        except Exception as e:
            print(f"Chunk insert error: {e}")

    # 5. Update document status
    try:
        sb.table("knowledge_documents").update({
            "processing_status": "complete",
            "total_chunks": inserted,
        }).eq("id", doc_id).execute()
    except Exception:
        pass

    return {
        "document_id": doc_id,
        "title": title,
        "chunks_created": inserted,
        "status": "success",
    }

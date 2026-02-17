"""Hybrid search with RRF fusion and Cohere reranking (GPT-4o-mini fallback)."""

import json
import logging

import cohere
from openai import OpenAI

from config import settings
from db import get_supabase

logger = logging.getLogger(__name__)

RRF_K = 60  # Standard Reciprocal Rank Fusion constant


def _get_tagged_doc_ids(tags: list[str], project_id: str | None = None) -> set[str]:
    """Fetch document IDs whose topic_tags overlap with the given tags."""
    sb = get_supabase()
    doc_ids: set[str] = set()
    for tag in tags:
        q = sb.table("knowledge_documents").select("id").contains("topic_tags", [tag])
        if project_id:
            q = q.eq("project_id", project_id)
        r = q.execute()
        for row in r.data or []:
            doc_ids.add(row["id"])
    return doc_ids


def _get_openai() -> OpenAI:
    return OpenAI(api_key=settings.OPENAI_API_KEY)


def embed_query(query: str) -> list[float]:
    """Generate embedding using OpenAI text-embedding-3-small."""
    client = _get_openai()
    resp = client.embeddings.create(model=settings.EMBEDDING_MODEL, input=query)
    return resp.data[0].embedding


def vector_search(
    embedding: list[float], top_k: int = 10, threshold: float = 0.3,
    project_id: str | None = None,
) -> list[dict]:
    """Vector similarity search via Supabase RPC."""
    sb = get_supabase()
    params = {
        "query_embedding": embedding,
        "match_threshold": threshold,
        "match_count": top_k,
        "filter_project_id": project_id,
    }
    r = sb.rpc("search_tax_law", params).execute()
    return r.data or []


def keyword_search(
    query: str, top_k: int = 10, project_id: str | None = None,
    doc_ids: set[str] | None = None,
) -> list[dict]:
    """Full-text keyword search on tax_law_chunks using PostgreSQL websearch."""
    sb = get_supabase()
    try:
        q = (
            sb.table("tax_law_chunks")
            .select(
                "id, document_id, chunk_text, citation, section_title, "
                "law_category, tax_types, source_type"
            )
            .text_search("chunk_text", query, options={"type": "websearch"})
        )
        if project_id:
            q = q.eq("project_id", project_id)
        if doc_ids is not None:
            q = q.in_("document_id", list(doc_ids))
        r = q.limit(top_k).execute()
        results = r.data or []
        for chunk in results:
            chunk.setdefault("similarity", 0.0)
        return results
    except Exception:
        return []


def rrf_fuse(
    vector_results: list[dict],
    keyword_results: list[dict],
    vector_weight: float = 0.6,
    keyword_weight: float = 0.4,
) -> list[dict]:
    """Reciprocal Rank Fusion to combine vector and keyword rankings."""
    scores: dict[str, float] = {}
    chunk_map: dict[str, dict] = {}

    for rank, chunk in enumerate(vector_results, 1):
        cid = chunk["id"]
        scores[cid] = scores.get(cid, 0) + vector_weight / (RRF_K + rank)
        chunk_map[cid] = chunk

    for rank, chunk in enumerate(keyword_results, 1):
        cid = chunk["id"]
        scores[cid] = scores.get(cid, 0) + keyword_weight / (RRF_K + rank)
        if cid not in chunk_map:
            chunk_map[cid] = chunk

    sorted_ids = sorted(scores, key=lambda x: scores[x], reverse=True)
    fused = []
    for cid in sorted_ids:
        c = chunk_map[cid]
        c["rrf_score"] = scores[cid]
        fused.append(c)
    return fused


def rerank_cohere(query: str, chunks: list[dict], top_k: int = 6) -> list[dict]:
    """Use Cohere Rerank 3.5 to rerank chunks by relevance."""
    if not chunks or len(chunks) <= top_k:
        return chunks[:top_k]

    if not settings.COHERE_API_KEY:
        return None  # Signal to try fallback

    # Extract text for Cohere (include citation for context)
    documents = []
    for c in chunks:
        text = (c.get("chunk_text") or "")[:1500]
        citation = c.get("citation", "")
        documents.append(f"[{citation}] {text}" if citation else text)

    try:
        co = cohere.Client(api_key=settings.COHERE_API_KEY)
        response = co.rerank(
            model="rerank-v3.5",
            query=query,
            documents=documents,
            top_n=top_k,
        )
        reranked = []
        for result in response.results:
            chunk = chunks[result.index]
            chunk["rerank_score"] = result.relevance_score
            reranked.append(chunk)
        return reranked
    except Exception as e:
        logger.warning(f"Cohere reranking failed: {e}, trying GPT-4o-mini fallback")
        return None  # Signal to try fallback


def rerank_with_llm(query: str, chunks: list[dict], top_k: int = 6) -> list[dict]:
    """Fallback reranker using GPT-4o-mini when Cohere is unavailable."""
    if not chunks or len(chunks) <= top_k:
        return chunks[:top_k]

    formatted = []
    for i, c in enumerate(chunks):
        text = (c.get("chunk_text") or "")[:400]
        citation = c.get("citation", "Unknown")
        formatted.append(f"[{i}] ({citation})\n{text}")
    chunks_block = "\n\n".join(formatted)

    prompt = (
        "Score each chunk's relevance to this Washington State tax law question.\n\n"
        f"Question: {query}\n\n"
        f"Chunks:\n{chunks_block}\n\n"
        'Return JSON only: {"scores": [{"index": 0, "score": 8}, ...]}\n'
        "Score 1-10 where 10 = directly answers the question."
    )

    try:
        client = _get_openai()
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
        )
        data = json.loads(resp.choices[0].message.content)
        score_map = {s["index"]: s["score"] for s in data.get("scores", [])}
        scored = [(i, score_map.get(i, 0)) for i in range(len(chunks))]
        scored.sort(key=lambda x: x[1], reverse=True)
        return [chunks[i] for i, _ in scored[:top_k]]
    except Exception:
        return chunks[:top_k]


def rerank(query: str, chunks: list[dict], top_k: int = 6) -> list[dict]:
    """Rerank chunks: tries Cohere first, falls back to GPT-4o-mini."""
    # Try Cohere first
    result = rerank_cohere(query, chunks, top_k)
    if result is not None:
        return result

    # Fallback to GPT-4o-mini
    logger.info("Using GPT-4o-mini fallback reranker")
    return rerank_with_llm(query, chunks, top_k)


def retrieve(
    query: str, top_k: int = 6, project_id: str | None = None,
    tags: list[str] | None = None,
) -> list[dict]:
    """
    Full retrieval pipeline: embed -> hybrid search -> RRF fusion -> rerank.

    Uses Cohere Rerank 3.5 when available, falls back to GPT-4o-mini.
    When tags are provided, results are scoped to documents matching those tags.
    This is the main entry point called by app.py.
    """
    # Pre-fetch matching document IDs when tag filtering
    doc_ids: set[str] | None = None
    if tags:
        doc_ids = _get_tagged_doc_ids(tags, project_id)
        if not doc_ids:
            return []  # No documents match the tags

    embedding = embed_query(query)

    # Over-fetch when tag-filtering to compensate for post-filter reduction
    fetch_k = top_k * 6 if doc_ids else top_k * 3

    vec_results = vector_search(embedding, top_k=fetch_k, threshold=0.3, project_id=project_id)
    kw_results = keyword_search(query, top_k=fetch_k, project_id=project_id, doc_ids=doc_ids)

    # Post-filter vector results by tagged document IDs
    if doc_ids is not None:
        vec_results = [c for c in vec_results if c.get("document_id") in doc_ids]

    fused = rrf_fuse(vec_results, kw_results)

    reranked = rerank(query, fused[:15], top_k=top_k)

    return reranked

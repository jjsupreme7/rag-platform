"""Hybrid search with RRF fusion and LLM reranking."""

import json

from openai import OpenAI

from config import settings
from db import get_supabase

RRF_K = 60  # Standard Reciprocal Rank Fusion constant


def _get_openai() -> OpenAI:
    return OpenAI(api_key=settings.OPENAI_API_KEY)


def embed_query(query: str) -> list[float]:
    """Generate embedding using OpenAI text-embedding-3-small."""
    client = _get_openai()
    resp = client.embeddings.create(model=settings.EMBEDDING_MODEL, input=query)
    return resp.data[0].embedding


def vector_search(
    embedding: list[float], top_k: int = 10, threshold: float = 0.3
) -> list[dict]:
    """Vector similarity search via Supabase RPC."""
    sb = get_supabase()
    r = sb.rpc(
        "search_tax_law",
        {
            "query_embedding": embedding,
            "match_threshold": threshold,
            "match_count": top_k,
        },
    ).execute()
    return r.data or []


def keyword_search(query: str, top_k: int = 10) -> list[dict]:
    """Full-text keyword search on tax_law_chunks using PostgreSQL websearch."""
    sb = get_supabase()
    try:
        r = (
            sb.table("tax_law_chunks")
            .select(
                "id, document_id, chunk_text, citation, section_title, "
                "law_category, tax_types, source_type"
            )
            .text_search("chunk_text", query, options={"type": "websearch"})
            .limit(top_k)
            .execute()
        )
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


def rerank_with_llm(query: str, chunks: list[dict], top_k: int = 6) -> list[dict]:
    """Use GPT-4o-mini to rerank chunks by relevance. Falls back to RRF order on error."""
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
            model=settings.RERANK_MODEL,
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


def retrieve(query: str, top_k: int = 6) -> list[dict]:
    """
    Full retrieval pipeline: embed -> hybrid search -> RRF fusion -> LLM rerank.

    This is the main entry point called by app.py.
    """
    embedding = embed_query(query)

    vec_results = vector_search(embedding, top_k=top_k * 3, threshold=0.3)
    kw_results = keyword_search(query, top_k=top_k * 3)

    fused = rrf_fuse(vec_results, kw_results)

    reranked = rerank_with_llm(query, fused[:15], top_k=top_k)

    return reranked

"""Batch ingest local WTD PDFs into Supabase.

Usage: python ingest_wtds.py [--dry-run] [--limit N]

Reads WTD PDFs + JSON metadata from refund-engine knowledge base,
chunks, embeds, and stores in Supabase.
"""

import json
import os
import sys
import time
from pathlib import Path

from ingest import extract_pdf_text, chunk_text, get_embedding
from db import get_supabase

WTD_DIR = Path.home() / "Desktop/refund-engine/knowledge_base/wa_tax_law/tax_decisions"


def find_wtd_files() -> list[dict]:
    """Find all WTD PDF+JSON pairs."""
    pairs = []
    for year_dir in sorted(WTD_DIR.iterdir()):
        if not year_dir.is_dir():
            continue
        for json_file in sorted(year_dir.glob("*.json")):
            pdf_file = json_file.with_suffix(".pdf")
            if pdf_file.exists():
                with open(json_file) as f:
                    meta = json.load(f)
                pairs.append({
                    "pdf_path": str(pdf_file),
                    "citation": meta.get("citation", json_file.stem),
                    "summary": meta.get("summary", ""),
                    "year": meta.get("year", year_dir.name),
                    "filename": pdf_file.name,
                })
    return pairs


def get_existing_citations(sb) -> set[str]:
    """Get citations already in the database to skip duplicates."""
    existing = set()
    offset = 0
    while True:
        r = sb.table("knowledge_documents").select("citation").ilike(
            "citation", "%WTD%"
        ).range(offset, offset + 999).execute()
        rows = r.data or []
        for row in rows:
            existing.add(row.get("citation", ""))
        if len(rows) < 1000:
            break
        offset += 1000
    return existing


def ingest_one_wtd(sb, wtd: dict) -> dict:
    """Ingest a single WTD. Returns {status, chunks_created, error?}."""
    # Extract text
    with open(wtd["pdf_path"], "rb") as f:
        pdf_bytes = f.read()

    text = extract_pdf_text(pdf_bytes)
    if not text or len(text) < 50:
        return {"status": "skip", "chunks_created": 0, "error": "No text extracted"}

    # Chunk
    chunks = chunk_text(text)
    if not chunks:
        return {"status": "skip", "chunks_created": 0, "error": "No chunks generated"}

    # Create document record
    title = wtd["citation"]
    try:
        doc_result = sb.table("knowledge_documents").insert({
            "title": title,
            "document_type": "tax_law",
            "source_file": wtd["filename"],
            "citation": wtd["citation"],
            "law_category": "Tax Determination (WTD)",
            "total_chunks": len(chunks),
            "processing_status": "processing",
        }).execute()
        doc_id = doc_result.data[0]["id"]
    except Exception as e:
        return {"status": "error", "chunks_created": 0, "error": f"DB insert: {e}"}

    # Embed and insert chunks
    inserted = 0
    for i, chunk_content in enumerate(chunks):
        embedding = get_embedding(chunk_content)
        if not embedding:
            continue
        try:
            sb.table("tax_law_chunks").insert({
                "document_id": doc_id,
                "chunk_text": chunk_content,
                "chunk_number": i,
                "citation": wtd["citation"],
                "law_category": "Tax Determination (WTD)",
                "embedding": embedding,
            }).execute()
            inserted += 1
        except Exception as e:
            print(f"  Chunk {i} error: {e}")

    # Update status
    sb.table("knowledge_documents").update({
        "processing_status": "complete",
        "total_chunks": inserted,
    }).eq("id", doc_id).execute()

    return {"status": "success", "chunks_created": inserted}


def main():
    dry_run = "--dry-run" in sys.argv
    limit = None
    if "--limit" in sys.argv:
        idx = sys.argv.index("--limit")
        limit = int(sys.argv[idx + 1])

    print(f"Scanning WTD directory: {WTD_DIR}")
    wtds = find_wtd_files()
    print(f"Found {len(wtds)} WTD PDF+JSON pairs")

    sb = get_supabase()
    existing = get_existing_citations(sb)
    print(f"Already ingested: {len(existing)} WTDs")

    # Filter out already-ingested
    to_ingest = [w for w in wtds if w["citation"] not in existing]
    print(f"New WTDs to ingest: {len(to_ingest)}")

    if limit:
        to_ingest = to_ingest[:limit]
        print(f"Limited to: {limit}")

    if dry_run:
        print("\n[DRY RUN] Would ingest:")
        for w in to_ingest[:10]:
            print(f"  {w['citation']} ({w['filename']})")
        if len(to_ingest) > 10:
            print(f"  ... and {len(to_ingest) - 10} more")
        return

    success = 0
    errors = 0
    total_chunks = 0
    start = time.time()

    for i, wtd in enumerate(to_ingest):
        print(f"[{i+1}/{len(to_ingest)}] {wtd['citation']}...", end=" ", flush=True)
        result = ingest_one_wtd(sb, wtd)
        if result["status"] == "success":
            success += 1
            total_chunks += result["chunks_created"]
            print(f"{result['chunks_created']} chunks")
        else:
            errors += 1
            print(f"{result['status']}: {result.get('error', '')}")

    elapsed = time.time() - start
    print(f"\nDone in {elapsed:.0f}s")
    print(f"  Success: {success}")
    print(f"  Errors/Skips: {errors}")
    print(f"  Total chunks: {total_chunks}")


if __name__ == "__main__":
    main()

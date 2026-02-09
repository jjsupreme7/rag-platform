"""Run database migration to add multi-project support.

NOTE: Run the following SQL in your Supabase SQL Editor FIRST:

-- 1. Create projects table
CREATE TABLE IF NOT EXISTS projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    system_prompt TEXT DEFAULT '',
    chat_model TEXT DEFAULT 'gpt-5.2',
    embedding_model TEXT DEFAULT 'text-embedding-3-small',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- 2. Add project_id columns
ALTER TABLE knowledge_documents ADD COLUMN IF NOT EXISTS project_id UUID REFERENCES projects(id);
CREATE INDEX IF NOT EXISTS idx_knowledge_documents_project_id ON knowledge_documents(project_id);

ALTER TABLE tax_law_chunks ADD COLUMN IF NOT EXISTS project_id UUID REFERENCES projects(id);
CREATE INDEX IF NOT EXISTS idx_tax_law_chunks_project_id ON tax_law_chunks(project_id);

-- 3. Update search_tax_law RPC
CREATE OR REPLACE FUNCTION search_tax_law(
    query_embedding vector(1536),
    match_threshold float,
    match_count int,
    filter_project_id uuid DEFAULT NULL
)
RETURNS TABLE (
    id uuid,
    document_id uuid,
    chunk_text text,
    citation text,
    section_title text,
    law_category text,
    tax_types text[],
    source_type text,
    similarity float
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        t.id,
        t.document_id,
        t.chunk_text,
        t.citation,
        t.section_title,
        t.law_category,
        t.tax_types,
        t.source_type,
        1 - (t.embedding <=> query_embedding) AS similarity
    FROM tax_law_chunks t
    WHERE 1 - (t.embedding <=> query_embedding) > match_threshold
      AND (filter_project_id IS NULL OR t.project_id = filter_project_id)
    ORDER BY t.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;

Then run this script to insert the default project and backfill data.

Usage: python migrate_projects.py
"""

from db import get_supabase

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

DEFAULT_PROJECT_ID = "00000000-0000-0000-0000-000000000001"


def main():
    sb = get_supabase()

    # 1. Insert default project
    print("Creating default WA Tax Law project...")
    try:
        sb.table("projects").upsert({
            "id": DEFAULT_PROJECT_ID,
            "name": "WA Tax Law",
            "description": "Washington State tax law knowledge base with RCW, WAC, ETA, WTD, and more.",
            "system_prompt": SYSTEM_PROMPT,
            "chat_model": "gpt-5.2",
            "embedding_model": "text-embedding-3-small",
        }).execute()
        print("  Done.")
    except Exception as e:
        print(f"  Error: {e}")
        return

    # 2. Backfill knowledge_documents
    print("Backfilling knowledge_documents...")
    try:
        sb.table("knowledge_documents").update(
            {"project_id": DEFAULT_PROJECT_ID}
        ).is_("project_id", "null").execute()
        print("  Done.")
    except Exception as e:
        print(f"  Error: {e}")

    # 3. Backfill tax_law_chunks in batches
    print("Backfilling tax_law_chunks (batched)...")
    total = 0
    while True:
        r = sb.table("tax_law_chunks").select("id").is_(
            "project_id", "null"
        ).limit(500).execute()
        rows = r.data or []
        if not rows:
            break
        ids = [row["id"] for row in rows]
        # Update in smaller sub-batches
        for i in range(0, len(ids), 50):
            batch_ids = ids[i:i+50]
            for cid in batch_ids:
                sb.table("tax_law_chunks").update(
                    {"project_id": DEFAULT_PROJECT_ID}
                ).eq("id", cid).execute()
            total += len(batch_ids)
            print(f"  Updated {total} chunks...", flush=True)

    print(f"Backfill complete. Total chunks updated: {total}")
    print("Migration complete!")


if __name__ == "__main__":
    main()

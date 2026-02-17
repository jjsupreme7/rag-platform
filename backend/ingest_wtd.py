"""
Download and ingest Washington Tax Decisions (WTDs) from dor.wa.gov.

Sources:
  1. Zip archives (Volumes 19–41) from taxpedia / legacy downloads
  2. Individual PDFs (Volumes 42–44+) from dor.wa.gov/washington-tax-decisions

Usage:
  python ingest_wtd.py [--project-id <uuid>] [--dry-run]
"""

import argparse
import io
import os
import re
import sys
import tempfile
import time
import zipfile
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

# Add backend to path so we can import ingest module
sys.path.insert(0, os.path.dirname(__file__))
from ingest import ingest_pdf
from db import get_supabase

# ---------------------------------------------------------------------------
# Volume → URL mapping
# ---------------------------------------------------------------------------

# Vol 41 lives at a different path than 1-40
ZIP_URLS: dict[int, str] = {}
for v in range(19, 41):
    # Volumes 20, 22-24 use lowercase prefix but curl follows redirects anyway
    ZIP_URLS[v] = f"https://dor.wa.gov/legacy/downloads/Taxpedia_Data/WTDvol{v}.zip"
ZIP_URLS[41] = "https://dor.wa.gov/sites/default/files/2022-06/WTDvol41.zip"

RECENT_WTD_URL = "https://dor.wa.gov/washington-tax-decisions"

PROJECT_ID_DEFAULT = "00000000-0000-0000-0000-000000000001"


def already_ingested(filename: str, project_id: str) -> bool:
    """Check if a WTD PDF has already been ingested by source_file name."""
    sb = get_supabase()
    r = (
        sb.table("knowledge_documents")
        .select("id")
        .eq("source_file", filename)
        .eq("project_id", project_id)
        .limit(1)
        .execute()
    )
    return len(r.data or []) > 0


def ingest_single_wtd(
    pdf_bytes: bytes,
    filename: str,
    volume: int,
    project_id: str,
    dry_run: bool = False,
) -> dict:
    """Ingest one WTD PDF."""
    if dry_run:
        return {"status": "dry_run", "title": filename, "chunks_created": 0}

    # Extract citation from filename  e.g. "25WTD1.pdf" → "25 WTD 1"
    match = re.match(r"(\d+)\s*WTD\s*(\d+)", filename, re.IGNORECASE)
    citation = f"{match.group(1)} WTD {match.group(2)}" if match else filename.replace(".pdf", "")

    result = ingest_pdf(
        pdf_bytes,
        filename,
        category="Tax Determination (WTD)",
        citation=citation,
        project_id=project_id,
    )

    # Tag as upload (from zip) — the ingest_pdf defaults to "upload" source_type
    return result


def download_and_ingest_zip(volume: int, project_id: str, dry_run: bool = False) -> dict:
    """Download a zip archive and ingest all PDFs inside."""
    url = ZIP_URLS.get(volume)
    if not url:
        return {"volume": volume, "error": "No URL for this volume"}

    print(f"\n{'='*60}")
    print(f"Volume {volume}: Downloading from {url}")

    try:
        r = httpx.get(url, follow_redirects=True, timeout=120)
        r.raise_for_status()
    except Exception as e:
        print(f"  ERROR downloading: {e}")
        return {"volume": volume, "error": str(e), "ingested": 0, "skipped": 0}

    stats = {"volume": volume, "ingested": 0, "skipped": 0, "errors": 0, "total_chunks": 0}

    try:
        zf = zipfile.ZipFile(io.BytesIO(r.content))
    except zipfile.BadZipFile:
        # Some volumes have a nested zip
        print(f"  Nested zip detected, extracting inner archive...")
        with tempfile.TemporaryDirectory() as td:
            inner_path = Path(td) / "inner.zip"
            inner_path.write_bytes(r.content)
            try:
                outer = zipfile.ZipFile(inner_path)
                inner_names = [n for n in outer.namelist() if n.endswith(".zip")]
                if inner_names:
                    outer.extract(inner_names[0], td)
                    zf = zipfile.ZipFile(Path(td) / inner_names[0])
                else:
                    zf = outer
            except Exception as e:
                print(f"  ERROR: Cannot read zip: {e}")
                return {"volume": volume, "error": str(e), "ingested": 0, "skipped": 0}

    pdf_names = [n for n in zf.namelist() if n.lower().endswith(".pdf")]
    print(f"  Found {len(pdf_names)} PDFs in archive")

    for pdf_name in pdf_names:
        # Normalize filename (strip directory prefix)
        base_name = os.path.basename(pdf_name)
        if not base_name:
            continue

        # Check if already ingested
        if already_ingested(base_name, project_id):
            stats["skipped"] += 1
            continue

        try:
            pdf_bytes = zf.read(pdf_name)
            result = ingest_single_wtd(pdf_bytes, base_name, volume, project_id, dry_run)
            if result.get("status") == "success":
                stats["ingested"] += 1
                stats["total_chunks"] += result.get("chunks_created", 0)
                print(f"    Ingested: {base_name} ({result.get('chunks_created', 0)} chunks)")
            elif result.get("status") == "dry_run":
                stats["ingested"] += 1
                print(f"    [DRY RUN] Would ingest: {base_name}")
            else:
                stats["errors"] += 1
                print(f"    ERROR: {base_name} — {result.get('error', 'unknown')}")
        except Exception as e:
            stats["errors"] += 1
            print(f"    ERROR reading {base_name}: {e}")

        # Small delay to avoid hammering the embedding API
        if not dry_run:
            time.sleep(0.1)

    print(f"  Volume {volume} done: {stats['ingested']} ingested, {stats['skipped']} skipped, {stats['errors']} errors")
    return stats


def scrape_recent_wtds(project_id: str, dry_run: bool = False) -> dict:
    """Scrape individual WTD PDFs from dor.wa.gov/washington-tax-decisions."""
    print(f"\n{'='*60}")
    print(f"Scraping recent WTDs from {RECENT_WTD_URL}")

    stats = {"source": "recent_page", "ingested": 0, "skipped": 0, "errors": 0, "total_chunks": 0}

    try:
        r = httpx.get(RECENT_WTD_URL, follow_redirects=True, timeout=60)
        r.raise_for_status()
    except Exception as e:
        print(f"  ERROR fetching page: {e}")
        return {**stats, "error": str(e)}

    soup = BeautifulSoup(r.text, "html.parser")

    # Find all PDF links that look like WTD documents
    pdf_links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.lower().endswith(".pdf") and "wtd" in href.lower():
            if not href.startswith("http"):
                href = f"https://dor.wa.gov{href}"
            pdf_links.append((href, a.get_text(strip=True)))

    print(f"  Found {len(pdf_links)} WTD PDF links")

    # Only ingest volumes 42+ (we get 19-41 from zips)
    filtered = []
    for href, text in pdf_links:
        # Check if it's volume 42, 43, 44, etc.
        vol_match = re.search(r"(\d+)\s*WTD", os.path.basename(href), re.IGNORECASE)
        if vol_match:
            vol_num = int(vol_match.group(1))
            if vol_num >= 42:
                filtered.append((href, text, vol_num))

    print(f"  {len(filtered)} PDFs are volume 42+ (not in zip archives)")

    for href, text, vol_num in filtered:
        base_name = os.path.basename(href).split("?")[0]

        if already_ingested(base_name, project_id):
            stats["skipped"] += 1
            continue

        try:
            pdf_r = httpx.get(href, follow_redirects=True, timeout=60)
            pdf_r.raise_for_status()
            pdf_bytes = pdf_r.content

            result = ingest_single_wtd(pdf_bytes, base_name, vol_num, project_id, dry_run)
            if result.get("status") == "success":
                stats["ingested"] += 1
                stats["total_chunks"] += result.get("chunks_created", 0)
                print(f"    Ingested: {base_name} ({result.get('chunks_created', 0)} chunks)")
            elif result.get("status") == "dry_run":
                stats["ingested"] += 1
                print(f"    [DRY RUN] Would ingest: {base_name}")
            else:
                stats["errors"] += 1
                print(f"    ERROR: {base_name} — {result.get('error', 'unknown')}")
        except Exception as e:
            stats["errors"] += 1
            print(f"    ERROR downloading {base_name}: {e}")

        if not dry_run:
            time.sleep(0.2)

    print(f"  Recent WTDs done: {stats['ingested']} ingested, {stats['skipped']} skipped, {stats['errors']} errors")
    return stats


def main():
    parser = argparse.ArgumentParser(description="Ingest WTDs from dor.wa.gov")
    parser.add_argument("--project-id", default=PROJECT_ID_DEFAULT, help="Project UUID")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be ingested without actually doing it")
    parser.add_argument("--volumes", default="19-41", help="Volume range to ingest, e.g. '19-41' or '25-30'")
    args = parser.parse_args()

    # Parse volume range
    vol_match = re.match(r"(\d+)-(\d+)", args.volumes)
    if vol_match:
        vol_start, vol_end = int(vol_match.group(1)), int(vol_match.group(2))
    else:
        vol_start = vol_end = int(args.volumes)

    print(f"WTD Ingestion Script")
    print(f"  Project ID: {args.project_id}")
    print(f"  Volumes: {vol_start}–{vol_end} (from zip archives)")
    print(f"  Recent WTDs: Vol 42+ (from website)")
    print(f"  Dry run: {args.dry_run}")
    print()

    all_stats = []

    # 1. Process zip archives
    for vol in range(vol_start, vol_end + 1):
        if vol in ZIP_URLS:
            stats = download_and_ingest_zip(vol, args.project_id, args.dry_run)
            all_stats.append(stats)

    # 2. Process recent individual WTDs (vol 42+)
    recent_stats = scrape_recent_wtds(args.project_id, args.dry_run)
    all_stats.append(recent_stats)

    # Summary
    total_ingested = sum(s.get("ingested", 0) for s in all_stats)
    total_skipped = sum(s.get("skipped", 0) for s in all_stats)
    total_errors = sum(s.get("errors", 0) for s in all_stats)
    total_chunks = sum(s.get("total_chunks", 0) for s in all_stats)

    print(f"\n{'='*60}")
    print(f"SUMMARY")
    print(f"  Total ingested: {total_ingested}")
    print(f"  Total skipped (already exists): {total_skipped}")
    print(f"  Total errors: {total_errors}")
    print(f"  Total chunks created: {total_chunks}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()

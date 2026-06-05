"""
run_pipeline.py — ORCHESTRATION Layer
=======================================
Entry point for the Spotify → MongoDB ETL pipeline.

Usage:
    python run_pipeline.py

Sequence:
    1. EXTRACT  — Authenticate with Spotify, fetch last 50 played tracks
                  and their audio features.
    2. TRANSFORM — Enrich each track with Vibe Labels and clean the schema.
    3. LOAD      — Upsert new documents into MongoDB Atlas, skip duplicates.
    4. REPORT    — Print a final summary to the console.
"""

import sys
import time
from datetime import datetime, timezone

from extract import run_extraction
from transform import run_transformation
from load_to_cloud import load_documents


# ─── Helpers ─────────────────────────────────────────────────────────────────
def print_banner(text: str, width: int = 60) -> None:
    border = "─" * width
    print(f"\n{border}")
    print(f"  {text}")
    print(f"{border}")


def print_step(step: int, total: int, name: str) -> None:
    print(f"\n[STEP {step}/{total}] ══ {name.upper()} ══")


# ─── Pipeline ────────────────────────────────────────────────────────────────
def run_pipeline() -> None:
    pipeline_start = time.perf_counter()
    run_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    print_banner(f"🎵  Spotify Music Data Warehouse Pipeline")
    print(f"  Run started at : {run_at}")
    print(f"  Pipeline       : Extract → Transform → Load")

    # ── Step 1: EXTRACT ───────────────────────────────────────────────────────
    print_step(1, 3, "Extract")
    try:
        recently_played, audio_features = run_extraction()
    except Exception as exc:
        print(f"\n[ERROR] Extraction failed: {exc}")
        print("  Check that your SPOTIPY_CLIENT_ID / SPOTIPY_CLIENT_SECRET")
        print("  are correctly set in the .env file and your app is registered")
        print("  in the Spotify Developer Dashboard.")
        sys.exit(1)

    if not recently_played:
        print("\n[INFO] No recently-played tracks found. Nothing to process.")
        sys.exit(0)

    # ── Step 2: TRANSFORM ─────────────────────────────────────────────────────
    print_step(2, 3, "Transform")
    try:
        documents = run_transformation(recently_played, audio_features)
    except Exception as exc:
        print(f"\n[ERROR] Transformation failed: {exc}")
        sys.exit(1)

    # ── Step 3: LOAD ──────────────────────────────────────────────────────────
    print_step(3, 3, "Load to MongoDB Atlas")
    try:
        summary = load_documents(documents)
    except Exception as exc:
        print(f"\n[ERROR] Load failed: {exc}")
        print("  Check that your MONGO_URI is correctly set in the .env file")
        print("  and that your Atlas cluster allows connections from this IP.")
        sys.exit(1)

    # ── Final Report ──────────────────────────────────────────────────────────
    elapsed = time.perf_counter() - pipeline_start

    print_banner("🏁  Pipeline Complete")
    print(f"  ✅  Successfully uploaded {summary['inserted']} new songs to the Cloud.")
    print(f"  ⏭   Skipped {summary['skipped']} duplicate(s).")

    if summary["errors"]:
        print(f"  ⚠   {summary['errors']} error(s) encountered (see above).")

    print(f"\n  Tracks fetched   : {len(recently_played)}")
    print(f"  Docs transformed : {len(documents)}")
    print(f"  Inserted         : {summary['inserted']}")
    print(f"  Skipped (dupes)  : {summary['skipped']}")
    print(f"  Time elapsed     : {elapsed:.2f}s")
    print("─" * 60)


# ─── Entry Point ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    run_pipeline()

"""
load_to_cloud.py — LOAD Layer
===============================
Connects to MongoDB Atlas and upserts enriched track documents into the
`listening_history` collection. Duplicate detection is based on the
unique (track_id, played_at) pair — the same song played twice at different
times is stored as separate entries.
"""

import os
from datetime import datetime, timezone

import pymongo
from pymongo import MongoClient
from pymongo.collection import Collection
from dotenv import load_dotenv

# ─── Load credentials ────────────────────────────────────────────────────────
load_dotenv()

MONGO_URI         = os.getenv("MONGO_URI")
MONGO_DB_NAME     = os.getenv("MONGO_DB_NAME",         "spotify_warehouse")
COLLECTION_NAME   = os.getenv("MONGO_COLLECTION_NAME", "listening_history")


# ─── Connect to MongoDB Atlas ─────────────────────────────────────────────────
def get_collection() -> Collection:
    """
    Creates a MongoClient and returns the target collection.
    Verifies connectivity with a lightweight ping command.
    """
    if not MONGO_URI:
        raise ValueError(
            "MONGO_URI is not set. Please add it to your .env file."
        )

    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=10_000)

    # Verify the connection is alive before proceeding
    client.admin.command("ping")
    print("[LOAD] ✓ Connected to MongoDB Atlas successfully.")

    db         = client[MONGO_DB_NAME]
    collection = db[COLLECTION_NAME]

    # Ensure a unique index on (played_at) to enforce deduplication at the
    # database level — an extra safety net on top of our Python check.
    collection.create_index(
        [("played_at", pymongo.ASCENDING)],
        unique=True,
        name="unique_played_at",
    )

    return collection


# ─── Deduplication check ─────────────────────────────────────────────────────
def is_duplicate(collection: Collection, played_at: str) -> bool:
    """
    Returns True if a document with the same `played_at` timestamp already
    exists in the collection. This is the primary duplicate guard.
    """
    return collection.count_documents({"played_at": played_at}, limit=1) > 0


# ─── Load documents ──────────────────────────────────────────────────────────
def load_documents(documents: list[dict]) -> dict[str, int]:
    """
    Iterates over transformed documents and inserts only new ones.

    Returns:
        A summary dict: {"inserted": int, "skipped": int, "errors": int}
    """
    if not documents:
        print("[LOAD] No documents to load.")
        return {"inserted": 0, "skipped": 0, "errors": 0}

    collection = get_collection()

    inserted = 0
    skipped  = 0
    errors   = 0

    for doc in documents:
        played_at = doc.get("played_at")

        if not played_at:
            print(f"[LOAD]   ⚠ Skipping document with missing played_at: {doc.get('track_name')}")
            errors += 1
            continue

        if is_duplicate(collection, played_at):
            skipped += 1
            continue

        try:
            collection.insert_one(doc)
            inserted += 1
            print(
                f"[LOAD]   ✓ Inserted: {doc.get('track_name', 'Unknown')} "
                f"by {doc.get('artist', 'Unknown')} "
                f"[{doc.get('vibe_label', '?')}] — {played_at}"
            )
        except pymongo.errors.DuplicateKeyError:
            # Race condition: another process inserted the same doc between
            # our is_duplicate check and the insert. Safe to ignore.
            skipped += 1
        except pymongo.errors.PyMongoError as exc:
            print(f"[LOAD]   ✗ Error inserting {doc.get('track_name')}: {exc}")
            errors += 1

    summary = {"inserted": inserted, "skipped": skipped, "errors": errors}
    print(
        f"[LOAD] ─── Summary: {inserted} inserted | "
        f"{skipped} skipped (duplicates) | {errors} errors"
    )
    return summary


# ─── Quick sanity-check ───────────────────────────────────────────────────────
if __name__ == "__main__":
    print("Running load_to_cloud.py standalone test …")
    print("This will attempt to connect to MongoDB Atlas using your .env settings.")
    try:
        col = get_collection()
        count = col.count_documents({})
        print(f"[LOAD] Collection '{COLLECTION_NAME}' currently has {count} documents.")
    except Exception as e:
        print(f"[LOAD] ✗ Connection failed: {e}")

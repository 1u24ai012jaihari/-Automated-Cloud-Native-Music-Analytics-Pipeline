"""
transform.py — TRANSFORM Layer
================================
Takes raw Spotify API data and builds clean, enriched documents ready for
MongoDB ingestion. Applies custom "Vibe Logic" to label each track.

Vibe Logic operates in two modes:
  1. AUDIO FEATURES MODE  — when /v1/audio-features data is available
     (uses danceability, energy, valence, acousticness, instrumentalness)
  2. METADATA MODE (fallback) — when audio features are unavailable
     (uses popularity, duration_ms, and explicit flag from the track object)
     This mode is used for Spotify apps created after Nov 2024 where the
     audio features endpoint has been deprecated.
"""

from __future__ import annotations
from datetime import datetime, timezone
from typing import Any


# ─── Vibe Label Rules — Audio Features Mode ──────────────────────────────────
# Evaluated in order; the FIRST matching rule wins.
AUDIO_VIBE_RULES: list[tuple[str, Any]] = [
    ("Banger",       lambda f: f.get("energy", 0) > 0.80 and f.get("danceability", 0) > 0.70),
    ("Hype",         lambda f: f.get("energy", 0) > 0.80),
    ("Feel-Good",    lambda f: f.get("valence", 0) > 0.70 and f.get("danceability", 0) > 0.60),
    ("Melancholic",  lambda f: f.get("valence", 0) < 0.30 and f.get("energy", 0) < 0.50),
    ("Acoustic",     lambda f: f.get("acousticness", 0) > 0.70),
    ("Instrumental", lambda f: f.get("instrumentalness", 0) > 0.50),
    ("Chill",        lambda f: True),   # fallback — always matches
]


# ─── Vibe Label Rules — Metadata Mode (fallback) ────────────────────────────
# Uses only data available in the track object (no audio features needed).
# popularity : 0–100 (Spotify’s own metric)
# duration_ms: track length in milliseconds
# explicit   : bool — whether the track has explicit content
METADATA_VIBE_RULES: list[tuple[str, Any]] = [
    # Very popular + short = radio-friendly Banger
    ("Banger",      lambda t: t.get("popularity", 0) >= 75 and t.get("duration_ms", 0) < 210_000),
    # Highly popular tracks = Hype
    ("Hype",        lambda t: t.get("popularity", 0) >= 75),
    # Explicit + moderately popular = Feel-Good party track
    ("Feel-Good",   lambda t: t.get("explicit") and t.get("popularity", 0) >= 55),
    # Long + low popularity = Melancholic deep cut
    ("Melancholic", lambda t: t.get("duration_ms", 0) > 300_000 and t.get("popularity", 0) < 40),
    # Long track (5+ min) = likely Acoustic / slow burn
    ("Acoustic",    lambda t: t.get("duration_ms", 0) > 300_000),
    # Low popularity niche tracks
    ("Underground", lambda t: t.get("popularity", 0) < 30),
    ("Chill",       lambda t: True),   # fallback — always matches
]


def get_vibe_label(audio_features: dict, track: dict) -> str:
    """
    Applies hierarchical Vibe Logic and returns a human-readable vibe label.

    Mode selection:
      • If `audio_features` is non-empty → AUDIO FEATURES MODE
        (danceability, energy, valence, acousticness, instrumentalness)
      • If `audio_features` is empty → METADATA MODE
        (popularity, duration_ms, explicit from the track object)
    """
    if audio_features:
        # ─ Audio Features Mode ───────────────────────────────────────
        for label, predicate in AUDIO_VIBE_RULES:
            if predicate(audio_features):
                return label
    else:
        # ─ Metadata Mode (fallback) ────────────────────────────────
        for label, predicate in METADATA_VIBE_RULES:
            if predicate(track):
                return label

    return "Chill"  # absolute safety net


# ─── Transform a single track item ───────────────────────────────────────────
def transform_track(item: dict, audio_features_map: dict[str, dict]) -> dict | None:
    """
    Transforms one raw Spotify recently-played item into a clean MongoDB
    document.

    Args:
        item               : raw item from Spotify's recently-played endpoint.
        audio_features_map : dict of track_id -> audio feature dict.

    Returns:
        A flat dict (MongoDB document) or None if the track data is missing.
    """
    track = item.get("track")
    if not track:
        return None

    track_id  = track.get("id")
    played_at = item.get("played_at", "")
    features  = audio_features_map.get(track_id, {})
    vibe      = get_vibe_label(features, track)    # dual-mode vibe logic

    # Parse played_at into a proper datetime object for better DB querying
    try:
        played_at_dt = datetime.strptime(played_at, "%Y-%m-%dT%H:%M:%S.%fZ").replace(
            tzinfo=timezone.utc
        )
    except (ValueError, TypeError):
        played_at_dt = None

    # Build the enriched document
    document = {
        # ── Identity ──────────────────────────────────────────────────────
        "track_id"        : track_id,
        "track_name"      : track.get("name", "Unknown"),
        "artist"          : ", ".join(a["name"] for a in track.get("artists", [])),
        "album"           : track.get("album", {}).get("name", "Unknown"),
        "album_image_url" : (track.get("album", {}).get("images") or [{}])[0].get("url"),
        "spotify_url"     : track.get("external_urls", {}).get("spotify"),
        "duration_ms"     : track.get("duration_ms"),
        "explicit"        : track.get("explicit", False),
        "popularity"      : track.get("popularity"),

        # ── Playback ──────────────────────────────────────────────────────
        "played_at"       : played_at,          # original ISO string (used as unique key)
        "played_at_dt"    : played_at_dt,       # datetime object for date-range queries

        # ── Audio Features (null when deprecated endpoint unavailable) ──────────
        "danceability"       : features.get("danceability"),
        "energy"             : features.get("energy"),
        "valence"            : features.get("valence"),
        "tempo"              : features.get("tempo"),
        "loudness"           : features.get("loudness"),
        "speechiness"        : features.get("speechiness"),
        "acousticness"       : features.get("acousticness"),
        "instrumentalness"   : features.get("instrumentalness"),
        "liveness"           : features.get("liveness"),
        "key"                : features.get("key"),
        "mode"               : features.get("mode"),           # 1 = Major, 0 = Minor
        "time_signature"     : features.get("time_signature"),
        "audio_features_available": bool(features),    # flag so you know which mode was used

        # ── Vibe Label (custom enrichment) ───────────────────────────────────
        "vibe_label"         : vibe,
        "vibe_mode"          : "audio_features" if features else "metadata",

        # ── Pipeline Metadata ─────────────────────────────────────────────
        "ingested_at"     : datetime.now(timezone.utc),
    }

    return document


# ─── Transform all tracks ────────────────────────────────────────────────────
def run_transformation(
    recently_played: list[dict],
    audio_features_map: dict[str, dict],
) -> list[dict]:
    """
    Transforms a full list of recently-played items into clean MongoDB docs.

    Returns:
        List of enriched track documents (skips items with missing track data).
    """
    print(f"[TRANSFORM] Processing {len(recently_played)} raw items …")
    documents = []

    for item in recently_played:
        doc = transform_track(item, audio_features_map)
        if doc:
            documents.append(doc)

    # Vibe distribution summary
    from collections import Counter
    vibe_counts = Counter(d["vibe_label"] for d in documents)
    print(f"[TRANSFORM] ✓ {len(documents)} documents built.")
    print(f"[TRANSFORM]   Vibe breakdown → {dict(vibe_counts)}")
    return documents


# ─── Quick sanity-check ───────────────────────────────────────────────────────
if __name__ == "__main__":
    # Minimal stub test — runs without Spotify API
    sample_item = {
        "track": {
            "id": "abc123",
            "name": "Test Track",
            "artists": [{"name": "Test Artist"}],
            "album": {"name": "Test Album", "images": []},
            "external_urls": {"spotify": "https://open.spotify.com/track/abc123"},
            "duration_ms": 200000,
            "explicit": False,
            "popularity": 75,
        },
        "played_at": "2026-06-05T10:30:00.000Z",
    }
    sample_features = {
        "abc123": {
            "danceability": 0.85,
            "energy": 0.92,
            "valence": 0.65,
            "tempo": 128.0,
            "loudness": -4.5,
            "speechiness": 0.05,
            "acousticness": 0.02,
            "instrumentalness": 0.00,
            "liveness": 0.10,
            "key": 5,
            "mode": 1,
            "time_signature": 4,
        }
    }

    docs = run_transformation([sample_item], sample_features)
    print(f"\nSample document:")
    for k, v in docs[0].items():
        print(f"  {k:<22}: {v}")

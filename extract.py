"""
extract.py — EXTRACT Layer
==========================
Connects to the Spotify API using SpotifyOAuth and fetches the last 50
recently-played tracks.

NOTE: Spotify deprecated the /v1/audio-features endpoint for new developer
apps (post Nov 2024). This module attempts to fetch audio features and
gracefully falls back to an empty dict if the endpoint is unavailable.
Vibe Labels are then derived from track metadata in transform.py.
"""

import os
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from dotenv import load_dotenv

# ─── Load credentials from .env ─────────────────────────────────────────────
load_dotenv()

CLIENT_ID     = os.getenv("SPOTIPY_CLIENT_ID")
CLIENT_SECRET = os.getenv("SPOTIPY_CLIENT_SECRET")
REDIRECT_URI  = os.getenv("SPOTIPY_REDIRECT_URI", "http://localhost:8888/callback")

# ─── Authenticate ────────────────────────────────────────────────────────────
def get_spotify_client() -> spotipy.Spotify:
    """
    Returns an authenticated Spotipy client using the OAuth2 Authorization
    Code Flow. On first run, a browser window will open asking you to log in
    and authorise the app. The token is then cached in `.cache` for reuse.
    """
    auth_manager = SpotifyOAuth(
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        redirect_uri=REDIRECT_URI,
        scope="user-read-recently-played",
        open_browser=True,
    )
    return spotipy.Spotify(auth_manager=auth_manager)


# ─── Fetch recently played tracks ────────────────────────────────────────────
def fetch_recently_played(sp: spotipy.Spotify, limit: int = 50) -> list[dict]:
    """
    Fetches the last `limit` (max 50) recently played tracks.

    Returns a list of raw item dicts from the Spotify API, each containing:
      - track      : full track object
      - played_at  : ISO-8601 timestamp string (UTC)
      - context    : playback context (playlist, album, etc.)
    """
    print(f"[EXTRACT] Fetching the last {limit} recently-played tracks …")
    results = sp.current_user_recently_played(limit=limit)
    items   = results.get("items", [])
    print(f"[EXTRACT] ✓ Retrieved {len(items)} tracks from Spotify.")
    return items


# ─── Fetch audio features for a batch of tracks ──────────────────────────────
def fetch_audio_features(sp: spotipy.Spotify, track_ids: list[str]) -> dict[str, dict]:
    """
    Attempts to fetch audio features for the given track IDs.

    ⚠ Spotify deprecated /v1/audio-features for apps created after Nov 2024.
    If the endpoint returns an error (403 / SpotifyException), this function
    logs a warning and returns an empty dict so the pipeline continues.
    Vibe Labels will fall back to metadata-based logic in transform.py.
    """
    print(f"[EXTRACT] Attempting to fetch audio features for {len(track_ids)} tracks …")
    try:
        features_list = sp.audio_features(track_ids)  # returns list | None per track
        if features_list is None:
            raise ValueError("API returned None for audio features.")

        features_map: dict[str, dict] = {}
        for feat in features_list:
            if feat:
                features_map[feat["id"]] = feat

        print(f"[EXTRACT] ✓ Audio features received for {len(features_map)} tracks.")
        return features_map

    except Exception as exc:
        print(
            f"[EXTRACT] ⚠ Audio features unavailable (Spotify deprecated this endpoint "
            f"for new apps): {exc}"
        )
        print("[EXTRACT]   Vibe Labels will be derived from track metadata instead.")
        return {}


# ─── Convenience: run extraction end-to-end ──────────────────────────────────
def run_extraction() -> tuple[list[dict], dict[str, dict]]:
    """
    Orchestrates the full extraction step.
    Returns:
        recently_played : list of raw Spotify recently-played items
        audio_features  : dict mapping track_id -> audio feature dict
                          (may be empty if the endpoint is deprecated for this app)
    """
    sp              = get_spotify_client()
    recently_played = fetch_recently_played(sp)
    track_ids       = [item["track"]["id"] for item in recently_played if item.get("track")]
    audio_features  = fetch_audio_features(sp, track_ids)
    return recently_played, audio_features


# ─── Quick sanity-check ───────────────────────────────────────────────────────
if __name__ == "__main__":
    items, features = run_extraction()
    print("\n--- Sample track ---")
    if items:
        t = items[0]["track"]
        print(f"  Name       : {t['name']}")
        print(f"  Artist     : {t['artists'][0]['name']}")
        print(f"  Played At  : {items[0]['played_at']}")
        print(f"  Popularity : {t.get('popularity', 'N/A')}")
        print(f"  Explicit   : {t.get('explicit', 'N/A')}")
        af = features.get(t["id"], {})
        print(f"  Audio Feat : {'available' if af else 'unavailable (deprecated endpoint)'}")

# 🎵 Spotify Cloud Data Warehouse

> A personal music analytics pipeline that extracts your Spotify listening history,
> enriches it with custom **Vibe Labels**, and loads it into a cloud-hosted MongoDB Atlas
> warehouse — ready for real-time dashboarding with MongoDB Charts.

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        DATA FLOW OVERVIEW                           │
└─────────────────────────────────────────────────────────────────────┘

  ┌─────────────────┐        ┌──────────────────────────────────────┐
  │   Spotify API   │        │         Python ETL Pipeline          │
  │  (Source Data)  │        │                                      │
  │                 │        │  ┌──────────┐   ┌────────────────┐   │
  │  • Recently     │──────► │  │ EXTRACT  │──►│  TRANSFORM     │   │
  │    Played Tracks│        │  │          │   │                │   │
  │  • Track Meta   │        │  │extract.py│   │  transform.py  │   │
  │    (popularity, │        │  │          │   │                │   │
  │    duration,    │        │  │SpotifyOAu│   │• Vibe Labels   │   │
  │    explicit)    │        │  │th OAuth2 │   │• Schema clean  │   │
  │                 │        │  │          │   │• Type casting  │   │
  │  Endpoint:      │        │  │last 50   │   │• Dedup key     │   │
  │  /recently-     │        │  │tracks    │   │  (played_at)   │   │
  │  played         │        │  └──────────┘   └───────┬────────┘   │
  └─────────────────┘        │                         │            │
                             │                  ┌──────▼────────┐   │
                             │                  │     LOAD      │   │
                             │                  │               │   │
                             │                  │load_to_cloud  │   │
                             │                  │    .py        │   │
                             │                  │               │   │
                             │                  │• Dupe check   │   │
                             │                  │• Upsert logic │   │
                             │                  └──────┬────────┘   │
                             └─────────────────────────│────────────┘
                                                       │
                                                       ▼
                             ┌─────────────────────────────────────┐
                             │       MongoDB Atlas (Cloud)          │
                             │         M0 Free Sandbox              │
                             │                                      │
                             │  Database: spotify_warehouse         │
                             │  Collection: listening_history       │
                             │                                      │
                             │  Document schema:                    │
                             │  {                                   │
                             │    track_id, track_name, artist,     │
                             │    album, played_at (unique key),    │
                             │    popularity, duration_ms,          │
                             │    explicit, vibe_label,             │
                             │    vibe_mode, ingested_at, ...       │
                             │  }                                   │
                             └──────────────────┬──────────────────┘
                                                │
                                                ▼
                             ┌─────────────────────────────────────┐
                             │         MongoDB Charts               │
                             │       (Analytics Layer)              │
                             │                                      │
                             │  📊 Vibe breakdown pie chart         │
                             │  📈 Listening activity over time     │
                             │  🎤 Top artists bar chart            │
                             │  🕐 Peak listening hours heatmap     │
                             └─────────────────────────────────────┘
```

---

## ⚡ Tech Stack

### Core Pipeline
- **Python 3.13** — pipeline runtime; clean type-annotated, modular scripts
- **Spotipy 2.26** — Spotify Web API wrapper; handles OAuth2 token refresh automatically
- **PyMongo 4.6** — async-ready MongoDB driver; supports bulk ops and index management
- **python-dotenv** — zero-config secret management; `.env` file never touches git

### Cloud Infrastructure
- **MongoDB Atlas M0 Sandbox** — fully managed cloud database; free tier, 512MB, global clusters
- **MongoDB Charts** — native BI layer built into Atlas; zero-ETL dashboards directly on live data

### Security
- **SpotifyOAuth2** — authorization code flow; scoped permissions (`user-read-recently-played` only)
- **Unique DB Index** — `played_at` field enforced unique at the database engine level — duplicate prevention that survives race conditions

---

## 🧠 Vibe Label Engine

Every track is automatically classified into a human-readable label:

| Vibe | Logic (Metadata Mode) |
|---|---|
| 🔥 **Banger** | Popularity ≥ 75 AND duration < 3:30 |
| ⚡ **Hype** | Popularity ≥ 75 |
| 😊 **Feel-Good** | Explicit + Popularity ≥ 55 |
| 😔 **Melancholic** | Duration > 5min AND Popularity < 40 |
| 🎸 **Acoustic** | Duration > 5min |
| 🕳️ **Underground** | Popularity < 30 |
| 😌 **Chill** | Everything else (fallback) |

> **Dual-mode design:** If Spotify's `/v1/audio-features` endpoint is available,
> Vibe Labels use precise audio signals (energy, danceability, valence). For new
> Spotify apps where this endpoint is deprecated (post-Nov 2024), the engine
> automatically falls back to track metadata — the pipeline never breaks.

---

## 📁 Project Structure

```
Personal Music Warehouse Engine/
│
├── extract.py          # EXTRACT — Spotify OAuth + recently played fetch
├── transform.py        # TRANSFORM — schema normalisation + Vibe Labels
├── load_to_cloud.py    # LOAD — MongoDB Atlas upsert with deduplication
├── run_pipeline.py     # ORCHESTRATOR — runs E→T→L, prints summary report
│
├── .env                # 🔑 Secrets (never committed — see .gitignore)
├── .gitignore          # Ignores .env, .cache, __pycache__, venv
└── requirements.txt    # Pinned dependencies
```

---

## 🚀 Quick Start

### 1. Clone & Install

```bash
git clone <your-repo-url>
cd "Personal Music Warehouse Engine"
pip install -r requirements.txt
```

### 2. Configure Credentials

Edit `.env` and fill in your keys:

```env
SPOTIPY_CLIENT_ID=your_spotify_client_id
SPOTIPY_CLIENT_SECRET=your_spotify_client_secret
SPOTIPY_REDIRECT_URI=http://127.0.0.1:8888/callback
MONGO_URI=mongodb+srv://<user>:<password>@<cluster>.mongodb.net/?appName=Spotify
```

> **Spotify Setup:** Register your app at [developer.spotify.com/dashboard](https://developer.spotify.com/dashboard).
> Add `http://127.0.0.1:8888/callback` as a Redirect URI under **Settings → Save**.

### 3. Run the Pipeline

```bash
python run_pipeline.py
```

On first run, a browser window opens for Spotify login. Token is cached in `.cache` — subsequent runs are fully automated.

**Expected output:**
```
────────────────────────────────────────────────────────────
  🎵  Spotify Music Data Warehouse Pipeline
────────────────────────────────────────────────────────────
  Run started at : 2026-06-05 15:05:01 UTC
  Pipeline       : Extract → Transform → Load

[STEP 1/3] ══ EXTRACT ══
[EXTRACT] Fetching the last 50 recently-played tracks …
[EXTRACT] ✓ Retrieved 50 tracks from Spotify.

[STEP 2/3] ══ TRANSFORM ══
[TRANSFORM] ✓ 50 documents built.
[TRANSFORM]   Vibe breakdown → {'Underground': 32, 'Feel-Good': 11, 'Chill': 7}

[STEP 3/3] ══ LOAD TO MONGODB ATLAS ══
[LOAD] ✓ Connected to MongoDB Atlas successfully.
[LOAD] ─── Summary: 49 inserted | 1 skipped (duplicates) | 0 errors

────────────────────────────────────────────────────────────
  🏁  Pipeline Complete
────────────────────────────────────────────────────────────
  ✅  Successfully uploaded 49 new songs to the Cloud.
  ⏭   Skipped 1 duplicate(s).
  Time elapsed : 10.71s
────────────────────────────────────────────────────────────
```

---

## 📈 Why This Architecture Scales

- **Stateless ETL scripts** — each run is idempotent; safe to schedule via cron/Task Scheduler without side effects
- **Cloud-native storage** — Atlas handles replication, backups, and indexing automatically; zero ops overhead
- **Unique index deduplication** — database-enforced constraint means you can run the pipeline 100× a day; no duplicate data ever lands
- **Schema-flexible documents** — MongoDB's document model lets you add new fields (e.g., audio features if re-enabled) without migrations
- **Separation of concerns** — Extract / Transform / Load are isolated modules; swap Spotify for Last.fm or the DB for BigQuery by changing one file
- **Free tier ceiling** — M0 Sandbox holds ~500K+ listening history documents before you'd need to upgrade; years of daily syncs

---

## 🔮 Potential Enhancements

- [ ] **Scheduling** — wrap `run_pipeline.py` in Windows Task Scheduler or GitHub Actions for daily auto-sync
- [ ] **MongoDB Charts Dashboard** — connect Atlas Charts to `listening_history` for live Vibe pie charts and top-artist leaderboards
- [ ] **Expanded scope** — add `user-top-artists`, `user-top-tracks`, and `playlist-read-private` scopes
- [ ] **Export to CSV/Pandas** — add an `analyze.py` module for local EDA and matplotlib visualisations
- [ ] **Alerting** — notify via email/Telegram when a new Vibe trend is detected week-over-week

---

## 📄 License

MIT — free to use, modify, and distribute.

---

*Built with Python 🐍 · Powered by Spotify API 🎵 · Stored on MongoDB Atlas ☁️*

# Transcriber

**Русская версия** → [README.md](README.md)

Local web app for transcribing audio and video: upload a file, a folder, or a YouTube link — get text with timecodes and speaker labels, plus export to TXT / SRT / VTT / JSON / DOCX. Everything runs on one machine, without cloud APIs: models run on the local CPU via WhisperX.

Built as a personal tool for transcribing courses, podcasts, and interviews. Published as a portfolio piece.

![Home page](docs/screenshots/home.png)

---

## Contents

- [Features](#features)
- [Tech stack](#tech-stack)
- [Architecture decisions](#architecture-decisions)
- [Quick start](#quick-start)
- [Screenshots](#screenshots)
- [What I learned along the way](#what-i-learned-along-the-way)
- [Future improvements](#future-improvements)

---

## Features

**Four input methods:**
- Single file upload via browser (with drag-and-drop)
- YouTube link (downloaded via yt-dlp)
- Single file on disk by absolute path
- Recursive folder scan — batch processing while you do something else

**Video format support** — `.mp4`, `.avi`, `.mkv`, `.mov`, `.webm`, and more. Audio is extracted by ffmpeg on the fly and cached.

**Quality vs speed trade-off.** The UI lets you pick between Whisper models: `base`, `small`, `medium`, `large-v3-turbo`. The choice is saved in the browser. Server-side, an LRU cache keeps the 2 most recently used models in memory — avoids wasting RAM while also avoiding reload delays when you switch.

**Speaker diarization** via pyannote — splits audio by speaker (`SPEAKER_00`, `SPEAKER_01`, ...).

**Optional translation** of speech to English (Whisper's built-in capability).

**Export to 7 formats:** TXT, SRT, VTT, JSON, DOCX in three styles (plain text / with timecodes / with timecodes and speakers). Batch processing saves files next to the source: `lecture_01.mp4` → `lecture_01.timecoded.docx`.

**Synchronized player.** On the task page, an HTML5 player plays the original audio. Segments highlight in real time as playback advances, and clicking a segment seeks the player to that position. The server uses HTTP Range responses so seeking is instant.

**Persistence and search.** Tasks live in SQLite and survive server restarts. Full-text search over transcript content via FTS5 finds all transcripts containing a word or phrase.

**Deduplication.** Reprocessing the same folder skips files already completed. A "force reprocess" checkbox overrides this.

---

## Tech stack

**Backend** — Python 3.11, FastAPI, WhisperX (faster-whisper + pyannote for diarization), yt-dlp, ffmpeg, python-docx. Storage is SQLite with an FTS5 index. No ORM — raw SQL through the `sqlite3` module.

**Frontend** — React 18, Vite, React Router. No state manager (useState/useEffect cover everything). No UI framework — custom CSS using variables, with light/dark theme support.

**Infrastructure** — `uvicorn` (backend) and `vite dev` (frontend) running in two terminals. Vite proxies `/api/*` → `localhost:8000` to bypass CORS.

**Development hardware** — Intel i5-2500 (Sandy Bridge, no AVX2), 16 GB RAM, no supported GPU. Everything runs on CPU. On this hardware: `small` ≈ 1× RT (real-time), `medium` ≈ 0.3× RT, `large-v3-turbo` ≈ 0.3× RT.

---

## Architecture decisions

A short log of the important choices I made while building this.

**Background tasks via FastAPI's `BackgroundTasks`, not Celery.** For a single-user tool, Celery + Redis is overkill. `BackgroundTasks` runs a function in a thread after the HTTP response returns. Downside: tasks don't survive a server restart — if `processing` when you hit `Ctrl+C`, it stays `processing` forever. Acceptable for personal use (worst case: re-run the file manually).

**Whisper on CPU with `int8` quantization.** On Sandy Bridge without AVX2, this is the only way to get acceptable speed. `float16` on CPU is slower. GPU isn't available (old card not supported by current PyTorch).

**LRU cache of 2 models.** Keeping all 4 models in RAM wastes ~10 GB. Reloading on every switch adds 30-60 seconds of lag. Compromise: the 2 most recent models stay in memory. Switching between `small` and `medium` keeps both; adding a third evicts the least recent.

**`audio_cache/` for extracted video audio tracks.** Course video files are often GB-sized, with 90% being unused video. ffmpeg extracts audio to compact m4a at 16 kHz mono 128 kbps. Cache key is a hash of absolute path + mtime + size, so the cache invalidates when the source changes.

**Upload files stored as `<task_id>.<ext>`.** Originally filenames were random uuids created separately from task_id, so the link between task and file was lost. Refactored so task_id is also the filename: `_locate_source` finds files via glob without additional schema fields.

**Custom Range handler for audio streaming.** FastAPI/Starlette's `FileResponse` in my version doesn't always return `Accept-Ranges: bytes`, which prevents HTML5 player seeking. Wrote my own `StreamingResponse`-based implementation: parses `Range: bytes=START-END`, responds with `206 Partial Content` and the requested chunk. Works reliably.

**Raw SQL instead of ORM.** One `tasks` table, one `segments`, one `exported_files`, plus an FTS5 virtual table for search. Schema is simple; migrations live in one file versioned by `PRAGMA user_version`. SQLAlchemy would be overkill and would hide SQL behind an abstraction.

**FTS5 with triggers for synchronization.** Segments live in the main table; the FTS index is a separate `virtual table` with `content='segments'`. Triggers `AFTER INSERT/UPDATE/DELETE` keep the index in sync. `MATCH` queries are instant even with hundreds of tasks.

**Deduplication by `local_source_path`.** The `tasks` table has a partial index `WHERE local_source_path IS NOT NULL`. Before creating a LOCAL task, we check whether a completed task already exists for that path — if yes, we return its task_id. A `force=true` flag bypasses the check.

**Vite proxy instead of CORS config.** During development, the frontend runs on `localhost:5173` and the backend on `localhost:8000` — cross-origin requests. Instead of configuring CORS headers, I set up a Vite proxy in `vite.config.js`: `/api/*` → `http://localhost:8000`. From the frontend's perspective, it's all same-origin.

---

## Quick start

### Requirements

- Python 3.11
- Node.js 22 LTS
- ffmpeg in PATH (check: `ffmpeg -version`)
- HuggingFace token for diarization (optional) — accept conditions on `pyannote/speaker-diarization-community-1` and `pyannote/segmentation-3.0`

### Install

```bash
git clone https://github.com/ea-vershinin/transcriber.git
cd transcriber

# Backend
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1       # Windows PowerShell
# source .venv/bin/activate      # Linux/Mac
pip install -r requirements.txt

# Frontend
cd ../frontend
npm install
```

### Configure

Create `backend/.env`:

```env
WHISPER_MODEL=small
HF_TOKEN=hf_xxxxxxxxxxxxxxxxxx   # optional, for diarization
```

### Run

Terminal 1 — backend:
```bash
cd backend
.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload
```

Terminal 2 — frontend:
```bash
cd frontend
npm run dev
```

Open http://localhost:5173/

API docs (Swagger) — http://localhost:8000/docs

---

## Screenshots

### Home page — forms and history
![Home](docs/screenshots/home.png)

### Folder picker — built-in filesystem browser
![Folder picker](docs/screenshots/folder-picker.png)

### Task page — metadata, player, segments, export
![Task page](docs/screenshots/task-page.png)

### Full-text search over transcripts
![Search](docs/screenshots/search.png)

---

## What I learned along the way

This was my first web application. Some of the things I had to figure out:

**ML stack on an old CPU under Windows.** WhisperX on PyPI was stale — you need the main branch from GitHub. Version compatibility across `faster-whisper` / `pyannote` / `torch` had to be hand-picked: one version broke the API, another required GPU features. The pinned list of versions lives in `requirements.lock.txt`.

**Async vs sync in FastAPI + BackgroundTasks.** Whisper is a synchronous CPU-bound process. Running it via `async def` doesn't make sense — it blocks the event loop. I used a sync function in `BackgroundTasks`, which automatically goes to a threadpool.

**HTTP Range requests.** Figuring out why the HTML5 player couldn't seek required DevTools Network — I was looking for 206 status codes. When I didn't see any, it became clear the server wasn't sending `Accept-Ranges`.

**React hooks with frequent re-renders.** `setInterval` inside `useEffect` with proper cleanup is a common pattern, but it's easy to leak. A `cancelled` flag is mandatory.

**SQLite FTS5 with the `UNICODE61` tokenizer.** Without it, search over Cyrillic text doesn't work — the default tokenizer only handles ASCII. Plus you need triggers `AFTER INSERT/UPDATE/DELETE` so the FTS index doesn't lag behind the main table.

**Cyrillic paths in JSON.** `"C:\Users\keen\Видео\..."` breaks JSON parsing at `\U` and `\k`. The fix is forward slashes or doubled backslashes. POST forms now mention this explicitly.

**Separate connection per thread for SQLite.** When testing the database, I noticed tasks weren't appearing in the `.db` — the WAL journal holds the changes while a connection is active. In a multi-threaded FastAPI setup, I use `sqlite3.connect()` through `threading.local()` so each thread gets its own connection.

---

## Future improvements

- **Transcription cache for YouTube URLs** (currently dedup works only for local files)
- **Summarization** via Claude/OpenAI API — a "TL;DR" button on the task page
- **EN→RU / other translation pairs** via NLLB or a cloud API
- **Electron/Tauri wrapper** for native file dialogs (currently a custom filesystem browser in a modal)
- **Scheduled cleanup** of old audio caches
- **Celery + Redis** if multi-user mode becomes needed

---

## License

This project is distributed under the MIT License — see the [LICENSE](LICENSE) file.

---

## Contact

Author — [@ea-vershinin](https://github.com/ea-vershinin)

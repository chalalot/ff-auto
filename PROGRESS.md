# ff-auto: Migration Progress

**Date**: March 24, 2026
**Status**: Phase 1 (FastAPI Backend) — Steps 1–5 complete ✅

---

## What Was Built

### Step 1 — Project Scaffold

Created the full `backend/` directory tree with `__init__.py` at every level:

```
backend/
├── api/           ← FastAPI routers
├── models/        ← Pydantic schemas
├── services/      ← Business logic (extracted from Streamlit apps)
├── database/      ← SQLite storage adapters
├── third_parties/ ← ComfyUI, Kling, GCS clients
├── workflows/     ← CrewAI workflows
├── tools/         ← Vision, audio tools
├── utils/         ← Constants, image/video/audio helpers
└── scripts/       ← Celery beat scripts
```

---

### Step 2 — `backend/config.py`

Cleaned copy of `src/config.py` with the Streamlit secrets block removed (lines 101–125 in the original).

Key change: added `PROMPTS_DIR` env var (was previously hard-coded relative to `__file__`).

All settings remain env-var-driven:

| Var | Default |
|-----|---------|
| `INPUT_DIR` | `Sorted` |
| `PROCESSED_DIR` | `processed` |
| `OUTPUT_DIR` | `results` |
| `PROMPTS_DIR` | `prompts` |
| `COMFYUI_API_URL` | `https://cloud.comfy.org/api` |
| `CELERY_BROKER_URL` | `redis://localhost:6379/0` |

---

### Step 3 — Celery, Tasks, Scripts

| File | Change from source |
|------|--------------------|
| `backend/celery_app.py` | Updated task include: `backend.tasks` |
| `backend/tasks.py` | All imports updated to `backend.*`, task names updated to `backend.tasks.*` |
| `backend/scripts/populate_generated_images.py` | Adjusted imports, removed `sys.path` hacks |

Celery Beat schedule unchanged — still runs `populate_generated_images` every 60s.

---

### Step 4 — Database, Utils (copied as-is)

These modules had zero framework deps — copied directly:

- `backend/database/image_logs_storage.py`
- `backend/database/video_logs_storage.py`
- `backend/database/runs_posts_storage.py`
- `backend/database/db_utils.py`
- `backend/utils/constants.py`
- `backend/utils/image_filters.py`
- `backend/utils/audio_utils.py`

**`backend/utils/video_utils.py`** — `StreamlitLogger` class renamed to `ProgressLogger` (generic callback-based). No functional change.

---

### Step 5 — Third Parties, Workflows, Tools

Copied from `src/` and batch-updated all imports:

| Old import | New import |
|-----------|------------|
| `from src.config import GlobalConfig` | `from backend.config import GlobalConfig` |
| `from src.utils.image_filters import` | `from backend.utils.image_filters import` |
| `from src.third_parties.` | `from backend.third_parties.` |
| `from src.workflows.` | `from backend.workflows.` |
| `from src.tools.` | `from backend.tools.` |
| `from utils.constants import` | `from backend.utils.constants import` |

`backend/workflows/config_manager.py` — `PROMPTS_DIR` path now reads from env var with fallback:
```python
self.PROMPTS_DIR = os.path.abspath(
    os.getenv("PROMPTS_DIR", os.path.join(os.path.dirname(__file__), '..', '..', 'prompts'))
)
```

---

### `backend/main.py` — FastAPI App Entry Point

```python
uvicorn backend.main:app --reload --port 8000
```

- CORS configured via `CORS_ORIGINS` env var (default: `localhost:3000,localhost:5173`)
- 4 routers registered under `/api/`
- `/health` endpoint for Docker healthchecks

---

### Pydantic Models

| File | Key models |
|------|-----------|
| `backend/models/workspace.py` | `ProcessImageRequest`, `TaskStatusResponse`, `InputImage`, `ExecutionRecord` |
| `backend/models/gallery.py` | `GalleryResponse`, `ApproveRequest`, `ImageMetadata`, `DownloadZipRequest` |
| `backend/models/config.py` | `PersonaSummary`, `PersonaUpdateRequest`, `LastUsedConfig`, `PresetConfig` |

---

### Services Layer

Business logic extracted from the Streamlit apps:

#### `ImageProcessingService` (from `1_workspace_app.py`)

| Method | Replaces |
|--------|---------|
| `scan_input_directory()` | `get_sorted_images(INPUT_DIR)` |
| `prepare_image(src_path)` | inline rename+copy logic → `ref_{timestamp}_{uuid}.png` |
| `dispatch_processing(...)` | `process_image_task.delay(...)` call |
| `dispatch_batch(paths, ...)` | loop over `dispatch_processing` |
| `get_task_status(task_id)` | `AsyncResult(task_id)` polling |
| `get_input_image_thumbnail(fn)` | `get_thumbnail_path()` |

#### `GalleryService` (from `2_gallery_app.py`)

| Method | Replaces |
|--------|---------|
| `list_images(status, page, per_page)` | `load_gallery_data()` + `get_paginated_items()` |
| `get_thumbnail(filename, status)` | `get_thumbnail_path()` |
| `extract_metadata(filename, status)` | `extract_metadata_from_image()` |
| `approve_images(filenames, rename_map)` | `move_image()` loop to `approved/` |
| `disapprove_images(filenames)` | `move_image()` loop to `disapproved/` |
| `undo_action(filenames, from_status)` | `move_image()` back to `results/` |
| `get_stats()` | `get_all_stats()` |
| `build_zip(filenames, date)` | `st.download_button` ZIP logic |
| `lookup_execution(filename)` | `fetch_execution_record()` |
| `load_notes()` / `save_note()` | daily notes JSON read/write |

#### `ConfigService` (from `WorkflowConfigManager` + `1_workspace_app.py`)

| Method | Replaces |
|--------|---------|
| `list_personas()` | `config_manager.get_personas()` |
| `get_persona(name)` | `config_manager.get_persona_config()` |
| `update_persona(name, data)` | `config_manager.update_persona_config()` |
| `list_presets()` / `get_preset()` / `save_preset()` / `delete_preset()` | inline preset CRUD in workspace_app |
| `get_last_used()` / `save_last_used()` | `load_preset("_last_used")` / `save_preset("_last_used", ...)` |

---

### API Endpoints (35 total)

#### Workspace `/api/workspace/`

| Method | Path | Description |
|--------|------|-------------|
| GET | `/input-images` | List images in INPUT_DIR |
| GET | `/input-images/{filename}/thumbnail` | Serve cached thumbnail |
| POST | `/process` | Dispatch single image Celery task |
| POST | `/process-batch` | Dispatch multiple images |
| GET | `/task/{task_id}/status` | Poll Celery task state |
| GET | `/executions` | Recent execution history (DB) |
| WS | `/ws/tasks` | Real-time task progress |

#### Gallery `/api/gallery/`

| Method | Path | Description |
|--------|------|-------------|
| GET | `/images` | Paginated listing (`?status=pending\|approved\|disapproved`) |
| GET | `/images/{filename}/thumbnail` | 512×512 JPEG thumbnail |
| GET | `/images/{filename}/metadata` | ComfyUI PNG metadata (seed, prompt) |
| GET | `/download/{filename}` | Full-resolution download |
| POST | `/approve` | Move to `approved/`, optional rename |
| POST | `/disapprove` | Move to `disapproved/` |
| POST | `/undo` | Move back to pending |
| GET | `/stats` | Daily approval statistics |
| POST | `/download-zip` | ZIP download by filenames or date |
| GET/PUT | `/notes` | Read/write `daily_notes.json` |

#### Config `/api/config/`

| Method | Path | Description |
|--------|------|-------------|
| GET | `/personas` | List all personas |
| GET/PUT | `/personas/{name}` | Read/update persona config files |
| GET | `/persona-types` | List types from `persona_types.txt` |
| GET | `/presets` | List saved presets |
| GET/POST/DELETE | `/presets/{name}` | CRUD for a preset |
| GET/PUT | `/presets/_last_used` | Sticky last-used config |
| GET | `/workflow-types` | `["turbo", "standard"]` |
| GET | `/vision-models` | Available vision model options |
| GET | `/clip-model-types` | CLIP model type list |
| GET | `/lora-options` | LoRA filename options |

#### Monitor `/api/monitor/`

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | CPU, RAM, disk via psutil |
| GET | `/processes` | Running Python/Celery processes |
| GET | `/db-stats` | SQLite row counts by status |
| GET | `/filesystem` | Image file counts per directory |

---

## Test Suite

**85 tests, all passing (~1s, no external services required)**

```
tests/
├── conftest.py                         # shared fixtures, temp dir patching
├── test_api_health.py                  # 3 tests  — smoke tests
├── test_api_config.py                  # 14 tests — personas, presets, last-used
├── test_api_gallery.py                 # 17 tests — listing, thumbnail, approve/reject, ZIP, notes
├── test_api_workspace.py               # 13 tests — input scan, dispatch (mocked), task status
├── test_api_monitor.py                 # 4 tests  — health, filesystem, db, processes
├── test_services_gallery.py            # 17 tests — GalleryService unit tests
└── test_services_image_processing.py   # 17 tests — ImageProcessingService unit tests
```

All tests run against temporary directories — no real `Sorted/`, `processed/`, or `results/` are touched.
Celery dispatch is mocked — no Redis connection needed.

**Run:**
```bash
cd /Users/trung/Work/ff-auto
python -m pytest tests/ -v
```

---

## Start the Server

```bash
cd /Users/trung/Work/ff-auto
uvicorn backend.main:app --reload --port 8000
```

Interactive API docs: `http://localhost:8000/docs`

---

## What's NOT Done Yet (Next Steps)

| Step | Description |
|------|-------------|
| Step 6 | Scaffold React frontend (Vite + TypeScript + Tailwind + shadcn/ui) |
| Step 7 | Build Workspace page components |
| Step 8 | Build Gallery page components |
| Step 9 | Docker setup (Dockerfile.backend, Dockerfile.frontend, docker-compose.yml) |
| Step 10 | Data migration & cutover from old Streamlit stack |
| Phase 4 | Video App (deferred) |
| Phase 5 | Monitor App (deferred) |

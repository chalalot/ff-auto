# Architecture: Database Schema & Async Patterns

> Generated 2026-05-11

---

## TL;DR — Executive Summary

**What this system does:** A React + FastAPI app that takes input images, generates AI variations via ComfyUI, curates results in a gallery, and trains custom LoRA models on RunPod.

**Three moving parts:**

```mermaid
flowchart LR
    A["① Browser\nReact SPA\npolls every 1–5s"] -->|REST| B["② FastAPI\n:8000\norchestrates jobs"]
    B -->|dispatch| C["③ Celery Workers\ndo the heavy work\n2 queues: image / video"]
    C -->|calls| D["External APIs\nComfyUI · Kling · CrewAI"]
    C -->|writes| E["SQLite ×3 tables\nimage · video · runpod\n+ PostgreSQL ×2 tables\nruns · posts"]
    B -->|task state| F["Redis\nbroker + registry"]
```

**Two main async flows:**

**Flow A — Image generation:**

1. User clicks **Process** → FastAPI enqueues a Celery task, returns a `task_id`
2. React polls `/task/{id}/status` every **1 second** until done
3. Celery worker calls **CrewAI** to write N prompts from the image, sends each to **ComfyUI**
4. A second Celery task retries every **5 s** (up to 1 hr) waiting for ComfyUI, then downloads the result
5. Result path saved to **SQLite** → Gallery reads it

**Flow B — LoRA training:**

1. User uploads images → React calls caption-export → Celery runs **CrewAI** on each image, returns `.txt` prompts
2. User downloads ZIP (images + captions) or uploads directly to **Google Drive**
3. User submits LoRA training job to **RunPod** → job ID saved to SQLite
4. React polls `/runpod/status/{job_id}` — **FastAPI calls RunPod API on-demand** (no background task), updates DB
5. When complete, user triggers upload of the `.safetensors` to **Hugging Face Hub**

**Data stored:** 3 SQLite tables (`image_logs`, `video_logs`, `runpod_jobs`) + 2 PostgreSQL tables (`runs`, `posts` for campaign content). No ORM, no migrations framework — raw SQL.

**No magic:** polling everywhere — no event bus, no persistent WebSocket in practice. Simple and debuggable.

---

## 1. Database Schema

### SQLite — 3 tables (image/video pipeline)

```mermaid
erDiagram
    image_logs {
        INTEGER id PK
        TEXT execution_id "NOT NULL — ComfyUI prompt ID"
        TEXT prompt "NOT NULL — CrewAI generated prompt"
        TEXT persona "nullable"
        TEXT image_ref_path "nullable — input image"
        TEXT result_image_path "nullable — output image"
        TEXT status "DEFAULT pending | completed | failed"
        TIMESTAMP created_at "DEFAULT CURRENT_TIMESTAMP"
    }

    video_logs {
        INTEGER id PK
        TEXT batch_id "nullable — groups related videos"
        TEXT execution_id "NOT NULL — Kling prompt ID"
        TEXT prompt "NOT NULL"
        TEXT source_image_path "nullable"
        TEXT video_output_path "nullable"
        TEXT status "DEFAULT pending | completed | failed"
        TIMESTAMP created_at "DEFAULT CURRENT_TIMESTAMP"
        TEXT filename_id "nullable"
    }

    runpod_jobs {
        INTEGER id PK
        TEXT job_id "NOT NULL UNIQUE — RunPod job ID"
        TEXT endpoint_id "NOT NULL"
        TEXT lora_name "NOT NULL"
        TEXT submitted_at "NOT NULL — ISO timestamp"
        TEXT job_input "NOT NULL — JSON blob"
        TEXT status "nullable — QUEUED | IN_PROGRESS | COMPLETED"
        TEXT output "nullable — JSON blob"
        TEXT updated_at "nullable"
    }
```

### PostgreSQL — 2 tables (campaign content)

```mermaid
erDiagram
    runs {
        TEXT id PK
        TEXT persona_name "NOT NULL"
        TEXT trend_text "NOT NULL"
        INTEGER num_posts "NOT NULL"
        JSONB adapted_idea "nullable — creative concept"
        JSONB trend_profile "nullable — trend analysis"
        JSONB metadata "nullable"
        BIGINT created_at "unix epoch"
        BIGINT updated_at "unix epoch"
    }

    posts {
        TEXT id PK
        TEXT run_id FK "→ runs.id CASCADE DELETE"
        INTEGER post_index "position in campaign"
        TEXT caption "nullable"
        TEXT[] hashtags "nullable"
        TEXT cta "nullable"
        TEXT image_url "nullable — GCS/HTTP public URL"
        TEXT image_prompt "nullable"
        TEXT positive_prompt "nullable"
        TEXT negative_prompt "nullable"
        JSONB visual_plan "nullable"
        JSONB content_seed "nullable"
        JSONB versions "nullable — version history array"
        INTEGER current_version "nullable"
        JSONB metadata "nullable"
        BIGINT created_at "unix epoch"
        BIGINT updated_at "unix epoch"
    }

    runs ||--o{ posts : "has many"
```

---

## 2. Celery Task Architecture

Two named queues, each with concurrency 2.

```mermaid
flowchart TD
    subgraph Queues["Celery Queues (Redis broker)"]
        IQ[image queue\nconcurrency 2]
        VQ[video queue\nconcurrency 2]
    end

    process_image_task --> IQ
    download_execution_task --> IQ
    caption_export_task --> IQ

    generate_storyboard_task --> VQ
    merge_videos_task --> VQ
    analyze_music_task --> VQ
    poll_comfy_video_task --> VQ
```

### Flow A — Image generation (end-to-end)

```mermaid
sequenceDiagram
    participant React
    participant FastAPI
    participant Redis
    participant CeleryW as Celery Worker (image)
    participant CrewAI
    participant ComfyUI
    participant SQLite

    React->>FastAPI: POST /api/workspace/process
    FastAPI->>CeleryW: process_image_task.apply_async()
    FastAPI->>Redis: sadd(active_tasks, task_id) + setex(task_meta:id, 1hr)
    FastAPI-->>React: {task_id}

    loop Poll every 1 s
        React->>FastAPI: GET /api/workspace/task/{id}/status
        FastAPI->>Redis: AsyncResult(task_id) from result backend
        FastAPI-->>React: {state, progress, status_message}
    end

    CeleryW->>CrewAI: generate N prompts from image (GPT-4o vision)
    loop For each prompt
        CeleryW->>ComfyUI: queue image generation → execution_id
        CeleryW->>SQLite: image_logs.log_execution(status=pending)
        CeleryW->>CeleryW: download_execution_task.apply_async(countdown=5s)
    end

    loop Retry every 5 s (max ~1 hr)
        CeleryW->>ComfyUI: check_status(execution_id)
        alt completed
            CeleryW->>ComfyUI: download_image_by_path()
            CeleryW->>SQLite: image_logs.update_result_path(status=completed)
        else failed
            CeleryW->>SQLite: image_logs.mark_as_failed()
        else pending / queued
            CeleryW->>CeleryW: retry(countdown=5s)
        end
    end
```

### Flow B — Caption export + LoRA training

> **Key:** RunPod polling is NOT a Celery task. The frontend calls FastAPI, which hits the RunPod API on-demand and updates the DB. No background worker involved.

```mermaid
sequenceDiagram
    participant React
    participant FastAPI
    participant CeleryW as Celery Worker (image)
    participant CrewAI
    participant GDrive as Google Drive
    participant RunPod
    participant HF as Hugging Face Hub
    participant SQLite

    Note over React,FastAPI: Step 1 — Upload & caption images
    React->>FastAPI: POST /caption-export/upload (or /gdrive/fetch)
    FastAPI->>GDrive: list + download images (if from Drive)
    FastAPI-->>React: {entries: [{stem, path}]}

    React->>FastAPI: POST /caption-export/start
    FastAPI->>CeleryW: caption_export_task.apply_async()
    FastAPI->>Redis: register task_id in active_tasks
    FastAPI-->>React: {task_id}

    loop Poll every 1 s
        React->>FastAPI: GET /task/{id}/status
        FastAPI-->>React: {state, progress "x/N images"}
    end

    CeleryW->>CrewAI: process() for each image (sequential)
    CeleryW-->>React: SUCCESS {results: [{stem, prompt}]}

    Note over React,FastAPI: Step 2 — Download or upload to Drive
    alt Download locally
        React->>FastAPI: GET /caption-export/{task_id}/download
        FastAPI-->>React: ZIP stream (images + .txt prompts)
    else Upload to Google Drive
        React->>FastAPI: POST /caption-export/gdrive/upload-zip
        FastAPI->>GDrive: upload ZIP, make_file_public()
        FastAPI-->>React: {public_url}
    end

    Note over React,FastAPI: Step 3 — Submit LoRA training to RunPod
    React->>FastAPI: POST /caption-export/runpod/submit
    FastAPI->>RunPod: POST /v2/{endpoint_id}/run
    FastAPI->>SQLite: runpod_jobs.insert(status=QUEUED)
    FastAPI-->>React: {job_id}

    Note over React,FastAPI: Step 4 — Poll RunPod status (on-demand, no background task)
    loop Frontend polls manually
        React->>FastAPI: GET /caption-export/runpod/status/{job_id}
        FastAPI->>RunPod: GET /v2/{endpoint_id}/status/{job_id}
        FastAPI->>SQLite: runpod_jobs.update_status()
        FastAPI-->>React: {status, output}
    end

    Note over React,FastAPI: Step 5 — Upload trained LoRA to Hugging Face
    React->>FastAPI: POST /caption-export/runpod/upload-to-hf
    FastAPI->>RunPod: download .safetensors from signed S3 URL
    FastAPI->>HF: HfApi.upload_file() → repo_id/filename
    FastAPI-->>React: {url: huggingface.co/...}
```

### Video pipeline

```mermaid
sequenceDiagram
    participant React
    participant FastAPI
    participant CeleryW as Celery Worker (video)
    participant Kling
    participant ComfyUI
    participant SQLite

    React->>FastAPI: POST /api/video/generate
    FastAPI->>Kling: submit video job
    FastAPI->>SQLite: video_logs.log_execution(status=pending)
    FastAPI->>CeleryW: poll_comfy_video_task.apply_async()
    FastAPI-->>React: {task_id, batch_id}

    loop Frontend polls every 5 s
        React->>FastAPI: GET /api/video/status/{id}
        FastAPI-->>React: {status, video_output_path}
    end

    loop Retry every 10 s (max 120 retries = 20 min)
        CeleryW->>ComfyUI: check_video_status(prompt_id)
        alt completed
            CeleryW->>ComfyUI: download_file_by_path()
            CeleryW->>SQLite: video_logs.update_result(status=completed)
        else failed
            CeleryW->>SQLite: video_logs.update_result(status=failed)
        else pending
            CeleryW->>CeleryW: retry(countdown=10s)
        end
    end
```

---

## 3. Redis Usage

```mermaid
flowchart LR
    subgraph Redis
        B1["Celery broker\n(CELERY_BROKER_URL)"]
        B2["Celery result backend\n(CELERY_RESULT_BACKEND)"]
        B3["active_tasks set\nttl 1 hr\ntask registry"]
        B4["task_meta:{id} keys\nttl 1 hr\ntask metadata JSON"]
    end

    FastAPI -->|send_task| B1
    FastAPI -->|sadd / setex| B3
    FastAPI -->|setex meta| B4
    CeleryWorker -->|update_state| B2
    FastAPI -->|AsyncResult| B2
    FastAPI -->|smembers| B3
```

---

## 4. Frontend Async Patterns

All server state via **React Query**. WebSocket endpoint exists but is request-reply only (client sends `{task_id}`, server responds once — not a push stream).

```mermaid
flowchart TD
    subgraph Hooks["React Query Hooks"]
        UT["useTaskProgress\nrefetch every 1s\nstops on SUCCESS / FAILURE"]
        UA["useActiveTasks\nrefetch every 5s\nalways on"]
        UV["useVideoStatus\nrefetch every 5s\nstops on completed / failed"]
        UG["useGalleryImages\nno auto-refetch\nmanual invalidate on approve/reject"]
    end

    UT -->|GET /workspace/task/:id/status| API
    UA -->|GET /workspace/active-tasks| API
    UV -->|GET /video/status/:id| API
    UG -->|GET /gallery/images| API

    subgraph API["FastAPI"]
        API -->|AsyncResult| Redis
        API -->|smembers| Redis
        API -->|SELECT| SQLite
        API -->|GET status on-demand| RunPod
    end
```

---

## 5. Full System Overview

```mermaid
flowchart TB
    Browser["React SPA\n(Vite + React Query)"]

    subgraph Backend["FastAPI :8000"]
        WS["/api/workspace\n(image gen + caption export + LoRA)"]
        VID["/api/video"]
        GAL["/api/gallery"]
        MON["/api/monitor"]
    end

    subgraph Workers["Celery Workers"]
        IW["image worker\nconcurrency 2\nprocess_image · download · caption_export"]
        VW["video worker\nconcurrency 2\nstoryboard · merge · music · poll_video"]
    end

    subgraph Storage
        SQLite["SQLite\nimage_logs · video_logs · runpod_jobs"]
        PG["PostgreSQL\nruns · posts"]
        Redis["Redis\nbroker + results + task registry"]
        FS["Filesystem\nSorted/ processed/ results/ prompts/"]
    end

    subgraph External
        ComfyUI["ComfyUI Cloud\n(image + video gen)"]
        Kling["Kling API\n(video gen)"]
        RunPod["RunPod API\n(LoRA training)\npolled on-demand by FastAPI"]
        CrewAI["CrewAI + GPT-4o\n(vision / prompt writing)"]
        GDrive["Google Drive\n(fetch input / upload ZIP)"]
        HF["Hugging Face Hub\n(store trained LoRAs)"]
    end

    Browser -->|HTTP REST + polling| Backend
    Backend -->|dispatch| Redis
    Redis -->|consume| Workers
    Workers -->|read/write| SQLite
    Workers -->|read/write| FS
    Workers -->|API calls| ComfyUI
    Workers -->|API calls| Kling
    Workers -->|API calls| CrewAI
    Backend -->|query| SQLite
    Backend -->|query| PG
    Backend -->|scan| Redis
    Backend -->|serve files| FS
    Backend -->|on-demand status check| RunPod
    Backend -->|fetch/upload| GDrive
    Backend -->|upload model| HF
```

---

## 6. Polling Timeouts Reference

| Service | Poll Interval | Max Duration | Mechanism |
|---------|-------------|--------------|-----------|
| ComfyUI image | 5 s | ~1 hour | Celery retry (worker-side) |
| ComfyUI/Kling video | 10 s | 20 min (120 retries) | Celery retry (worker-side) |
| RunPod LoRA training | on-demand | no timeout | FastAPI → RunPod API (frontend-triggered) |
| Frontend — image/caption task | 1 s | until SUCCESS/FAILURE | React Query refetchInterval |
| Frontend — video task | 5 s | until completed/failed | React Query refetchInterval |
| Frontend — active tasks list | 5 s | always | React Query refetchInterval |

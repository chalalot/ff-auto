# Video App Migration Plan

**Source:** `ff-automation-captioning/apps/pages/3_video_app.py` (Streamlit)
**Target:** `ff-auto/` (FastAPI + React)
**Date:** April 1, 2026

---

## Current State

The target project (`ff-auto`) already has the **image pipeline** fully migrated — Workspace, Gallery, Monitor, and Prompts pages are working with FastAPI backend and React frontend. The backend also already contains the core video **library code** (copied but not yet wired up):

| Module | Status |
|--------|--------|
| `backend/workflows/video_storyboard_workflow.py` | Copied, not integrated |
| `backend/workflows/music_analysis_workflow.py` | Copied, not integrated |
| `backend/third_parties/kling_client.py` | Copied, not integrated |
| `backend/database/video_logs_storage.py` | Copied, not integrated |
| `backend/utils/video_utils.py` | Copied, not integrated |
| `backend/tools/audio_tool.py` | Copied, not integrated |

**What's missing:** All the API routes, Celery tasks, services, frontend pages, and components to actually expose the video functionality.

---

## Migration Phases

### Phase 1: Video Backend API & Tasks

Create the FastAPI routes and Celery tasks that wrap the existing backend modules.

#### 1.1 — Create Pydantic Models (`backend/models/video.py`)

Define request/response schemas:

- `VideoGenerateRequest` — source image path, prompt (optional), kling settings (model, mode, duration, aspect ratio, CFG scale, audio settings)
- `VideoGenerateResponse` — task_id, batch_id, status
- `VideoBatchRequest` — list of images with per-image variation counts, shared kling settings
- `VideoStatusResponse` — status, progress percentage, video URL (if complete)
- `VideoItem` — id, filename, source_image, prompt, status, created_at, duration, thumbnail URL
- `VideoListResponse` — items list with pagination
- `VideoMergeRequest` — list of video filenames, transition type (crossfade/fade_to_black/simple_cut), transition duration
- `VideoMergeResponse` — task_id, output filename
- `MusicAnalysisRequest` — audio file path or GCS URL
- `MusicAnalysisResponse` — vibe, lyrics, analysis text
- `StoryboardRequest` — image paths, vision model, persona
- `StoryboardResponse` — generated prompts per image

#### 1.2 — Create Video Service (`backend/services/video.py`)

Extract business logic from the Streamlit app into a clean service class:

- `VideoService.generate_storyboard(images, vision_model, persona)` — runs `VideoStoryboardWorkflow` to produce prompts from images
- `VideoService.queue_video_generation(image_path, prompt, kling_settings)` — calls `KlingClient.generate_video()`, logs to `VideoLogsStorage`
- `VideoService.queue_batch(images_with_prompts, kling_settings)` — loops through images, queues each, returns batch_id
- `VideoService.get_video_status(task_id)` — polls `KlingClient.get_video_status()`, updates DB
- `VideoService.list_videos(status, page, per_page)` — reads from `raw_video/` directory + DB
- `VideoService.merge_videos(filenames, transition, duration)` — calls `video_utils.merge_videos()`
- `VideoService.analyze_music(audio_path)` — runs `MusicAnalysisWorkflow`
- `VideoService.get_video_thumbnail(filename)` — generates/serves video thumbnail frame

#### 1.3 — Create Video API Routes (`backend/api/video.py`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/video/storyboard` | Generate prompts from images via CrewAI agents |
| `POST` | `/api/video/generate` | Queue single video generation to Kling |
| `POST` | `/api/video/generate-batch` | Queue batch of videos |
| `GET` | `/api/video/status/{task_id}` | Poll Kling job status |
| `GET` | `/api/video/list` | List videos (filter by status, pagination) |
| `GET` | `/api/video/{filename}` | Stream/download a video file |
| `GET` | `/api/video/{filename}/thumbnail` | Get video thumbnail |
| `POST` | `/api/video/merge` | Merge multiple videos with transitions |
| `GET` | `/api/video/merge/{task_id}/status` | Poll merge task status |
| `POST` | `/api/video/upload` | Upload external video clips |
| `DELETE` | `/api/video/{filename}` | Delete a video |
| `POST` | `/api/video/music-analysis` | Analyze uploaded audio |
| `POST` | `/api/video/music-upload` | Upload audio to GCS |
| `GET` | `/api/video/kling-presets` | List saved Kling presets |
| `POST` | `/api/video/kling-presets` | Save a Kling preset |

#### 1.4 — Create Celery Tasks (`backend/tasks.py` additions)

Add these to the existing tasks file:

- `generate_video_task(image_path, prompt, kling_settings)` — async Kling API call + DB logging
- `poll_video_batch_task(batch_id)` — periodic poll of all pending videos in a batch
- `merge_videos_task(filenames, transition, duration)` — CPU-intensive merge via moviepy
- `analyze_music_task(audio_path)` — CrewAI music analysis workflow

#### 1.5 — Register Routes in `backend/main.py`

Add the video router alongside existing routers:

```python
from backend.api.video import router as video_router
app.include_router(video_router, prefix="/api/video", tags=["video"])
```

#### 1.6 — Wire Up Dependencies (`backend/api/deps.py`)

Add singleton for `VideoService` with access to `KlingClient`, `VideoLogsStorage`, `VideoStoryboardWorkflow`, and `MusicAnalysisWorkflow`.

---

### Phase 2: Video Frontend — Create Video Tab

Build the React page that replaces the "Create Video" Streamlit tab.

#### 2.1 — Create VideoPage (`frontend/src/pages/VideoPage.tsx`)

Top-level page with 4 tabs using Shadcn `Tabs` component:

- **Create Video** — main generation workflow
- **Video Constructor** — timeline editor & merging
- **Video Gallery** — browse generated videos
- **Song Producer** — music analysis

Add route in `App.tsx`: `<Route path="video" element={<VideoPage />} />`
Add nav link in `Layout.tsx`.

#### 2.2 — Create Video API Client (`frontend/src/api/video.ts`)

TypeScript functions wrapping all `/api/video/*` endpoints with proper types.

#### 2.3 — Create TypeScript Types (`frontend/src/types/video.ts`)

Define interfaces matching backend Pydantic models: `VideoItem`, `KlingSettings`, `VideoGenerateRequest`, `StoryboardResult`, `MergeRequest`, etc.

#### 2.4 — Create Video Tab: "Create Video"

This is the largest piece. Break into sub-components:

| Component | Purpose |
|-----------|---------|
| `ImageSelector.tsx` | Select source images from gallery/processed or upload new ones. Reuse existing ref-image list from workspace API. |
| `SelectionQueue.tsx` | Show selected images with per-image variation count controls. Drag-to-reorder. |
| `StoryboardGenerator.tsx` | "Generate Prompts" button → calls storyboard API → displays editable prompts per image. Vision model selector. |
| `KlingSettingsPanel.tsx` | Model version dropdown (v1.6, v2.0, v2.6), mode (standard/pro), duration (5s/10s), aspect ratio, CFG scale, negative prompt. Audio settings for v2.6+ (sound generation toggle, custom audio, voice ID). |
| `KlingPresetManager.tsx` | Save/load named Kling setting presets (JSON). |
| `BatchQueuePanel.tsx` | "Queue to Kling" button → dispatches batch → shows progress cards per video with status polling. |
| `VideoGenerationHistory.tsx` | Table of past generations from `video_logs` DB. |

**Workflow for the user:**
1. Select images → adjust variation counts
2. Click "Generate Prompts" → review/edit generated prompts
3. Configure Kling settings (or load preset)
4. Click "Queue to Kling" → monitor progress
5. Videos appear in Video Gallery when complete

#### 2.5 — React Hooks for Create Video

- `useStoryboard()` — mutation hook for prompt generation
- `useVideoGenerate()` — mutation hook for queueing videos
- `useVideoStatus(taskId)` — polling query for Kling job status
- `useKlingPresets()` — query/mutation for presets
- `useVideoHistory()` — query for generation history

---

### Phase 3: Video Constructor Tab

#### 3.1 — Video Library Browser

- Grid of video thumbnails (generated from first frame)
- Pagination, sorted by date
- Click to preview (HTML5 `<video>` player)
- Upload button for external clips

#### 3.2 — Timeline Track Editor

- Drag-and-drop clip ordering (use a library like `@dnd-kit/core` or `react-beautiful-dnd`)
- Visual timeline showing clip durations
- Remove clips from timeline

#### 3.3 — Merge Controls

- Transition type selector (Crossfade, Fade to Black, Simple Cut)
- Transition duration slider
- "Merge" button → calls merge API → polls for result
- Preview merged video when done

**Components:**

| Component | Purpose |
|-----------|---------|
| `VideoLibrary.tsx` | Grid browser with thumbnails + upload |
| `TimelineEditor.tsx` | Drag-to-reorder clip list with durations |
| `MergeControls.tsx` | Transition settings + merge button |
| `VideoPreview.tsx` | HTML5 video player for preview |

---

### Phase 4: Video Gallery Tab

#### 4.1 — Video Gallery Grid

- Display all videos from `raw_video/` directory
- Thumbnail grid with metadata overlay (duration, date, source image)
- Click to play in modal
- Download button per video
- Delete button per video

#### 4.2 — Filtering & Organization

- Filter by date range
- Filter by source persona
- Sort by date / name
- Pagination

**Components:**

| Component | Purpose |
|-----------|---------|
| `VideoGallery.tsx` | Main grid with filters |
| `VideoCard.tsx` | Single video thumbnail card with actions |
| `VideoPlayerModal.tsx` | Full-screen video playback modal |

---

### Phase 5: Song Producer Tab

#### 5.1 — Audio Upload & Trim

- File upload for audio (mp3, wav, m4a)
- Audio player with waveform visualization (optional, could use `wavesurfer.js`)
- Trim controls (start/end time)
- Upload trimmed audio to GCS

#### 5.2 — Music Analysis

- "Analyze" button → calls music analysis API
- Displays results: vibe description, lyrics extraction, mood tags
- Option to send results to n8n webhook (keep this as a simple POST call)

**Components:**

| Component | Purpose |
|-----------|---------|
| `AudioUploader.tsx` | Upload + basic audio player |
| `AudioTrimmer.tsx` | Start/end time controls |
| `MusicAnalysisResults.tsx` | Display analysis output |

---

### Phase 6: Infrastructure & Polish

#### 6.1 — Docker Updates

- Update `docker-compose.yml` to mount `raw_video/` volume for both backend and worker services
- Ensure `ffmpeg` is available in backend container (already in Dockerfile)
- Add video output directory env var to config

#### 6.2 — Nginx Updates

- Ensure large file uploads work (video files can be big): set `client_max_body_size` in nginx.conf
- Add streaming support for video file serving

#### 6.3 — Workflow Configuration Studio

Migrate the "edit agent backstories & tasks" UI from Streamlit:

- This is already partially covered by the **PromptsPage** (template editor)
- Extend PromptsPage to include video workflow agent configuration (analyst, concept creator, prompt specialist backstories and task descriptions)
- Store as text files in `prompts/templates/video/`

#### 6.4 — Export Utilities (Optional)

Migrate `export_utils.py` if social media CSV export is needed. Create:
- `POST /api/video/export` — generates CSV for RecurPost or other platforms
- Frontend download button in Video Gallery

---

## Implementation Order & Estimates

| Phase | Description | Estimated Effort | Dependencies |
|-------|-------------|-----------------|--------------|
| **1** | Backend API + Tasks | 2-3 days | None |
| **2** | Create Video Tab (frontend) | 3-4 days | Phase 1 |
| **3** | Video Constructor Tab | 2-3 days | Phase 1 |
| **4** | Video Gallery Tab | 1-2 days | Phase 1 |
| **5** | Song Producer Tab | 1-2 days | Phase 1 |
| **6** | Infrastructure & Polish | 1 day | All phases |

**Total estimate: ~10-15 days**

---

## File Creation Summary

### New Files to Create

**Backend:**
```
backend/
├── models/video.py          (NEW - Pydantic schemas)
├── services/video.py        (NEW - Business logic)
├── api/video.py             (NEW - FastAPI routes)
└── tasks.py                 (EDIT - Add video tasks)
```

**Frontend:**
```
frontend/src/
├── pages/VideoPage.tsx                    (NEW)
├── types/video.ts                         (NEW)
├── api/video.ts                           (NEW)
├── hooks/
│   ├── useStoryboard.ts                   (NEW)
│   ├── useVideoGenerate.ts                (NEW)
│   ├── useVideoStatus.ts                  (NEW)
│   └── useVideoLibrary.ts                 (NEW)
├── components/video/
│   ├── ImageSelector.tsx                  (NEW)
│   ├── SelectionQueue.tsx                 (NEW)
│   ├── StoryboardGenerator.tsx            (NEW)
│   ├── KlingSettingsPanel.tsx             (NEW)
│   ├── KlingPresetManager.tsx             (NEW)
│   ├── BatchQueuePanel.tsx                (NEW)
│   ├── VideoGenerationHistory.tsx         (NEW)
│   ├── VideoLibrary.tsx                   (NEW)
│   ├── TimelineEditor.tsx                 (NEW)
│   ├── MergeControls.tsx                  (NEW)
│   ├── VideoPreview.tsx                   (NEW)
│   ├── VideoGallery.tsx                   (NEW)
│   ├── VideoCard.tsx                      (NEW)
│   ├── VideoPlayerModal.tsx               (NEW)
│   ├── AudioUploader.tsx                  (NEW)
│   ├── AudioTrimmer.tsx                   (NEW)
│   └── MusicAnalysisResults.tsx           (NEW)
```

**Config:**
```
App.tsx                  (EDIT - Add /video route)
Layout.tsx               (EDIT - Add Video nav link)
backend/main.py          (EDIT - Register video router)
backend/api/deps.py      (EDIT - Add VideoService)
docker-compose.yml       (EDIT - Mount raw_video volume)
nginx.conf               (EDIT - client_max_body_size)
```

### Existing Files to Reuse (Already in Target)

These are already copied into the target backend — they just need to be imported and used by the new service/routes:

```
backend/workflows/video_storyboard_workflow.py   (USE)
backend/workflows/music_analysis_workflow.py      (USE)
backend/third_parties/kling_client.py             (USE)
backend/database/video_logs_storage.py            (USE)
backend/utils/video_utils.py                      (USE)
backend/tools/audio_tool.py                       (USE)
```

---

## Key Differences from Streamlit Version

1. **Async-first:** All Kling API calls go through Celery tasks instead of blocking the UI thread with `time.sleep` polling loops.
2. **Real-time updates:** Use the existing WebSocket pattern (`/ws/tasks`) for video task progress instead of Streamlit's `st.rerun()`.
3. **Separation of concerns:** Business logic in services, not embedded in UI code.
4. **Type safety:** TypeScript frontend with Zod validation on forms.
5. **Persistent state:** React Query cache + Zustand store instead of `st.session_state`.

---

## Risk & Notes

- **Large video files:** Kling generates videos that can be 50-200MB. Ensure streaming responses for downloads and proper nginx buffering.
- **Long-running tasks:** Video generation takes 1-5 minutes per clip on Kling. The polling/WebSocket architecture from the image pipeline can be reused.
- **Video merging:** moviepy operations are CPU-intensive. Run merge tasks on the Celery worker, not the API server.
- **GCS integration:** The Streamlit app uses GCS for video/audio storage. Ensure GCS client is properly initialized in the FastAPI service layer.
- **Kling API rate limits:** The batch queue should respect rate limits. Consider adding a configurable delay between submissions.

"""
Video API router — Kling video generation, storyboarding, music analysis,
merge, and preset management.
"""
import uuid
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, Response

from backend.api.deps import get_video_service
from backend.celery_app import celery_app
from backend.config import GlobalConfig
from backend.models.video import (
    KlingPreset,
    KlingSettings,
    MusicAnalysisRequest,
    MusicAnalysisResponse,
    StoryboardRequest,
    StoryboardResponse,
    VideoBatchRequest,
    VideoBatchResponse,
    VideoGenerateRequest,
    VideoGenerateResponse,
    VideoListResponse,
    VideoMergeRequest,
    VideoMergeResponse,
    VideoStatusResponse,
)
from backend.services.video import VideoService
from backend.tasks import merge_videos_task, analyze_music_task

router = APIRouter()


# ------------------------------------------------------------------
# Storyboard
# ------------------------------------------------------------------

@router.post("/storyboard", response_model=StoryboardResponse)
def generate_storyboard(
    body: StoryboardRequest,
    svc: VideoService = Depends(get_video_service),
):
    """Generate storyboard prompts for one or more images."""
    results = []
    for image_path in body.image_paths:
        try:
            raw = svc.generate_storyboard(
                image_path=image_path,
                persona=body.persona,
                vision_model=body.vision_model,
                variation_count=body.variation_count,
            )
            results.append(raw)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Storyboard failed for {image_path}: {e}")
    return {"results": results}


# ------------------------------------------------------------------
# Video generation
# ------------------------------------------------------------------

@router.post("/generate", response_model=VideoGenerateResponse)
def generate_video(
    body: VideoGenerateRequest,
    svc: VideoService = Depends(get_video_service),
):
    """Queue a single Kling video generation task."""
    try:
        task_id = svc.queue_video(
            image_path=body.image_path,
            prompt=body.prompt,
            kling_settings=body.kling_settings,
            batch_id=body.batch_id,
        )
        return VideoGenerateResponse(task_id=task_id, batch_id=body.batch_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/generate-batch", response_model=VideoBatchResponse)
def generate_video_batch(
    body: VideoBatchRequest,
    svc: VideoService = Depends(get_video_service),
):
    """Queue multiple Kling video generation tasks as a batch."""
    batch_id = uuid.uuid4().hex
    task_ids: List[str] = []

    for item in body.items:
        for _ in range(item.variation_count):
            try:
                task_id = svc.queue_video(
                    image_path=item.image_path,
                    prompt=item.prompt,
                    kling_settings=body.kling_settings,
                    batch_id=batch_id,
                )
                task_ids.append(task_id)
            except Exception as e:
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to queue video for {item.image_path}: {e}",
                )

    return VideoBatchResponse(batch_id=batch_id, task_ids=task_ids)


# ------------------------------------------------------------------
# Status polling
# ------------------------------------------------------------------

@router.get("/status/{task_id}", response_model=VideoStatusResponse)
def get_video_status(
    task_id: str,
    svc: VideoService = Depends(get_video_service),
):
    """Poll Kling API for a video task status."""
    return svc.get_video_status(task_id)


# ------------------------------------------------------------------
# Listing
# ------------------------------------------------------------------

@router.get("/list", response_model=VideoListResponse)
def list_videos(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    svc: VideoService = Depends(get_video_service),
):
    """List all video generation records with pagination."""
    return svc.list_videos(page=page, per_page=per_page)


# ------------------------------------------------------------------
# File serving
# ------------------------------------------------------------------

@router.get("/{filename}/thumbnail")
def get_video_thumbnail(
    filename: str,
    svc: VideoService = Depends(get_video_service),
):
    """Return the first frame of a video as a JPEG thumbnail."""
    data = svc.get_video_thumbnail(filename)
    if data is None:
        raise HTTPException(status_code=404, detail="Thumbnail not available")
    return Response(content=data, media_type="image/jpeg")


@router.get("/{filename}")
def stream_video(filename: str):
    """Stream or download a video file."""
    video_dir = Path(GlobalConfig.VIDEO_DIR)
    video_path = video_dir / filename
    if not video_path.exists():
        raise HTTPException(status_code=404, detail="Video not found")
    return FileResponse(str(video_path), media_type="video/mp4", filename=filename)


# ------------------------------------------------------------------
# Merge
# ------------------------------------------------------------------

@router.post("/merge", response_model=VideoMergeResponse)
def merge_videos(body: VideoMergeRequest):
    """Merge multiple videos with transitions (async Celery task)."""
    output_filename = f"merged_{uuid.uuid4().hex[:8]}.mp4"
    task = merge_videos_task.apply_async(
        args=[body.filenames, body.transition_type, body.transition_duration],
    )
    return VideoMergeResponse(task_id=task.id, output_filename=output_filename)


@router.get("/merge/{task_id}/status")
def get_merge_status(task_id: str):
    """Poll the status of a video merge Celery task."""
    result = celery_app.AsyncResult(task_id)
    state = result.state
    meta = result.info or {}
    if isinstance(meta, Exception):
        meta = {"error": str(meta)}
    return {
        "task_id": task_id,
        "state": state,
        "progress": meta.get("progress", 0) if isinstance(meta, dict) else 0,
        "result": meta if state == "SUCCESS" else None,
    }


# ------------------------------------------------------------------
# Upload
# ------------------------------------------------------------------

@router.post("/upload")
async def upload_video(file: UploadFile = File(...)):
    """Upload an external video clip to the video directory."""
    video_dir = Path(GlobalConfig.VIDEO_DIR)
    video_dir.mkdir(parents=True, exist_ok=True)

    safe_name = Path(file.filename or "upload.mp4").name
    dest = video_dir / safe_name
    # Avoid overwriting existing files
    if dest.exists():
        stem = dest.stem
        suffix = dest.suffix
        dest = video_dir / f"{stem}_{uuid.uuid4().hex[:6]}{suffix}"

    data = await file.read()
    dest.write_bytes(data)
    return {"filename": dest.name, "size_bytes": len(data)}


# ------------------------------------------------------------------
# Delete
# ------------------------------------------------------------------

@router.delete("/{filename}")
def delete_video(
    filename: str,
    svc: VideoService = Depends(get_video_service),
):
    """Delete a video file from disk."""
    video_dir = Path(GlobalConfig.VIDEO_DIR)
    video_path = video_dir / filename
    if not video_path.exists():
        raise HTTPException(status_code=404, detail="Video not found")
    try:
        video_path.unlink()
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Delete failed: {e}")
    return {"deleted": filename}


# ------------------------------------------------------------------
# Music analysis
# ------------------------------------------------------------------

@router.post("/music-analysis")
def music_analysis(body: MusicAnalysisRequest):
    """Analyze an audio file for vibe and lyrics (async Celery task)."""
    task = analyze_music_task.apply_async(args=[body.audio_path])
    return {"task_id": task.id, "status": "pending"}


# ------------------------------------------------------------------
# Presets
# ------------------------------------------------------------------

@router.get("/kling-presets", response_model=List[KlingPreset])
def list_presets(svc: VideoService = Depends(get_video_service)):
    """List all saved Kling generation presets."""
    return svc.list_presets()


@router.post("/kling-presets", response_model=KlingPreset)
def save_preset(preset: KlingPreset, svc: VideoService = Depends(get_video_service)):
    """Save or overwrite a named Kling preset."""
    return svc.save_preset(preset.name, preset.settings)


@router.delete("/kling-presets/{name}")
def delete_preset(name: str, svc: VideoService = Depends(get_video_service)):
    """Delete a named Kling preset."""
    deleted = svc.delete_preset(name)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Preset '{name}' not found")
    return {"deleted": name}

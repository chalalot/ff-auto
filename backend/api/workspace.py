import asyncio
import io
import zipfile
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from fastapi.responses import Response, StreamingResponse
from fastapi.websockets import WebSocket, WebSocketDisconnect

from backend.api.deps import get_image_processing_service, get_image_logs_storage, get_runpod_jobs_storage
from backend.models.workspace import (
    InputImage,
    RefImage,
    ProcessImageRequest,
    ProcessBatchRequest,
    TaskStatusResponse,
    DispatchResponse,
    BatchDispatchResponse,
    ActiveTask,
    ExecutionRecord,
    CaptionExportEntry,
    CaptionExportUploadResponse,
    CaptionExportRequest,
    GDriveFetchRequest,
    GDriveUploadZipRequest,
    RunpodSubmitRequest,
    ManualExportToDriveRequest,
)
from backend.services.image_processing import ImageProcessingService
from backend.database.image_logs_storage import ImageLogsStorage

router = APIRouter()


@router.get("/input-images", response_model=List[InputImage])
def list_input_images(svc: ImageProcessingService = Depends(get_image_processing_service)):
    return svc.scan_input_directory()


@router.get("/input-images/{filename}/thumbnail")
def input_image_thumbnail(filename: str, svc: ImageProcessingService = Depends(get_image_processing_service)):
    data = svc.get_input_image_thumbnail(filename)
    if not data:
        raise HTTPException(status_code=404, detail="Image not found")
    return Response(content=data, media_type="image/jpeg")


@router.post("/upload")
async def upload_images(
    files: List[UploadFile] = File(...),
    svc: ImageProcessingService = Depends(get_image_processing_service),
):
    """Save uploaded images directly into PROCESSED_DIR (unified library)."""
    saved = []
    for f in files:
        data = await f.read()
        try:
            path = svc.save_ref_image(f.filename or "upload", data)
            saved.append(Path(path).name)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    return {"saved": saved, "count": len(saved)}


@router.post("/process", response_model=DispatchResponse)
def process_image(body: ProcessImageRequest, svc: ImageProcessingService = Depends(get_image_processing_service)):
    try:
        task_id = svc.dispatch_processing(
            image_path=body.image_path,
            persona=body.persona,
            workflow_type=body.workflow_type,
            vision_model=body.vision_model,
            variation_count=body.variation_count,
            strength=body.strength,
            seed_strategy=body.seed_strategy,
            base_seed=body.base_seed,
            width=body.width,
            height=body.height,
            lora_name=body.lora_name,
            clip_model_type=body.clip_model_type,
            prepare=not body.skip_prepare,
        )
        return {"task_id": task_id}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/process-batch", response_model=BatchDispatchResponse)
def process_batch(body: ProcessBatchRequest, svc: ImageProcessingService = Depends(get_image_processing_service)):
    try:
        task_ids = svc.dispatch_batch(
            image_paths=body.image_paths,
            persona=body.persona,
            workflow_type=body.workflow_type,
            vision_model=body.vision_model,
            variation_count=body.variation_count,
            strength=body.strength,
            seed_strategy=body.seed_strategy,
            base_seed=body.base_seed,
            width=body.width,
            height=body.height,
            lora_name=body.lora_name,
            clip_model_type=body.clip_model_type,
            prepare=not body.skip_prepare,
        )
        return {"task_ids": task_ids}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ------------------------------------------------------------------
# Reference image library (processed/ directory)
# ------------------------------------------------------------------

@router.get("/ref-images", response_model=List[RefImage])
def list_ref_images(
    svc: ImageProcessingService = Depends(get_image_processing_service),
    storage: ImageLogsStorage = Depends(get_image_logs_storage),
):
    use_counts = storage.get_ref_path_use_counts()
    return svc.scan_ref_images(use_counts)


@router.post("/ref-images/upload", response_model=List[RefImage])
async def upload_ref_images(
    files: List[UploadFile] = File(...),
    svc: ImageProcessingService = Depends(get_image_processing_service),
    storage: ImageLogsStorage = Depends(get_image_logs_storage),
):
    """Upload images directly into PROCESSED_DIR as reusable ref images."""
    for f in files:
        data = await f.read()
        try:
            svc.save_ref_image(f.filename or "upload", data)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    use_counts = storage.get_ref_path_use_counts()
    return svc.scan_ref_images(use_counts)


@router.delete("/ref-images/{filename}")
def delete_ref_image(filename: str, svc: ImageProcessingService = Depends(get_image_processing_service)):
    try:
        svc.delete_ref_image(filename)
        return {"deleted": filename}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/ref-images/{filename}/thumbnail")
def ref_image_thumbnail(filename: str, svc: ImageProcessingService = Depends(get_image_processing_service)):
    data = svc.get_ref_image_thumbnail(filename)
    if not data:
        raise HTTPException(status_code=404, detail="Ref image not found")
    return Response(content=data, media_type="image/jpeg")


@router.get("/ref-images/{filename}")
def ref_image_full(filename: str, svc: ImageProcessingService = Depends(get_image_processing_service)):
    data = svc.get_ref_image_bytes(filename)
    if not data:
        raise HTTPException(status_code=404, detail="Ref image not found")
    suffix = Path(filename).suffix.lower()
    media_type = "image/png" if suffix == ".png" else "image/jpeg"
    return Response(content=data, media_type=media_type)


@router.get("/active-tasks")
def list_active_tasks(svc: ImageProcessingService = Depends(get_image_processing_service)):
    """
    Returns all currently running tasks across all users.
    Registered in Redis on dispatch; pruned when a terminal state is detected.
    Poll this every 5s from any client to show a shared live view.
    """
    return svc.get_active_tasks()


@router.get("/task/{task_id}/status", response_model=TaskStatusResponse)
def task_status(task_id: str, svc: ImageProcessingService = Depends(get_image_processing_service)):
    return svc.get_task_status(task_id)


@router.get("/executions", response_model=List[ExecutionRecord])
def list_executions(
    limit: int = Query(50, ge=1, le=500),
    storage: ImageLogsStorage = Depends(get_image_logs_storage),
):
    rows = storage.get_recent_executions(limit=limit)
    return rows


# ------------------------------------------------------------------
# Caption Export — run CrewAI, export ZIP of images + .txt prompts
# ------------------------------------------------------------------

@router.post("/caption-export/upload", response_model=CaptionExportUploadResponse)
async def caption_export_upload(
    files: List[UploadFile] = File(...),
    svc: ImageProcessingService = Depends(get_image_processing_service),
):
    """Upload images for caption export. Saves to PROCESSED_DIR; returns stem mapping."""
    entries = []
    for f in files:
        data = await f.read()
        original_name = f.filename or "upload"
        stem = Path(original_name).stem
        ext = Path(original_name).suffix.lower() or ".jpg"
        try:
            saved_path = svc.save_ref_image(original_name, data)
            entries.append(CaptionExportEntry(stem=stem, path=saved_path, original_ext=ext))
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    return CaptionExportUploadResponse(entries=entries)


@router.post("/caption-export/start")
def caption_export_start(body: CaptionExportRequest):
    """Dispatch caption_export_task to run CrewAI on each uploaded image."""
    import json as _json
    import time as _time
    from backend.celery_app import celery_app as _celery
    from backend.services.image_processing import _redis_client, _ACTIVE_TASKS_SET, _TASK_META_PREFIX, _TASK_META_TTL

    task = _celery.send_task(
        "backend.tasks.caption_export_task",
        kwargs={
            "image_entries": [e.model_dump() for e in body.image_entries],
            "persona": body.persona,
            "vision_model": body.vision_model,
            "workflow_type": body.workflow_type,
        },
        queue="image",
    )

    # Register in Redis so any session/user can track this task
    try:
        r = _redis_client()
        meta = _json.dumps({
            "task_type": "caption_export",
            "persona": body.persona,
            "image_count": len(body.image_entries),
            "dispatched_at": _time.time(),
        })
        r.sadd(_ACTIVE_TASKS_SET, task.id)
        r.setex(_TASK_META_PREFIX + task.id, _TASK_META_TTL, meta)
    except Exception as exc:
        logger.warning(f"Could not register caption export task {task.id} in Redis: {exc}")

    return {"task_id": task.id}


@router.get("/caption-export/{task_id}/download")
def caption_export_download(task_id: str):
    """Build and stream a ZIP of (image + .txt prompt) pairs once the task succeeds."""
    from celery.result import AsyncResult
    from backend.celery_app import celery_app as _celery

    result = AsyncResult(task_id, app=_celery)
    if result.state != "SUCCESS":
        raise HTTPException(
            status_code=400,
            detail=f"Task not ready (state: {result.state}). Wait for it to finish.",
        )

    data = result.result or {}
    results = data.get("results", [])

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for item in results:
            stem = item.get("stem", "image")
            ext = item.get("original_ext", ".jpg")
            image_path = Path(item.get("path", ""))
            prompt = item.get("prompt", "")

            if image_path.exists():
                zf.write(image_path, f"{stem}{ext}")
            zf.writestr(f"{stem}.txt", prompt)

    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="caption_export_{task_id[:8]}.zip"'},
    )


# ------------------------------------------------------------------
# Caption Export — Google Drive integration
# ------------------------------------------------------------------

@router.post("/caption-export/gdrive/fetch", response_model=CaptionExportUploadResponse)
async def caption_export_gdrive_fetch(
    body: GDriveFetchRequest,
    svc: ImageProcessingService = Depends(get_image_processing_service),
):
    """
    Fetch images from a Google Drive folder, downscale with Pillow, save to
    PROCESSED_DIR, and return entries in the same format as the upload endpoint.
    """
    import io as _io
    from PIL import Image
    from backend.third_parties import gdrive_client

    try:
        folder_id = gdrive_client.get_folder_id(body.folder_url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        files = gdrive_client.list_images_in_folder(folder_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to list Drive folder: {e}")

    if not files:
        raise HTTPException(status_code=404, detail="No images found in the specified Drive folder")

    entries = []
    errors = []
    for file in files:
        try:
            raw = gdrive_client.download_file(file["id"])
            img = Image.open(_io.BytesIO(raw)).convert("RGB")
            if body.max_dimension and max(img.size) > body.max_dimension:
                img.thumbnail((body.max_dimension, body.max_dimension), Image.LANCZOS)
            buf = _io.BytesIO()
            img.save(buf, format="JPEG", quality=90)
            data = buf.getvalue()

            stem = Path(file["name"]).stem
            ext = ".jpg"
            saved_path = svc.save_ref_image(f"{stem}{ext}", data)
            entries.append(CaptionExportEntry(stem=stem, path=saved_path, original_ext=ext))
        except Exception as e:
            errors.append(f"{file['name']}: {e}")

    if not entries:
        detail = "Failed to process any images from Drive"
        if errors:
            detail += f". Errors: {'; '.join(errors[:3])}"
        raise HTTPException(status_code=500, detail=detail)

    return CaptionExportUploadResponse(entries=entries)


@router.post("/caption-export/gdrive/upload-zip")
def caption_export_gdrive_upload_zip(body: GDriveUploadZipRequest):
    """
    Build the ZIP (images + .txt prompts) from a completed caption task, upload it
    to the configured GDRIVE_UPLOAD_FOLDER_ID, and make it publicly readable.
    """
    from celery.result import AsyncResult
    from backend.celery_app import celery_app as _celery
    from backend.third_parties import gdrive_client
    from backend.config import GlobalConfig

    folder_id = GlobalConfig.GDRIVE_UPLOAD_FOLDER_ID
    if not folder_id:
        raise HTTPException(status_code=400, detail="GDRIVE_UPLOAD_FOLDER_ID is not set in .env")

    result = AsyncResult(body.task_id, app=_celery)
    if result.state != "SUCCESS":
        raise HTTPException(
            status_code=400,
            detail=f"Task not ready (state: {result.state}). Wait for it to finish.",
        )

    data = result.result or {}
    results = data.get("results", [])

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for item in results:
            stem = item.get("stem", "image")
            ext = item.get("original_ext", ".jpg")
            image_path = Path(item.get("path", ""))
            prompt = item.get("prompt", "")
            if image_path.exists():
                zf.write(image_path, f"{stem}{ext}")
            zf.writestr(f"{stem}.txt", prompt)
    zip_data = buf.getvalue()

    try:
        zip_filename = f"caption_export_{body.task_id[:8]}.zip"
        file_id = gdrive_client.upload_file(zip_filename, zip_data, "application/zip", folder_id)
        public_url = gdrive_client.make_file_public(file_id)
        return {"file_id": file_id, "filename": zip_filename, "public_url": public_url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to upload to Drive: {e}")


# ------------------------------------------------------------------
# Caption Export — manual captions → ZIP → Drive
# ------------------------------------------------------------------

@router.post("/caption-export/manual/export-to-drive")
def caption_export_manual_to_drive(body: ManualExportToDriveRequest):
    """Build ZIP from manually-supplied captions and upload to Google Drive."""
    import time as _time
    from backend.third_parties import gdrive_client
    from backend.config import GlobalConfig

    folder_id = GlobalConfig.GDRIVE_UPLOAD_FOLDER_ID
    if not folder_id:
        raise HTTPException(status_code=400, detail="GDRIVE_UPLOAD_FOLDER_ID is not set in .env")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for entry in body.entries:
            image_path = Path(entry.path)
            caption = body.captions.get(entry.stem, "")
            if image_path.exists():
                zf.write(image_path, f"{entry.stem}{entry.original_ext}")
            zf.writestr(f"{entry.stem}.txt", caption)
    zip_data = buf.getvalue()

    ts = int(_time.time())
    zip_filename = f"manual_captions_{ts}.zip"
    try:
        file_id = gdrive_client.upload_file(zip_filename, zip_data, "application/zip", folder_id)
        public_url = gdrive_client.make_file_public(file_id)
        return {
            "file_id": file_id,
            "filename": zip_filename,
            "folder_id": folder_id,
            "public_url": public_url,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to upload to Drive: {e}")


# ------------------------------------------------------------------
# Caption Export — RunPod LoRA training
# ------------------------------------------------------------------

@router.get("/caption-export/runpod/jobs")
def caption_export_runpod_jobs(
    db: "RunpodJobsStorage" = Depends(get_runpod_jobs_storage),
):
    return db.list_jobs()


@router.post("/caption-export/runpod/submit")
def caption_export_runpod_submit(
    body: RunpodSubmitRequest,
    db: "RunpodJobsStorage" = Depends(get_runpod_jobs_storage),
):
    """Submit a LoRA training job to the RunPod serverless endpoint and persist it."""
    import requests as _requests
    from datetime import datetime
    from backend.config import GlobalConfig

    api_key = GlobalConfig.RUNPOD_API_KEY
    endpoint_id = body.endpoint_id or GlobalConfig.RUNPOD_ENDPOINT_ID

    if not api_key:
        raise HTTPException(status_code=400, detail="RUNPOD_API_KEY is not configured in .env")
    if not endpoint_id:
        raise HTTPException(status_code=400, detail="RUNPOD_ENDPOINT_ID is not configured in .env")

    url = f"https://api.runpod.ai/v2/{endpoint_id}/run"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {"input": body.job_input.model_dump()}

    try:
        resp = _requests.post(url, json=payload, headers=headers, timeout=30)
        resp.raise_for_status()
    except _requests.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"RunPod API error: {e.response.text}")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to reach RunPod: {e}")

    result = resp.json()
    job_id = result["id"]

    db.insert(
        job_id=job_id,
        endpoint_id=endpoint_id,
        lora_name=body.job_input.lora_name,
        submitted_at=datetime.utcnow().isoformat(),
        job_input=body.job_input.model_dump(),
    )

    return {"job_id": job_id, "endpoint_id": endpoint_id}


@router.get("/caption-export/runpod/status/{job_id}")
def caption_export_runpod_status(
    job_id: str,
    endpoint_id: Optional[str] = None,
    db: "RunpodJobsStorage" = Depends(get_runpod_jobs_storage),
):
    """Check the current status of a RunPod job and update the DB record."""
    import requests as _requests
    from backend.config import GlobalConfig

    api_key = GlobalConfig.RUNPOD_API_KEY
    eid = endpoint_id or GlobalConfig.RUNPOD_ENDPOINT_ID

    if not api_key:
        raise HTTPException(status_code=400, detail="RUNPOD_API_KEY is not configured in .env")
    if not eid:
        raise HTTPException(status_code=400, detail="RUNPOD_ENDPOINT_ID is not configured in .env")

    url = f"https://api.runpod.ai/v2/{eid}/status/{job_id}"
    headers = {"Authorization": f"Bearer {api_key}"}

    try:
        resp = _requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
    except _requests.HTTPError as e:
        if e.response.status_code == 404:
            db.update_status(job_id=job_id, status="COMPLETED")
            return {"id": job_id, "status": "COMPLETED", "message": "Job completed and cleared from RunPod queue."}
        raise HTTPException(status_code=502, detail=f"RunPod API error: {e.response.text}")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to reach RunPod: {e}")

    data = resp.json()
    db.update_status(
        job_id=job_id,
        status=data.get("status", ""),
        output=data.get("output"),
    )
    return data


# ------------------------------------------------------------------
# WebSocket — real-time task progress polling
# ------------------------------------------------------------------

@router.websocket("/ws/tasks")
async def ws_task_progress(websocket: WebSocket, svc: ImageProcessingService = Depends(get_image_processing_service)):
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_json()
            task_id = data.get("task_id")
            if not task_id:
                continue
            status = svc.get_task_status(task_id)
            await websocket.send_json(status)
    except WebSocketDisconnect:
        pass

import asyncio
import shutil
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from fastapi.responses import Response
from fastapi.websockets import WebSocket, WebSocketDisconnect

from backend.api.deps import get_image_processing_service, get_image_logs_storage
from backend.models.workspace import (
    InputImage,
    ProcessImageRequest,
    ProcessBatchRequest,
    TaskStatusResponse,
    DispatchResponse,
    BatchDispatchResponse,
    ExecutionRecord,
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
    """Save uploaded images into INPUT_DIR so they appear in the queue."""
    allowed = {".png", ".jpg", ".jpeg", ".webp"}
    saved = []
    for f in files:
        ext = Path(f.filename or "").suffix.lower()
        if ext not in allowed:
            raise HTTPException(status_code=400, detail=f"Unsupported file type: {f.filename}")
        dest = Path(svc.input_dir) / f.filename
        with dest.open("wb") as out:
            shutil.copyfileobj(f.file, out)
        saved.append(f.filename)
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
        )
        return {"task_ids": task_ids}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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

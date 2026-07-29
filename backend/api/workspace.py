"""Workspace routes: the image library, generation dispatch, and task status.

Pipeline/workflow introspection and the workflow file library live in
:mod:`backend.api.workflows`; the caption-export / RunPod / Hugging Face flow
lives in :mod:`backend.api.exports`. All three are mounted under the same
``/api/workspace`` prefix, so the split changed no URLs.
"""
import asyncio
import ipaddress
import socket
from pathlib import Path
from typing import List, Optional
from urllib.parse import urlparse

import httpx

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from fastapi.responses import Response
from fastapi.websockets import WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from backend.api.deps import get_image_processing_service, get_image_logs_storage
from backend.models.workspace import (
    InputImage,
    RefImage,
    ProcessImageRequest,
    ProcessBatchRequest,
    RunWorkflowDirectRequest,
    TaskStatusResponse,
    DispatchResponse,
    BatchDispatchResponse,
    ExecutionRecord,
)
from backend.services.image_processing import ImageProcessingService
from backend.database.image_logs_storage import ImageLogsStorage
from backend.api.identity import Identity, get_identity
from backend.database.uploads_storage import UploadsStorage

router = APIRouter()


def _assert_paths_in_roots(raw_paths: List[str]) -> None:
    """Reject dispatch paths that leave the app's image directories.

    Every path handed to a dispatch endpoint is eventually read off disk and
    uploaded to ComfyUI (or sent to a vision model), so an unconstrained path
    here is an arbitrary local-file read. Same roots as the review queue.
    """
    from backend.api.review import _source_path_in_roots

    outside, missing = [], []
    for raw in raw_paths:
        path = _source_path_in_roots(raw)
        if path is None:
            outside.append(raw)
        elif not path.is_file():
            missing.append(raw)
    if outside:
        raise HTTPException(
            status_code=400,
            detail=f"Image(s) outside the allowed directories: {', '.join(outside)}",
        )
    if missing:
        raise HTTPException(status_code=404, detail=f"Image(s) not found: {', '.join(missing)}")


def _validate_image_pipeline_type(pipeline_type: str) -> None:
    """Reject unknown or non-image pipeline types at the request boundary."""
    from backend.pipelines import UnknownPipelineError, get_pipeline

    try:
        pipeline = get_pipeline(pipeline_type)
    except UnknownPipelineError:
        raise HTTPException(status_code=400, detail=f"Unknown pipeline_type '{pipeline_type}'")
    if pipeline.media_type != "image":
        raise HTTPException(
            status_code=400,
            detail=f"pipeline_type '{pipeline_type}' is not an image pipeline",
        )


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
    identity: Identity = Depends(get_identity),
):
    """Save uploaded images directly into PROCESSED_DIR (unified library)."""
    saved = []
    uploads = UploadsStorage()
    for f in files:
        data = await f.read()
        try:
            path = svc.save_ref_image(f.filename or "upload", data)
            saved.append(Path(path).name)
            uploads.add_upload(
                filename=Path(path).name, path=str(path), kind="input",
                project_id=identity.project_id,
                created_by_member_id=identity.member_id,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    return {"saved": saved, "count": len(saved)}


@router.post("/process", response_model=DispatchResponse)
def process_image(
    body: ProcessImageRequest,
    svc: ImageProcessingService = Depends(get_image_processing_service),
    identity: Identity = Depends(get_identity),
):
    _validate_image_pipeline_type(body.pipeline_type)
    # A brief-only run has no source image; anything else must be in the library.
    if body.image_path:
        _assert_paths_in_roots([body.image_path])
    try:
        dispatch = svc.dispatch_processing(
            image_path=body.image_path,
            persona=body.persona,
            workflow_type=body.workflow_type,
            vision_model=body.vision_model,
            variation_count=body.variation_count,
            width=body.width,
            height=body.height,
            pipeline_type=body.pipeline_type,
            workflow_overrides=body.workflow_overrides,
            workflow_name=body.workflow_name,
            project_id=identity.project_id,
            member_id=identity.member_id,
            prepare=not body.skip_prepare,
            brief=body.brief,
        )
        return dispatch
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/process-batch", response_model=BatchDispatchResponse)
def process_batch(
    body: ProcessBatchRequest,
    svc: ImageProcessingService = Depends(get_image_processing_service),
    identity: Identity = Depends(get_identity),
):
    _validate_image_pipeline_type(body.pipeline_type)
    _assert_paths_in_roots(body.image_paths)
    try:
        dispatches = svc.dispatch_batch(
            image_paths=body.image_paths,
            persona=body.persona,
            workflow_type=body.workflow_type,
            vision_model=body.vision_model,
            variation_count=body.variation_count,
            width=body.width,
            height=body.height,
            pipeline_type=body.pipeline_type,
            workflow_overrides=body.workflow_overrides,
            workflow_name=body.workflow_name,
            project_id=identity.project_id,
            member_id=identity.member_id,
            prepare=not body.skip_prepare,
        )
        return {
            "task_ids": [item["task_id"] for item in dispatches],
            "run_ids": [item.get("run_id") for item in dispatches],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/run-direct", response_model=BatchDispatchResponse)
def run_workflow_direct(
    body: RunWorkflowDirectRequest,
    svc: ImageProcessingService = Depends(get_image_processing_service),
    identity: Identity = Depends(get_identity),
):
    """Submit selected image(s) straight to a ComfyUI workflow.

    Image → LoadImage node; optional prompt → CLIPTextEncode node; everything
    else is edited via workflow_overrides. Used by the Image Upscaler and
    Multiangle-Edit workflow types, and by Image Generation with a manual prompt.
    """
    from backend.pipelines import list_workflow_files

    if body.workflow_name not in list_workflow_files():
        raise HTTPException(status_code=404, detail=f"Unknown workflow '{body.workflow_name}'")
    _assert_paths_in_roots(body.image_paths)
    try:
        dispatches = svc.dispatch_direct(
            image_paths=body.image_paths,
            workflow_name=body.workflow_name,
            workflow_type=body.workflow_type,
            prompt=body.prompt,
            workflow_overrides=body.workflow_overrides,
            project_id=identity.project_id,
            member_id=identity.member_id,
        )
        return {"task_ids": [item["task_id"] for item in dispatches], "run_ids": []}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ------------------------------------------------------------------
# Reference image library (processed/ directory)
# ------------------------------------------------------------------

@router.get("/ref-images", response_model=List[RefImage])
def list_ref_images(
    project_id: Optional[str] = Query(None),
    svc: ImageProcessingService = Depends(get_image_processing_service),
    storage: ImageLogsStorage = Depends(get_image_logs_storage),
):
    use_counts = storage.get_ref_path_use_counts()
    images = svc.scan_ref_images(use_counts)
    if project_id:
        allowed = UploadsStorage().get_project_ref_basenames(project_id)
        images = [im for im in images if im["filename"] in allowed]
    return images


@router.post("/ref-images/upload", response_model=List[RefImage])
async def upload_ref_images(
    files: List[UploadFile] = File(...),
    svc: ImageProcessingService = Depends(get_image_processing_service),
    storage: ImageLogsStorage = Depends(get_image_logs_storage),
    identity: Identity = Depends(get_identity),
):
    """Upload images directly into PROCESSED_DIR as reusable ref images."""
    uploads = UploadsStorage()
    for f in files:
        data = await f.read()
        try:
            path = svc.save_ref_image(f.filename or "upload", data)
            uploads.add_upload(
                filename=Path(path).name, path=str(path), kind="ref",
                project_id=identity.project_id,
                created_by_member_id=identity.member_id,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    use_counts = storage.get_ref_path_use_counts()
    return svc.scan_ref_images(use_counts)


class FetchImageRequest(BaseModel):
    url: str


_FETCH_IMAGE_MAX_BYTES = 30 * 1024 * 1024
_FETCH_IMAGE_MIME_TO_EXT = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/webp": ".webp",
}
_FETCH_IMAGE_EXT_TO_MIME = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


def _resolve_host_ips(host: str) -> List[str]:
    """Resolve a hostname to its addresses (separate function so tests can patch it)."""
    return [info[4][0] for info in socket.getaddrinfo(host, None)]


async def _resolve_public_http_url(url: str) -> str:
    """SSRF guard: only http(s) URLs whose host resolves to public addresses.

    The backend can reach internal services (redis, postgres, ComfyUI) that
    the browser cannot, so it must not be usable as a proxy into them.

    Returns the single address the request must then be pinned to. Handing
    the hostname back to httpx instead would let it resolve a second time,
    and a host with a short TTL or several A records can answer the guard
    with a public IP and the client with 127.0.0.1 (DNS rebinding).
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(status_code=400, detail="Only http(s) URLs are supported")
    if not parsed.hostname:
        raise HTTPException(status_code=400, detail="URL has no host")
    try:
        ips = await asyncio.to_thread(_resolve_host_ips, parsed.hostname)
    except socket.gaierror:
        raise HTTPException(status_code=400, detail=f"Cannot resolve host: {parsed.hostname}")
    if not ips:
        raise HTTPException(status_code=400, detail=f"Cannot resolve host: {parsed.hostname}")
    # Strip any IPv6 zone id (fe80::1%eth0) before parsing.
    parsed_ips = [ipaddress.ip_address(raw.split("%")[0]) for raw in ips]
    for ip in parsed_ips:
        if not ip.is_global:
            raise HTTPException(status_code=400, detail="URL resolves to a non-public address")
    # Pinning gives up httpx's multi-address fallback, so prefer IPv4 — most
    # deployments here have no working IPv6 route.
    v4 = [ip for ip in parsed_ips if ip.version == 4]
    return str(v4[0] if v4 else parsed_ips[0])


def _pin_to_ip(url: str, ip: str) -> tuple[httpx.URL, dict, dict]:
    """Rewrite the URL to connect to `ip`, keeping the original host for
    routing (Host header) and TLS (SNI + certificate verification)."""
    parsed = httpx.URL(url)
    host = parsed.host
    authority = f"[{host}]" if ":" in host else host
    if parsed.port is not None:
        authority = f"{authority}:{parsed.port}"
    headers = {
        "Host": authority,
        # Some image hosts reject non-browser user agents.
        "User-Agent": "Mozilla/5.0 (compatible; ff-auto/1.0)",
    }
    return parsed.copy_with(host=ip), headers, {"sni_hostname": host}


async def _read_capped(resp: httpx.Response) -> bytes:
    """Buffer the body, aborting as soon as it exceeds the size limit."""
    declared = resp.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > _FETCH_IMAGE_MAX_BYTES:
        raise HTTPException(status_code=413, detail="Image exceeds the 30MB limit")
    chunks, total = [], 0
    async for chunk in resp.aiter_bytes():
        total += len(chunk)
        if total > _FETCH_IMAGE_MAX_BYTES:
            raise HTTPException(status_code=413, detail="Image exceeds the 30MB limit")
        chunks.append(chunk)
    return b"".join(chunks)


@router.post("/fetch-image")
async def fetch_image(body: FetchImageRequest, identity: Identity = Depends(get_identity)):
    """Download an image from a URL and relay the bytes.

    Dragging an image from another web page hands the browser a URL rather
    than a File, and fetching it client-side is blocked by CORS on most image
    hosts — so the frontend delegates the download to us.
    """
    url = body.url
    try:
        # Redirects are followed manually so every hop passes the SSRF guard.
        async with httpx.AsyncClient(follow_redirects=False, timeout=30.0) as http:
            for _ in range(5):
                ip = await _resolve_public_http_url(url)
                pinned, headers, extensions = _pin_to_ip(url, ip)
                # Streamed so an oversized body is cut off mid-download rather
                # than buffered in full and rejected afterwards.
                async with http.stream("GET", pinned, headers=headers, extensions=extensions) as resp:
                    if resp.is_redirect:
                        location = resp.headers.get("location")
                        if not location:
                            raise HTTPException(status_code=502, detail="Redirect without Location header")
                        url = str(httpx.URL(url).join(location))
                        continue
                    resp.raise_for_status()
                    content_type = (resp.headers.get("content-type") or "").split(";")[0].strip().lower()
                    data = await _read_capped(resp)
                break
            else:
                raise HTTPException(status_code=502, detail="Too many redirects")
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch image: {e}")
    ext = _FETCH_IMAGE_MIME_TO_EXT.get(content_type)
    if ext is None:
        # Hosts sometimes serve images as octet-stream; fall back to the URL
        # extension (of the final hop, after redirects).
        url_ext = Path(urlparse(url).path).suffix.lower()
        ext = url_ext if url_ext in _FETCH_IMAGE_EXT_TO_MIME else None
    if ext is None:
        raise HTTPException(
            status_code=415,
            detail="URL does not point to a supported image type (PNG, JPG, WEBP)",
        )
    return Response(content=data, media_type=_FETCH_IMAGE_EXT_TO_MIME[ext])


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
    project_id: Optional[str] = Query(None),
    storage: ImageLogsStorage = Depends(get_image_logs_storage),
):
    rows = storage.get_recent_executions(limit=limit, project_id=project_id)
    return rows


# ------------------------------------------------------------------
# Persona instructions — read template files for a given persona
# ------------------------------------------------------------------

@router.get("/persona-instructions/{persona_name}")
def get_persona_instructions(persona_name: str):
    from backend.config import GlobalConfig

    def read_prompt(*parts: str) -> str:
        try:
            return (Path(GlobalConfig.PROMPTS_DIR).joinpath(*parts)).read_text(encoding="utf-8")
        except Exception:
            return ""

    # Single-agent pipeline: one global system prompt drives the writer, and the
    # per-character identity lock supplies the fixed "who" injected into the prompt.
    return {
        "agent_system": read_prompt("agents", "agent_system.txt"),
        "identity_lock": read_prompt("personas", persona_name, "identity_lock.txt"),
    }



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

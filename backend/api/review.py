"""
Prompt review queue endpoints (phase 2). All generation flows through here:
rows are created by the image pipeline / the video page, edited while
pending_review, and dispatched to providers only via POST /dispatch.
"""
import io
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from backend.database.generation_requests_storage import (
    GenerationRequestsStorage,
    InvalidStateError,
)
from backend.models.review import (
    ReviewCreateRequest,
    ReviewCreateResponse,
    ReviewDispatchRequest,
    ReviewDispatchResponse,
    ReviewListResponse,
    ReviewPatchRequest,
    ReviewRequestItem,
    ReviewStatus,
)

logger = logging.getLogger(__name__)
router = APIRouter()

THUMBNAIL_SIZE = (256, 256)


@router.get("/requests", response_model=ReviewListResponse)
def list_requests(
    status: ReviewStatus | None = Query(default=None),
    batch_id: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=200),
    storage: GenerationRequestsStorage = Depends(GenerationRequestsStorage),
):
    return storage.list_requests(
        status=status, batch_id=batch_id, page=page, per_page=per_page
    )


@router.post("/requests", response_model=ReviewCreateResponse)
def create_requests(
    body: ReviewCreateRequest,
    storage: GenerationRequestsStorage = Depends(GenerationRequestsStorage),
):
    return storage.create_requests(
        [item.model_dump() for item in body.items], batch_id=body.batch_id
    )


@router.patch("/requests/{request_id}", response_model=ReviewRequestItem)
def patch_request(
    request_id: str,
    body: ReviewPatchRequest,
    storage: GenerationRequestsStorage = Depends(GenerationRequestsStorage),
):
    try:
        row = storage.update_request(
            request_id, prompt=body.prompt, settings=body.settings
        )
    except InvalidStateError as e:
        raise HTTPException(status_code=409, detail=str(e))
    if row is None:
        raise HTTPException(status_code=404, detail="Request not found")
    return row


@router.delete("/requests/{request_id}", response_model=ReviewRequestItem)
def discard_request(
    request_id: str,
    storage: GenerationRequestsStorage = Depends(GenerationRequestsStorage),
):
    try:
        row = storage.discard_request(request_id)
    except InvalidStateError as e:
        raise HTTPException(status_code=409, detail=str(e))
    if row is None:
        raise HTTPException(status_code=404, detail="Request not found")
    return row


@router.post("/dispatch", response_model=ReviewDispatchResponse)
def dispatch_requests(
    body: ReviewDispatchRequest,
    storage: GenerationRequestsStorage = Depends(GenerationRequestsStorage),
):
    from backend.tasks import dispatch_generation_request_task

    claimed = storage.claim_for_dispatch(body.ids)
    for rid in claimed:
        row = storage.get_request(rid)
        queue = "image" if row["provider"] == "comfy_image" else "video"
        dispatch_generation_request_task.apply_async(args=[rid], queue=queue)
    skipped = [i for i in body.ids if i not in set(claimed)]
    return ReviewDispatchResponse(dispatched=claimed, skipped=skipped)


@router.get("/requests/{request_id}/thumbnail")
def request_thumbnail(
    request_id: str,
    storage: GenerationRequestsStorage = Depends(GenerationRequestsStorage),
):
    """Thumbnail of the row's source image. Only the DB-stored path is ever
    opened — the client cannot supply a path, so no traversal surface."""
    from PIL import Image

    row = storage.get_request(request_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Request not found")
    source = Path(row["source_image_path"])
    if not source.is_file():
        raise HTTPException(status_code=404, detail="Source image not found")
    try:
        with Image.open(source) as img:
            img.thumbnail(THUMBNAIL_SIZE)
            buf = io.BytesIO()
            img.convert("RGB").save(buf, format="JPEG", quality=80)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Thumbnail failed: {e}")
    return Response(content=buf.getvalue(), media_type="image/jpeg")

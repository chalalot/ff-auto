"""Uploads API (phase 3 Assets tab)."""
import io
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel

from backend.api.review import _source_path_in_roots
from backend.database.uploads_storage import UploadsStorage

logger = logging.getLogger(__name__)
router = APIRouter()

THUMBNAIL_SIZE = (256, 256)


class UploadItem(BaseModel):
    id: str
    filename: str
    path: str
    kind: str
    project_id: Optional[str] = None
    created_by_member_id: Optional[str] = None
    created_at: Optional[str] = None


class UploadListResponse(BaseModel):
    items: list[UploadItem]
    total: int
    page: int
    pages: int


@router.get("", response_model=UploadListResponse)
def list_uploads(
    project_id: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=200),
):
    return UploadsStorage().list_uploads(
        project_id=project_id, page=page, per_page=per_page
    )


@router.get("/{upload_id}/thumbnail")
def upload_thumbnail(upload_id: str):
    from PIL import Image

    row = UploadsStorage().get_upload(upload_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Upload not found")
    source = _source_path_in_roots(row["path"])
    if source is None or not source.is_file():
        raise HTTPException(status_code=404, detail="Upload file not found")
    try:
        with Image.open(source) as img:
            img.thumbnail(THUMBNAIL_SIZE)
            buf = io.BytesIO()
            img.convert("RGB").save(buf, format="JPEG", quality=80)
    except Exception:
        logger.exception("Thumbnail generation failed for upload %s", upload_id)
        raise HTTPException(status_code=500, detail="Thumbnail generation failed")
    return Response(content=buf.getvalue(), media_type="image/jpeg")

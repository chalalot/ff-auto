from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response, StreamingResponse
import io

from backend.api.deps import get_gallery_service
from backend.models.gallery import (
    GalleryResponse,
    ApproveRequest,
    DisapproveRequest,
    UndoRequest,
    DownloadZipRequest,
    GalleryStats,
    NotesRequest,
    ImageMetadata,
)
from backend.services.gallery import GalleryService

router = APIRouter()


@router.get("/images", response_model=GalleryResponse)
def list_images(
    status: str = Query("pending", pattern="^(pending|approved|disapproved)$"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    persona: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None, pattern="^\\d{4}-\\d{2}-\\d{2}$"),
    date_to: Optional[str] = Query(None, pattern="^\\d{4}-\\d{2}-\\d{2}$"),
    sort: str = Query("newest", pattern="^(newest|oldest)$"),
    svc: GalleryService = Depends(get_gallery_service),
):
    return svc.list_images(
        status=status, page=page, per_page=per_page,
        persona=persona, search=search,
        date_from=date_from, date_to=date_to, sort=sort,
    )


@router.get("/personas", response_model=List[str])
def gallery_personas(svc: GalleryService = Depends(get_gallery_service)):
    return svc.get_available_personas()


@router.get("/images/{filename}/thumbnail")
def image_thumbnail(
    filename: str,
    status: str = Query("pending", pattern="^(pending|approved|disapproved)$"),
    svc: GalleryService = Depends(get_gallery_service),
):
    data = svc.get_thumbnail(filename, status=status)
    if not data:
        raise HTTPException(status_code=404, detail="Image not found")
    return Response(content=data, media_type="image/jpeg")


@router.get("/images/{filename}/metadata", response_model=ImageMetadata)
def image_metadata(
    filename: str,
    status: str = Query("pending", pattern="^(pending|approved|disapproved)$"),
    svc: GalleryService = Depends(get_gallery_service),
):
    return svc.extract_metadata(filename, status=status)


@router.get("/images/{filename}/ref-image")
def image_ref(
    filename: str,
    status: str = Query("pending", pattern="^(pending|approved|disapproved)$"),
    svc: GalleryService = Depends(get_gallery_service),
):
    data = svc.get_ref_image(filename, status=status)
    if not data:
        raise HTTPException(status_code=404, detail="Reference image not found")
    return Response(content=data, media_type="image/jpeg")


@router.get("/download/{filename}")
def download_image(
    filename: str,
    status: str = Query("pending", pattern="^(pending|approved|disapproved)$"),
    svc: GalleryService = Depends(get_gallery_service),
):
    path = svc._dir_for_status(status) / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="Image not found")
    return Response(content=path.read_bytes(), media_type="image/png",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.post("/approve")
def approve_images(body: ApproveRequest, svc: GalleryService = Depends(get_gallery_service)):
    return svc.approve_images(body.filenames, rename_map=body.rename_map)


@router.post("/disapprove")
def disapprove_images(body: DisapproveRequest, svc: GalleryService = Depends(get_gallery_service)):
    return svc.disapprove_images(body.filenames)


@router.post("/undo")
def undo_action(body: UndoRequest, svc: GalleryService = Depends(get_gallery_service)):
    return svc.undo_action(body.filenames, body.from_status)


@router.get("/stats", response_model=GalleryStats)
def gallery_stats(svc: GalleryService = Depends(get_gallery_service)):
    return svc.get_stats()


@router.post("/download-zip")
def download_zip(body: DownloadZipRequest, svc: GalleryService = Depends(get_gallery_service)):
    try:
        data = svc.build_zip(filenames=body.filenames, date=body.date)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    fname = f"approved_{body.date}.zip" if body.date else "images.zip"
    return Response(
        content=data,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.get("/notes")
def get_notes(svc: GalleryService = Depends(get_gallery_service)):
    return svc.load_notes()


@router.put("/notes")
def save_note(body: NotesRequest, svc: GalleryService = Depends(get_gallery_service)):
    ok = svc.save_note(body.date, body.text)
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to save note")
    return {"ok": True}

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from backend.api.deps import get_archive_service
from backend.services.archive import ArchiveService

router = APIRouter()


@router.get("/servers")
def list_servers(svc: ArchiveService = Depends(get_archive_service)):
    """List available archive server names."""
    return {"servers": svc.list_servers()}


@router.get("/list")
def list_archive(
    server: Optional[str] = Query(None, description="Filter by server name"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    svc: ArchiveService = Depends(get_archive_service),
):
    """Paginated list of result images from archive directories."""
    return svc.list_images(server=server, page=page, per_page=per_page)


@router.get("/thumbnail")
def archive_thumbnail(
    server: str = Query(...),
    filename: str = Query(...),
    svc: ArchiveService = Depends(get_archive_service),
):
    """Serve a 512x512 JPEG thumbnail for an archive result image."""
    data = svc.get_thumbnail(server, filename)
    if not data:
        raise HTTPException(status_code=404, detail="Image not found")
    return Response(content=data, media_type="image/jpeg")


@router.get("/metadata")
def archive_metadata(
    server: str = Query(...),
    filename: str = Query(...),
    svc: ArchiveService = Depends(get_archive_service),
):
    """Extract ComfyUI metadata (seed, prompt) from an archive result image."""
    return svc.extract_metadata(server, filename)


@router.get("/ref-image")
def archive_ref_image(
    server: str = Query(...),
    filename: str = Query(...),
    svc: ArchiveService = Depends(get_archive_service),
):
    """Serve the reference/processed image paired with a result image."""
    data = svc.get_ref_image(server, filename)
    if not data:
        raise HTTPException(status_code=404, detail="Reference image not found")
    return Response(content=data, media_type="image/jpeg")


@router.get("/image")
def archive_image(
    server: str = Query(...),
    filename: str = Query(...),
    svc: ArchiveService = Depends(get_archive_service),
):
    """Download the full-resolution archive result image."""
    data = svc.get_image(server, filename)
    if not data:
        raise HTTPException(status_code=404, detail="Image not found")
    return Response(
        content=data,
        media_type="image/png",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

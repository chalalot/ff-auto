from typing import List, Optional, Dict
from pydantic import BaseModel


class ImageItem(BaseModel):
    filename: str
    path: str
    thumbnail_url: str
    created_at: float
    date: str
    metadata: Optional[dict] = None


class GalleryResponse(BaseModel):
    items: List[ImageItem]
    total: int
    page: int
    pages: int
    per_page: int


class ApproveRequest(BaseModel):
    filenames: List[str]
    rename_map: Dict[str, str] = {}


class DisapproveRequest(BaseModel):
    filenames: List[str]


class UndoRequest(BaseModel):
    filenames: List[str]
    from_status: str  # "approved" | "disapproved"


class DownloadZipRequest(BaseModel):
    filenames: Optional[List[str]] = None
    date: Optional[str] = None  # "YYYY-MM-DD" — download all for that date


class GalleryStats(BaseModel):
    daily: List[dict]
    totals: dict


class NotesRequest(BaseModel):
    date: str
    text: str


class ImageMetadata(BaseModel):
    seed: Optional[int] = None
    prompt: Optional[str] = None
    raw_metadata: dict = {}

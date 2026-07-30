from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field

Provider = Literal["kling", "comfy_video", "comfy_image"]
ReviewStatus = Literal[
    "pending_review", "approved", "dispatched", "completed", "failed", "discarded"
]


class ReviewItemCreate(BaseModel):
    source_image_path: str
    prompt: str
    provider: Provider
    workflow_name: Optional[str] = None
    settings: Dict = Field(default_factory=dict)


class ReviewCreateRequest(BaseModel):
    items: List[ReviewItemCreate] = Field(min_length=1)
    batch_id: Optional[str] = None


class ReviewCreateResponse(BaseModel):
    batch_id: str
    request_ids: List[str]


class ReviewRequestItem(BaseModel):
    id: str
    batch_id: str
    source_image_path: str
    original_prompt: str
    prompt: str
    provider: str
    workflow_name: Optional[str] = None
    settings: Dict = Field(default_factory=dict)
    status: str
    execution_id: Optional[str] = None
    result_path: Optional[str] = None
    error: Optional[str] = None
    project_id: Optional[str] = None
    created_by_member_id: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    # "<node_id>.<input_key>" for saved overrides the current workflow JSON no
    # longer accepts — these are dropped silently at dispatch. Computed per
    # response against the workflow on disk, never persisted.
    stale_overrides: List[str] = Field(default_factory=list)


class ReviewListResponse(BaseModel):
    items: List[ReviewRequestItem]
    total: int
    page: int
    pages: int
    # Rows per status across the whole queue (project/batch scope applies, the
    # `status` filter and pagination do not) — the Flow rail's stage counters
    # read this instead of counting the returned page. Statuses with no rows
    # are absent.
    status_counts: Dict[str, int] = Field(default_factory=dict)


class ReviewPatchRequest(BaseModel):
    prompt: Optional[str] = None
    settings: Optional[Dict] = None


class ReviewDispatchRequest(BaseModel):
    ids: List[str] = Field(min_length=1)


class ReviewRedispatchBulkRequest(BaseModel):
    ids: List[str] = Field(min_length=1)


class ReviewDispatchResponse(BaseModel):
    dispatched: List[str]
    skipped: List[str]

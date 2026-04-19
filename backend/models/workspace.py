from typing import List, Optional
from pydantic import BaseModel, Field


class InputImage(BaseModel):
    filename: str
    path: str
    size_bytes: int
    modified_at: float
    thumbnail_url: str


class RefImage(BaseModel):
    filename: str
    path: str
    size_bytes: int
    modified_at: float
    thumbnail_url: str
    use_count: int
    is_used: bool


class ProcessImageRequest(BaseModel):
    image_path: str
    skip_prepare: bool = False  # True when image_path is already in PROCESSED_DIR
    persona: str
    workflow_type: str = "turbo"
    vision_model: str = "gpt-4o"
    variation_count: int = Field(default=1, ge=1, le=5)
    strength: float = Field(default=0.8, ge=0.0, le=2.0)
    seed_strategy: str = "random"
    base_seed: int = 0
    width: int = 1024
    height: int = 1600
    lora_name: str = ""
    clip_model_type: str = "sd3"


class ProcessBatchRequest(BaseModel):
    image_paths: List[str]
    skip_prepare: bool = False
    persona: str
    workflow_type: str = "turbo"
    vision_model: str = "gpt-4o"
    variation_count: int = Field(default=1, ge=1, le=5)
    strength: float = Field(default=0.8, ge=0.0, le=2.0)
    seed_strategy: str = "random"
    base_seed: int = 0
    width: int = 1024
    height: int = 1600
    lora_name: str = ""
    clip_model_type: str = "sd3"


class TaskStatusResponse(BaseModel):
    task_id: str
    state: str
    status_message: str = ""
    progress: int = 0
    result: Optional[dict] = None


class DispatchResponse(BaseModel):
    task_id: str


class BatchDispatchResponse(BaseModel):
    task_ids: List[str]


class ComfyUIQueueStatus(BaseModel):
    running: List[dict]
    pending: List[dict]
    counts: dict


class ExecutionRecord(BaseModel):
    id: int
    execution_id: str
    prompt: str
    persona: Optional[str]
    image_ref_path: Optional[str]
    result_image_path: Optional[str]
    status: str
    created_at: str


class CaptionExportEntry(BaseModel):
    stem: str          # original filename stem (e.g. "image_1")
    path: str          # absolute path in PROCESSED_DIR
    original_ext: str  # original file extension (e.g. ".jpg")


class CaptionExportUploadResponse(BaseModel):
    entries: List[CaptionExportEntry]


class CaptionExportRequest(BaseModel):
    image_entries: List[CaptionExportEntry]
    persona: str
    vision_model: str = "gpt-4o"
    workflow_type: str = "turbo"


class GDriveFetchRequest(BaseModel):
    folder_url: str
    max_dimension: int = 1024  # Pillow thumbnail max side in pixels


class GDriveUploadZipRequest(BaseModel):
    task_id: str
    folder_url: str


class RunpodJobInput(BaseModel):
    dataset_source: str
    lora_name: str
    steps: int = 2000
    save_every: int = 500
    sample_every: int = 500
    sample_prompts: List[str] = []


class RunpodSubmitRequest(BaseModel):
    job_input: RunpodJobInput
    endpoint_id: Optional[str] = None  # overrides RUNPOD_ENDPOINT_ID env var

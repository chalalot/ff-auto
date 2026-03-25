from typing import List, Optional
from pydantic import BaseModel, Field


class InputImage(BaseModel):
    filename: str
    path: str
    size_bytes: int
    modified_at: float
    thumbnail_url: str


class ProcessImageRequest(BaseModel):
    image_path: str
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

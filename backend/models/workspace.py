from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, model_validator


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
    image_path: Optional[str] = None  # None → brief-only headless (S13)
    skip_prepare: bool = False  # True when image_path is already in PROCESSED_DIR
    persona: str
    workflow_type: str = "image_generation"
    vision_model: str = "gpt-4o"
    variation_count: int = Field(default=1, ge=1, le=5)
    width: int = 1024
    height: int = 1600
    # Which image generation pipeline builds the ComfyUI workflow.
    # See backend.pipelines; default preserves the auto-split behaviour.
    pipeline_type: str = "image.subject_environment"
    # Per-run node-input overrides: { node_id: { input_key: value } }.
    # Seeds, LoRA, dimensions, CLIP type are all edited through these.
    workflow_overrides: Dict[str, Dict[str, Any]] = {}
    # Which workflows/*.json graph to build from (default: workflow.json).
    workflow_name: Optional[str] = None
    # Optional creative brief steering the analyst (image + brief). See A12.
    brief: Optional[str] = None

    @model_validator(mode="after")
    def _require_image_or_brief(self):
        if not (self.image_path or (self.brief and self.brief.strip())):
            raise ValueError("at least one of `image_path` or `brief` is required")
        return self


class ProcessBatchRequest(BaseModel):
    image_paths: List[str]
    skip_prepare: bool = False
    persona: str
    workflow_type: str = "image_generation"
    vision_model: str = "gpt-4o"
    variation_count: int = Field(default=1, ge=1, le=5)
    width: int = 1024
    height: int = 1600
    pipeline_type: str = "image.subject_environment"
    workflow_overrides: Dict[str, Dict[str, Any]] = {}
    workflow_name: Optional[str] = None


class RunWorkflowDirectRequest(BaseModel):
    """Direct ComfyUI submission — no prompt-writing agent, no review queue.

    Used by the Image Upscaler and Multiangle-Edit workflow types, by Image
    Generation I2I when the user supplies the prompt text themselves, and by
    Image Generation T2I, where the prompt is the whole input. An image (when
    given) is uploaded to ComfyUI and patched into the LoadImage node;
    ``prompt`` (when given) is patched into the CLIPTextEncode node if the
    graph has one. Everything else is edited via ``workflow_overrides``.
    """

    # Empty for text-to-image: a T2I graph has no LoadImage node, so there is
    # nothing to select and one run is dispatched rather than one per image.
    image_paths: List[str] = []
    workflow_name: str
    workflow_type: str = "image_upscaler"
    prompt: Optional[str] = None
    workflow_overrides: Dict[str, Dict[str, Any]] = {}

    @model_validator(mode="after")
    def _require_image_or_prompt(self):
        # Neither an image nor a prompt means the request carries no input at
        # all — previously impossible (image_paths had min_length=1), and worth
        # rejecting loudly rather than silently queueing the bare graph.
        if not self.image_paths and not (self.prompt and self.prompt.strip()):
            raise ValueError("at least one of `image_paths` or `prompt` is required")
        return self


class TaskStatusResponse(BaseModel):
    task_id: str
    state: str
    status_message: str = ""
    progress: int = 0
    result: Optional[dict] = None


class DispatchResponse(BaseModel):
    task_id: str
    run_id: Optional[str] = None


class BatchDispatchResponse(BaseModel):
    task_ids: List[str]
    run_ids: List[Optional[str]] = []


class PipelineInfo(BaseModel):
    pipeline_type: str
    media_type: str
    label: str
    available: bool


class WorkflowParamInput(BaseModel):
    key: str
    value: Any = None
    type: str
    locked: bool = False
    locked_reason: Optional[str] = None


class WorkflowParamNode(BaseModel):
    node_id: str
    class_type: str
    title: str
    inputs: List[WorkflowParamInput]


class WorkflowParametersResponse(BaseModel):
    pipeline_type: str
    nodes: List[WorkflowParamNode]


class WorkflowFileParametersResponse(BaseModel):
    workflow: str
    nodes: List[WorkflowParamNode]


class WorkflowSummary(BaseModel):
    """One workflow file as the management list shows it.

    ``valid`` is False for files that fail JSON parsing or API-format
    validation; they stay listed (with ``error``) so they can be repaired.
    """

    name: str
    node_count: int
    size_bytes: int
    modified_at: float
    valid: bool
    error: Optional[str] = None


class WorkflowGraphResponse(BaseModel):
    """A workflow opened for editing.

    ``raw`` is always the file's text so the JSON editor can open (and repair)
    a file that doesn't parse; ``graph`` is populated only when it validates,
    and ``error`` explains why it didn't.
    """

    name: str
    raw: str
    graph: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class WorkflowCreateRequest(BaseModel):
    name: str
    # Omitted → a minimal valid starter graph (see workflow_library.blank_graph).
    graph: Optional[Dict[str, Any]] = None


class WorkflowSaveRequest(BaseModel):
    graph: Dict[str, Any]


class WorkflowRenameRequest(BaseModel):
    new_name: str


class WorkflowDuplicateRequest(BaseModel):
    # Omitted → "<name> copy.json", auto-incremented on collision.
    new_name: Optional[str] = None


class WorkflowMutationResponse(BaseModel):
    """The resulting filename — the server may adjust it (suffix, collision)."""

    name: str


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
    workflow_type: str = "image_generation"


class GDriveFetchRequest(BaseModel):
    folder_url: str
    max_dimension: int = 1024  # Pillow thumbnail max side in pixels


class GDriveUploadZipRequest(BaseModel):
    task_id: str


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


class ManualExportToDriveRequest(BaseModel):
    entries: List[CaptionExportEntry]
    captions: Dict[str, str]  # stem → caption text


class ActiveTask(BaseModel):
    task_id: str
    state: str
    status_message: str = ""
    progress: float = 0
    image_path: Optional[str] = None
    run_id: Optional[str] = None
    persona: str = ""
    dispatched_at: Optional[float] = None
    task_type: str = "image_process"   # "image_process" | "caption_export"
    image_count: Optional[int] = None  # for caption_export tasks

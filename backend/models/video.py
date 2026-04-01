from typing import List, Optional
from pydantic import BaseModel, Field


class KlingSettings(BaseModel):
    model_name: str = "kling-v1.6"
    mode: str = "std"  # "std" or "pro"
    duration: str = "5"  # "5" or "10"
    aspect_ratio: str = "16:9"
    cfg_scale: float = Field(default=0.5, ge=0.0, le=1.0)
    negative_prompt: Optional[str] = None
    sound: Optional[str] = None  # "on" or "off"
    voice_list: Optional[List[str]] = None


class VideoGenerateRequest(BaseModel):
    image_path: str
    prompt: Optional[str] = None
    kling_settings: KlingSettings = Field(default_factory=KlingSettings)
    batch_id: Optional[str] = None


class VideoGenerateResponse(BaseModel):
    task_id: str
    batch_id: Optional[str] = None
    status: str = "pending"


class VideoBatchItem(BaseModel):
    image_path: str
    prompt: Optional[str] = None
    variation_count: int = Field(default=1, ge=1, le=5)


class VideoBatchRequest(BaseModel):
    items: List[VideoBatchItem]
    kling_settings: KlingSettings = Field(default_factory=KlingSettings)


class VideoBatchResponse(BaseModel):
    batch_id: str
    task_ids: List[str]


class VideoStatusResponse(BaseModel):
    task_id: str
    status: str
    progress: int = 0
    video_url: Optional[str] = None
    local_path: Optional[str] = None
    duration: Optional[str] = None


class VideoItem(BaseModel):
    id: int
    execution_id: str
    filename: Optional[str] = None
    source_image: Optional[str] = None
    prompt: str
    status: str
    created_at: str
    batch_id: Optional[str] = None
    video_url: Optional[str] = None
    thumbnail_url: Optional[str] = None


class VideoListResponse(BaseModel):
    items: List[VideoItem]
    total: int
    page: int
    pages: int


class VideoMergeRequest(BaseModel):
    filenames: List[str]
    transition_type: str = "Crossfade"
    transition_duration: float = Field(default=0.5, ge=0.0, le=2.0)


class VideoMergeResponse(BaseModel):
    task_id: str
    output_filename: str


class MusicAnalysisRequest(BaseModel):
    audio_path: str


class MusicAnalysisResponse(BaseModel):
    vibe: str
    lyrics: str
    analysis: Optional[str] = None


class StoryboardRequest(BaseModel):
    image_paths: List[str]
    vision_model: str = "gpt-4o"
    persona: str = "default"
    variation_count: int = Field(default=3, ge=1, le=5)


class StoryboardVariation(BaseModel):
    variation: int
    concept_name: str
    prompt: str


class StoryboardResult(BaseModel):
    source_image: str
    persona: str
    variations: List[StoryboardVariation]


class StoryboardResponse(BaseModel):
    results: List[StoryboardResult]


class KlingPreset(BaseModel):
    name: str
    settings: KlingSettings

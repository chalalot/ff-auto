from typing import Optional
from pydantic import BaseModel


class PersonaSummary(BaseModel):
    name: str


class PresetConfig(BaseModel):
    name: str
    data: dict


class LastUsedConfig(BaseModel):
    persona: str = ""
    workflow_type: str = "image_generation"
    workflow_name: str = ""
    vision_model: str = "gpt-4o"
    variations: int = 1
    width: int = 1024
    height: int = 1600
    batch_limit: Optional[int] = None

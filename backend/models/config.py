from typing import List, Optional
from pydantic import BaseModel


class PersonaSummary(BaseModel):
    name: str
    type: str
    hair_color: str
    hairstyles: List[str]


class PersonaUpdateRequest(BaseModel):
    type: Optional[str] = None
    hair_color: Optional[str] = None
    hairstyles: Optional[List[str]] = None


class PresetConfig(BaseModel):
    name: str
    data: dict


class LastUsedConfig(BaseModel):
    persona: str = ""
    workflow_type: str = "turbo"
    vision_model: str = "gpt-4o"
    clip_model_type: str = "sd3"
    variations: int = 1
    strength: float = 0.8
    width: int = 1024
    height: int = 1600
    seed_strategy: str = "random"
    base_seed: int = 0
    lora_name: str = ""
    batch_limit: Optional[int] = None

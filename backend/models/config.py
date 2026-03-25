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
    kol_persona: str = "Jennie"
    workflow_choice: str = "Turbo"
    vision_model_choice: str = "ChatGPT (gpt-4o)"
    clip_model_type: str = "sd3"
    limit_choice: int = 10
    variation_count: int = 1
    strength_model: float = 0.8
    width: str = "1024"
    height: str = "1600"
    seed_strategy: str = "random"
    base_seed: int = 0
    lora_name_override: str = ""
    persona_config_select: str = "Jennie"
    editor_type_select: str = "instagirl"

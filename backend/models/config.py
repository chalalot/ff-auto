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
    # Image Generation is nested: "i2i" starts from a source image, "t2i" from
    # the prompt alone. Unknown to the other workflow types, which always need
    # an image. Listed here because the PUT is typed — a field missing from this
    # model is silently dropped on save.
    generation_mode: str = "i2i"
    # T2I only: run the typed prompt through the prompt agent before generating.
    enhance_prompt: bool = False
    workflow_name: str = ""
    vision_model: str = "gpt-4o"
    variations: int = 1
    width: int = 1024
    height: int = 1600
    batch_limit: Optional[int] = None

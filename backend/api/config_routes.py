from typing import Dict, List

from fastapi import APIRouter, Body, Depends, HTTPException

from backend.api.deps import get_config_service
from backend.models.config import PersonaSummary, PersonaUpdateRequest, PresetConfig, LastUsedConfig
from backend.services.config import ConfigService

router = APIRouter()


@router.get("/personas", response_model=List[PersonaSummary])
def list_personas(svc: ConfigService = Depends(get_config_service)):
    return svc.list_personas()


@router.get("/personas/{name}", response_model=PersonaSummary)
def get_persona(name: str, svc: ConfigService = Depends(get_config_service)):
    persona = svc.get_persona(name)
    if not persona:
        raise HTTPException(status_code=404, detail=f"Persona '{name}' not found")
    return persona


@router.put("/personas/{name}")
def update_persona(name: str, body: PersonaUpdateRequest, svc: ConfigService = Depends(get_config_service)):
    ok = svc.update_persona(name, body.model_dump(exclude_none=True))
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to update persona")
    return {"ok": True}


@router.get("/presets", response_model=List[str])
def list_presets(svc: ConfigService = Depends(get_config_service)):
    return svc.list_presets()


# NOTE: _last_used routes must be declared BEFORE /presets/{name} so the
# literal path takes priority over the wildcard in FastAPI's route matching.

@router.get("/presets/_last_used")
def get_last_used(svc: ConfigService = Depends(get_config_service)):
    return svc.get_last_used()


@router.put("/presets/_last_used")
def save_last_used(body: LastUsedConfig, svc: ConfigService = Depends(get_config_service)):
    ok = svc.save_last_used(body.model_dump())
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to save last-used config")
    return {"ok": True}


@router.get("/presets/{name}")
def get_preset(name: str, svc: ConfigService = Depends(get_config_service)):
    data = svc.get_preset(name)
    if data is None:
        raise HTTPException(status_code=404, detail=f"Preset '{name}' not found")
    return data


@router.post("/presets/{name}")
def save_preset(name: str, body: PresetConfig, svc: ConfigService = Depends(get_config_service)):
    ok = svc.save_preset(name, body.data)
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to save preset")
    return {"ok": True}


@router.delete("/presets/{name}")
def delete_preset(name: str, svc: ConfigService = Depends(get_config_service)):
    ok = svc.delete_preset(name)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Preset '{name}' not found")
    return {"ok": True}


@router.get("/workflow-types", response_model=List[str])
def workflow_types(svc: ConfigService = Depends(get_config_service)):
    return svc.get_workflow_types()


@router.get("/vision-models")
def vision_models(svc: ConfigService = Depends(get_config_service)):
    return svc.get_vision_models()


@router.get("/clip-model-types", response_model=List[str])
def clip_model_types(svc: ConfigService = Depends(get_config_service)):
    return svc.get_clip_model_types()


@router.get("/lora-options", response_model=List[str])
def lora_options(svc: ConfigService = Depends(get_config_service)):
    return svc.get_lora_options()


@router.get("/persona-types", response_model=List[str])
def persona_types(svc: ConfigService = Depends(get_config_service)):
    return svc.get_persona_types()


# ------------------------------------------------------------------
# Template file editor
# ------------------------------------------------------------------

@router.get("/templates", response_model=List[str])
def list_templates(svc: ConfigService = Depends(get_config_service)):
    return svc.list_template_types()


@router.get("/templates/{type_name}", response_model=Dict[str, str])
def get_template(type_name: str, svc: ConfigService = Depends(get_config_service)):
    types = svc.list_template_types()
    if type_name not in types:
        raise HTTPException(status_code=404, detail=f"Template type '{type_name}' not found")
    return svc.get_template_files(type_name)


@router.put("/templates/{type_name}/{filename}")
def save_template(
    type_name: str,
    filename: str,
    content: str = Body(..., media_type="text/plain"),
    svc: ConfigService = Depends(get_config_service),
):
    ok = svc.save_template_file(type_name, filename, content)
    if not ok:
        raise HTTPException(status_code=400, detail=f"Invalid filename '{filename}'")
    return {"ok": True}

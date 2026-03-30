"""
ConfigService — extracted from WorkflowConfigManager + 1_workspace_app.py preset logic.

Handles: persona CRUD, preset CRUD, last-used sticky config.
"""
import json
import logging
import os
from pathlib import Path
from typing import Dict, List, Optional

from backend.config import GlobalConfig
from backend.workflows.config_manager import WorkflowConfigManager

logger = logging.getLogger(__name__)


class ConfigService:
    def __init__(self):
        self.prompts_dir = Path(GlobalConfig.PROMPTS_DIR)
        self.presets_dir = self.prompts_dir / "presets"
        self.presets_dir.mkdir(parents=True, exist_ok=True)
        self._config_manager = WorkflowConfigManager()

    # ------------------------------------------------------------------
    # Personas
    # ------------------------------------------------------------------

    def list_personas(self) -> List[dict]:
        names = self._config_manager.get_personas()
        result = []
        for name in names:
            cfg = self._config_manager.get_persona_config(name)
            result.append(
                {
                    "name": name,
                    "type": cfg.get("type", "instagirl"),
                    "hair_color": cfg.get("hair_color", ""),
                    "hairstyles": cfg.get("hairstyles", []),
                }
            )
        return result

    def get_persona(self, name: str) -> Optional[dict]:
        personas = self._config_manager.get_personas()
        if name not in personas:
            return None
        cfg = self._config_manager.get_persona_config(name)
        return {"name": name, **cfg}

    def update_persona(self, name: str, data: dict) -> bool:
        try:
            self._config_manager.update_persona_config(name, data)
            return True
        except Exception as e:
            logger.error(f"Failed to update persona {name}: {e}")
            return False

    def get_persona_types(self) -> List[str]:
        return self._config_manager.get_persona_types()

    def create_persona_type(self, type_name: str) -> bool:
        try:
            return self._config_manager.create_persona_template_structure(type_name)
        except Exception as e:
            logger.error(f"Failed to create persona type {type_name}: {e}")
            return False

    # ------------------------------------------------------------------
    # Presets
    # ------------------------------------------------------------------

    def list_presets(self) -> List[str]:
        if not self.presets_dir.exists():
            return []
        return [
            f.stem
            for f in self.presets_dir.iterdir()
            if f.suffix == ".json" and not f.name.startswith("_")
        ]

    def get_preset(self, name: str) -> Optional[dict]:
        path = self.presets_dir / f"{name}.json"
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text())
        except Exception as e:
            logger.error(f"Failed to load preset {name}: {e}")
            return None

    def save_preset(self, name: str, data: dict) -> bool:
        path = self.presets_dir / f"{name}.json"
        try:
            path.write_text(json.dumps(data, indent=4))
            return True
        except Exception as e:
            logger.error(f"Failed to save preset {name}: {e}")
            return False

    def delete_preset(self, name: str) -> bool:
        path = self.presets_dir / f"{name}.json"
        if not path.exists():
            return False
        path.unlink()
        return True

    # ------------------------------------------------------------------
    # Last-used sticky config
    # ------------------------------------------------------------------

    def get_last_used(self) -> dict:
        return self.get_preset("_last_used") or {}

    def save_last_used(self, data: dict) -> bool:
        return self.save_preset("_last_used", data)

    # ------------------------------------------------------------------
    # Template files (prompts/templates/{type}/*.txt)
    # ------------------------------------------------------------------

    TEMPLATE_FILES = [
        "turbo_agent.txt",
        "turbo_framework.txt",
        "turbo_constraints.txt",
        "turbo_example.txt",
        "analyst_agent.txt",
        "analyst_task.txt",
    ]

    def list_template_types(self) -> List[str]:
        templates_dir = self.prompts_dir / "templates"
        if not templates_dir.exists():
            return []
        return sorted(d.name for d in templates_dir.iterdir() if d.is_dir())

    def get_template_files(self, type_name: str) -> Dict[str, str]:
        """Return {filename: content} for all template files of a type."""
        template_dir = self.prompts_dir / "templates" / type_name
        result = {}
        for filename in self.TEMPLATE_FILES:
            path = template_dir / filename
            try:
                result[filename] = path.read_text(encoding="utf-8") if path.exists() else ""
            except Exception as e:
                logger.error(f"Failed to read {path}: {e}")
                result[filename] = ""
        return result

    def save_template_file(self, type_name: str, filename: str, content: str) -> bool:
        if filename not in self.TEMPLATE_FILES:
            return False
        template_dir = self.prompts_dir / "templates" / type_name
        template_dir.mkdir(parents=True, exist_ok=True)
        try:
            (template_dir / filename).write_text(content, encoding="utf-8")
            return True
        except Exception as e:
            logger.error(f"Failed to write template {type_name}/{filename}: {e}")
            return False

    # ------------------------------------------------------------------
    # Static option lists (replaces Streamlit selectbox values)
    # ------------------------------------------------------------------

    def get_workflow_types(self) -> List[str]:
        return ["turbo", "standard"]

    def get_vision_models(self) -> List[Dict[str, str]]:
        return [
            {"label": "ChatGPT (gpt-4o)", "value": "gpt-4o"},
            {"label": "Grok (grok-4-1-fast-non-reasoning)", "value": "grok-4-1-fast-non-reasoning"},
            {"label": "Gemini 3 Flash (gemini-3-flash-preview)", "value": "gemini-3-flash-preview"},
        ]

    def get_clip_model_types(self) -> List[str]:
        return [
            "stable_diffusion", "stable_cascade", "sd3", "stable_audio", "mochi",
            "ltxv", "pixart", "cosmos", "lumina2", "wan", "hidream", "chroma",
            "ace", "omnigen2", "qwen_image", "hunyuan_image", "flux2", "ovis", "longcat_image",
        ]

    def get_lora_options(self) -> List[str]:
        return [
            "khiemle__xz-comfy__jennie_turbo_v4.safetensors",
            "khiemle__xz-comfy__jennie_turbo_outdoor_v1.safetensors",
            "khiemle__xz-comfy__jennie_turbo_indoor_v1.safetensors",
            "khiemle__xz-comfy__jennie_turbo_selfie_v2.safetensors",
            "khiemle__xz-comfy__sephera_turbo_v6.safetensors",
            "khiemle__xz-comfy__sephera_turbo_v2_gymer.safetensors",
            "khiemle__xz-comfy__emi_turbo_v2.safetensors",
            "Macincesht__ff-loras__emi_v3.safetensors",
            "khiemle__xz-comfy__roxie_v3.safetensors",
            "khiemle__xz-comfy__roxie_v4_000001250.safetensors",
            "khiemle__xz-comfy__Sephera%20v7.safetensors",
        ]

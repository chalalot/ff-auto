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
        # Personas resolve through the config manager (lazy PROMPTS_DIR) so that
        # listing, reading, and writing identity locks always share one directory.
        self.personas_dir = Path(self._config_manager.PERSONAS_DIR)

    # ------------------------------------------------------------------
    # Personas
    # ------------------------------------------------------------------

    def list_personas(self) -> List[dict]:
        """Return the character roster — just names now."""
        return [{"name": name} for name in self._config_manager.get_personas()]

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
    # Character identity locks (prompts/personas/{name}/identity_lock.txt)
    # ------------------------------------------------------------------
    # Each character has one preset "identity lock" — the fixed user-prompt text
    # describing WHO the subject is. It is injected verbatim into every generated
    # prompt. This replaces the old per-type persona_contract templates.

    def get_identity_locks(self) -> Dict[str, str]:
        """Return {persona_name: identity_lock_content} for every character."""
        result = {}
        for name in self._config_manager.get_personas():
            path = self.personas_dir / name / "identity_lock.txt"
            try:
                result[name] = path.read_text(encoding="utf-8") if path.exists() else ""
            except Exception as e:
                logger.error(f"Failed to read {path}: {e}")
                result[name] = ""
        return result

    def save_identity_lock(self, name: str, content: str) -> bool:
        if name not in self._config_manager.get_personas():
            return False
        persona_dir = self.personas_dir / name
        persona_dir.mkdir(parents=True, exist_ok=True)
        try:
            (persona_dir / "identity_lock.txt").write_text(content, encoding="utf-8")
            return True
        except Exception as e:
            logger.error(f"Failed to write identity lock for {name}: {e}")
            return False

    # ------------------------------------------------------------------
    # Global agent prompts (prompts/agents/*.txt) — the single system prompt
    # and its task template, shared across every persona.
    # ------------------------------------------------------------------

    AGENT_PROMPT_FILES = [
        "agent_system.txt",
        "agent_instruction.txt",
        # Mode directives substituted into {{MODE_DIRECTIVE}} in the instruction.
        "mode_image_directive.txt",
        "mode_brief_directive.txt",
    ]

    def get_agent_prompts(self) -> Dict[str, str]:
        """Return {filename: content} for the global agent prompts."""
        agents_dir = self.prompts_dir / "agents"
        result = {}
        for filename in self.AGENT_PROMPT_FILES:
            path = agents_dir / filename
            try:
                result[filename] = path.read_text(encoding="utf-8") if path.exists() else ""
            except Exception as e:
                logger.error(f"Failed to read {path}: {e}")
                result[filename] = ""
        return result

    def save_agent_prompt(self, filename: str, content: str) -> bool:
        if filename not in self.AGENT_PROMPT_FILES:
            return False
        agents_dir = self.prompts_dir / "agents"
        agents_dir.mkdir(parents=True, exist_ok=True)
        try:
            (agents_dir / filename).write_text(content, encoding="utf-8")
            return True
        except Exception as e:
            logger.error(f"Failed to write agent prompt {filename}: {e}")
            return False

    # ------------------------------------------------------------------
    # Selector option lists (prompts/options.json)
    # ------------------------------------------------------------------
    # The lists live in prompts/options.json — the prompts dir is bind-mounted,
    # so edits take effect without a rebuild or restart. The constants below are
    # fallbacks for a missing/broken file, and the seed for the repo copy.

    _DEFAULT_WORKFLOW_TYPES = ["image_generation", "image_upscaler", "multiangle_edit"]

    _DEFAULT_VISION_MODELS = [
        {"label": "ChatGPT (gpt-4o)", "value": "gpt-4o"},
        {"label": "Grok (grok-4.3)", "value": "grok-4.3"},
        {"label": "Gemini 2.5 Pro (gemini-2.5-pro)", "value": "gemini-2.5-pro"},
        {"label": "Gemma 4 31B IT (gemma-4-31b-it)", "value": "gemma-4-31b-it"},
    ]

    _DEFAULT_CLIP_MODEL_TYPES = [
        "stable_diffusion", "stable_cascade", "sd3", "stable_audio", "mochi",
        "ltxv", "pixart", "cosmos", "lumina2", "wan", "hidream", "chroma",
        "ace", "omnigen2", "qwen_image", "hunyuan_image", "flux2", "ovis", "longcat_image",
    ]

    @property
    def _options_file(self) -> Path:
        return self.prompts_dir / "options.json"

    def _load_options(self) -> dict:
        if not self._options_file.exists():
            return {}
        try:
            data = json.loads(self._options_file.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception as e:
            logger.error(f"Failed to load {self._options_file}: {e}")
            return {}

    def _option_list(self, key: str, default: list) -> list:
        value = self._load_options().get(key)
        if isinstance(value, list) and value:
            return value
        return default

    def get_workflow_types(self) -> List[str]:
        return self._option_list("workflow_types", self._DEFAULT_WORKFLOW_TYPES)

    def get_vision_models(self) -> List[Dict[str, str]]:
        return self._option_list("vision_models", self._DEFAULT_VISION_MODELS)

    def get_clip_model_types(self) -> List[str]:
        return self._option_list("clip_model_types", self._DEFAULT_CLIP_MODEL_TYPES)

    _BUILTIN_LORA_OPTIONS = [
        "khiemle__xz-comfy__jennie_turbo_v4.safetensors",
        "khiemle__xz-comfy__jennie_outdoor_v1.safetensors",
        "khiemle__xz-comfy__jennie_indoor_v1.safetensors",
        "khiemle__xz-comfy__jennie_selfie_v2.safetensors",
        "khiemle__xz-comfy__sephera_turbo_v6.safetensors",
        "khiemle__xz-comfy__sephera_turbo_v2_gymer.safetensors",
        "khiemle__xz-comfy__emi_turbo_v2.safetensors",
        "Macincesht__ff-loras__emi_v3.safetensors",
        "Macincesht__ff-loras__emi_v4.safetensors",
        "Macincesht__ff-loras__emi_v5.safetensors",
        "Macincesht__ff-loras__emi_v6.safetensors",
        "Macincesht__ff-loras__emi_v7.safetensors",
        "khiemle__xz-comfy__roxie_v3.safetensors",
        "khiemle__xz-comfy__roxie_v4_000001250.safetensors",
        "khiemle__xz-comfy__Sephera_v7.safetensors",
    ]

    @property
    def _custom_loras_file(self) -> Path:
        return self.prompts_dir / "lora_options_custom.json"

    def _load_custom_loras(self) -> List[str]:
        if not self._custom_loras_file.exists():
            return []
        try:
            return json.loads(self._custom_loras_file.read_text())
        except Exception:
            return []

    def get_lora_options(self) -> List[str]:
        base = self._option_list("lora_options", self._BUILTIN_LORA_OPTIONS)
        custom = self._load_custom_loras()
        seen = set(base)
        extras = [c for c in custom if c not in seen]
        return base + extras

    def add_lora_option(self, name: str) -> List[str]:
        name = name.strip()
        all_options = self.get_lora_options()
        if name in all_options:
            return all_options
        custom = self._load_custom_loras()
        custom.append(name)
        self._custom_loras_file.write_text(json.dumps(custom, indent=2))
        return self.get_lora_options()

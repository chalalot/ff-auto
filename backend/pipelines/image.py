"""ComfyUI image generation pipelines.

Two strategies are ported from the original ``ComfyUIClient.generate_image``:

- :class:`UnifiedPromptPipeline` — the whole prompt drives a single CLIP node.
- :class:`SubjectEnvironmentPipeline` — a ``#Subject`` / ``#Environment`` prompt
  drives two separate conditioning nodes, with a single-node fallback.

Both share the :class:`ComfyImagePipeline` skeleton (load workflow.json, patch
the CLIP loader / LoRA / dimensions / seeds) and differ only in how the prompt
is injected — the variable step. Node discovery and patching reuse the existing
helpers in :mod:`backend.third_parties.comfyui_client` so behaviour stays
identical to the current generation path.
"""
from __future__ import annotations

import json
import os
import re
from abc import abstractmethod
from typing import Any, Dict, Optional, Tuple

from backend.third_parties.comfyui_client import (
    PERSONA_LORA_MAPPING_TURBO,
    _find_lora_workflow_node,
    _find_workflow_node,
    _patch_sampler_seeds,
    _patch_workflow_dimensions,
    _workflow_node_inputs,
)

from .base import GenerationInputs, GenerationPipeline, register

_SUBJECT_RE = re.compile(r"#Subject\s*(.*?)(?=#Environment|$)", re.IGNORECASE | re.DOTALL)
_ENVIRONMENT_RE = re.compile(r"#Environment\s*(.*?)(?=#Subject|$)", re.IGNORECASE | re.DOTALL)
_LORA_TAG_RE = re.compile(r"<lora:[^>]+>,\s*Instagirl,?\s*", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Shared building blocks
# ---------------------------------------------------------------------------

def _clean_prompt(prompt: str) -> str:
    """Strip embedded ``<lora:...>, Instagirl`` tags the way generate_image does."""
    return _LORA_TAG_RE.sub("", prompt)


def _resolve_lora(lora_name: Optional[str], kol_persona: Optional[str]) -> Optional[str]:
    """Explicit override wins; otherwise map the persona to its turbo LoRA."""
    if lora_name:
        return lora_name
    if kol_persona:
        for persona_key, lora in PERSONA_LORA_MAPPING_TURBO.items():
            if persona_key.lower() == kol_persona.lower():
                return lora
    return None


def _load_workflow_json() -> Dict[str, Any]:
    """Load the workflow graph from ``WORKFLOW_JSON_PATH`` or the project root."""
    workflow_path = os.getenv(
        "WORKFLOW_JSON_PATH",
        os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "workflow.json",
        ),
    )
    with open(workflow_path, "r") as f:
        return json.load(f)


def _patch_clip_loader(workflow_data: Dict[str, Any], clip_model_type: str) -> None:
    clip_node = _find_workflow_node(
        workflow_data,
        class_type="CLIPLoader",
        required_inputs={"type"},
        legacy_id="39",
    )
    if not clip_node:
        return
    clip_inputs = _workflow_node_inputs(clip_node)
    if clip_model_type:
        clip_inputs["type"] = clip_model_type
    clip_device = os.getenv("COMFYUI_CLIP_DEVICE")
    if "device" in clip_inputs and clip_device:
        clip_inputs["device"] = clip_device


def _split_subject_environment(cleaned_prompt: str) -> Tuple[Optional[str], Optional[str]]:
    """Return ``(subject_text, env_text)`` if both markers are present, else (None, None)."""
    sub_match = _SUBJECT_RE.search(cleaned_prompt)
    env_match = _ENVIRONMENT_RE.search(cleaned_prompt)
    if sub_match and env_match:
        return (
            f"#Subject\n{sub_match.group(1).strip()}",
            f"#Environment\n{env_match.group(1).strip()}",
        )
    return None, None


def _find_subject_env_node_ids(
    workflow_data: Dict[str, Any]
) -> Tuple[Optional[str], Optional[str]]:
    """Map ConditioningSetTimestepRange nodes to their source CLIP node ids.

    A range with ``start > 0`` feeds the subject; ``start == 0`` feeds the
    environment (matching the original generate_image heuristic).
    """
    subject_node_id: Optional[str] = None
    env_node_id: Optional[str] = None
    for node in workflow_data.values():
        if not isinstance(node, dict) or node.get("class_type") != "ConditioningSetTimestepRange":
            continue
        inputs = _workflow_node_inputs(node)
        cond_input = inputs.get("conditioning")
        start_val = inputs.get("start", 0)
        if isinstance(cond_input, list) and cond_input:
            source_id = str(cond_input[0])
            if start_val > 0:
                subject_node_id = source_id
            else:
                env_node_id = source_id
    return subject_node_id, env_node_id


def _inject_split_prompt(
    workflow_data: Dict[str, Any], subject_text: str, env_text: str
) -> bool:
    """Inject into the two conditioning source nodes. Returns False if absent."""
    subject_node_id, env_node_id = _find_subject_env_node_ids(workflow_data)
    if (
        subject_node_id
        and env_node_id
        and subject_node_id in workflow_data
        and env_node_id in workflow_data
    ):
        _workflow_node_inputs(workflow_data[subject_node_id])["text"] = subject_text
        _workflow_node_inputs(workflow_data[env_node_id])["text"] = env_text
        return True
    return False


def _inject_single_prompt(workflow_data: Dict[str, Any], text: str) -> None:
    prompt_node = _find_workflow_node(
        workflow_data,
        class_type="CLIPTextEncode",
        required_inputs={"text"},
        legacy_id="45",
    )
    if prompt_node:
        _workflow_node_inputs(prompt_node)["text"] = text


# ---------------------------------------------------------------------------
# Pipelines
# ---------------------------------------------------------------------------

class ComfyImagePipeline(GenerationPipeline):
    """Shared skeleton for ComfyUI image pipelines.

    Subclasses implement :meth:`inject_prompt` — the only step that differs.
    """

    media_type = "image"

    def build_workflow(self, inputs: GenerationInputs) -> Dict[str, Any]:
        cleaned_prompt = _clean_prompt(inputs.prompt)
        workflow_data = _load_workflow_json()
        final_lora = _resolve_lora(inputs.lora_name, inputs.kol_persona)

        _patch_clip_loader(workflow_data, inputs.clip_model_type)
        self.inject_prompt(workflow_data, cleaned_prompt)

        lora_node = _find_lora_workflow_node(workflow_data)
        if lora_node:
            lora_inputs = _workflow_node_inputs(lora_node)
            if final_lora:
                lora_inputs["lora_name"] = final_lora
            if inputs.strength_model is not None:
                lora_inputs["strength_model"] = float(inputs.strength_model)

        _patch_workflow_dimensions(workflow_data, inputs.width, inputs.height)
        _patch_sampler_seeds(workflow_data, inputs.seed_strategy, inputs.base_seed)
        return workflow_data

    @abstractmethod
    def inject_prompt(self, workflow_data: Dict[str, Any], cleaned_prompt: str) -> None:
        """Write the prompt into the appropriate node(s) for this strategy."""


@register
class UnifiedPromptPipeline(ComfyImagePipeline):
    """Single-prompt image generation: the whole prompt drives one CLIP node."""

    pipeline_type = "image.unified"
    label = "Unified prompt"

    def inject_prompt(self, workflow_data: Dict[str, Any], cleaned_prompt: str) -> None:
        _inject_single_prompt(workflow_data, cleaned_prompt)


@register
class SubjectEnvironmentPipeline(ComfyImagePipeline):
    """Two-part prompt: ``#Subject`` and ``#Environment`` drive separate nodes.

    Falls back to a single combined node when the workflow has no split nodes,
    preserving the original generate_image behaviour.
    """

    pipeline_type = "image.subject_environment"
    label = "Subject + Environment"

    def inject_prompt(self, workflow_data: Dict[str, Any], cleaned_prompt: str) -> None:
        subject_text, env_text = _split_subject_environment(cleaned_prompt)
        if subject_text and env_text and _inject_split_prompt(
            workflow_data, subject_text, env_text
        ):
            return
        combined = (
            f"{subject_text}, {env_text}"
            if subject_text and env_text
            else cleaned_prompt
        )
        _inject_single_prompt(workflow_data, combined)

"""ComfyUI image generation pipelines.

Two strategies are ported from the original ``ComfyUIClient.generate_image``:

- :class:`UnifiedPromptPipeline` — the full narrative drives one text node.
- :class:`SubjectEnvironmentPipeline` — full and environment narratives drive
  late/early timestep conditioning nodes, with a full-narrative fallback.

Both share the :class:`ComfyImagePipeline` skeleton (load the workflow graph,
patch the prompt / source image / per-run overrides) and differ only in how the
prompt is injected — the variable step. Seeds, LoRA, dimensions, and CLIP type
are owned by the workflow JSON itself and edited via ``workflow_overrides``.
"""
from __future__ import annotations

import json
import os
import re
from abc import abstractmethod
from typing import Any, Dict, Optional, Tuple

from backend.third_parties.comfyui_client import (
    _find_workflow_node,
    _workflow_node_inputs,
)

from .base import (
    GenerationInputs,
    GenerationPipeline,
    PipelineInputError,
    apply_workflow_overrides,
    register,
)

_FULL_PROMPT_RE = re.compile(
    r"#(?:Prompt|Subject)\s*(.*?)(?=#Environment|$)", re.IGNORECASE | re.DOTALL
)
_ENVIRONMENT_RE = re.compile(
    r"#Environment\s*(.*?)(?=#(?:Prompt|Subject)|$)", re.IGNORECASE | re.DOTALL
)
_LORA_TAG_RE = re.compile(r"<lora:[^>]+>,\s*Instagirl,?\s*", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Shared building blocks
# ---------------------------------------------------------------------------

def _clean_prompt(prompt: str) -> str:
    """Strip embedded ``<lora:...>, Instagirl`` tags the way generate_image does."""
    return _LORA_TAG_RE.sub("", prompt)


def _workflows_dir() -> str:
    """Directory holding the selectable workflow JSON graphs."""
    return os.getenv(
        "WORKFLOWS_DIR",
        os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "workflows",
        ),
    )


def list_workflow_files() -> list:
    """Sorted ``*.json`` filenames available in the workflows directory."""
    directory = _workflows_dir()
    if not os.path.isdir(directory):
        return []
    return sorted(f for f in os.listdir(directory) if f.endswith(".json"))


def _resolve_workflow_path(workflow_name: str) -> str:
    """Map a bare filename to a path inside the workflows dir, guarding traversal."""
    if (
        not workflow_name
        or "/" in workflow_name
        or "\\" in workflow_name
        or ".." in workflow_name
    ):
        raise PipelineInputError(f"Invalid workflow name '{workflow_name}'")
    return os.path.join(_workflows_dir(), workflow_name)


def _load_workflow_json(workflow_name: Optional[str] = None) -> Dict[str, Any]:
    """Load a workflow graph by filename, defaulting to ``workflow.json``.

    An explicit ``workflow_name`` resolves inside :func:`_workflows_dir` (with a
    path-traversal guard). With no name, ``WORKFLOW_JSON_PATH`` wins if set,
    otherwise ``<workflows>/workflow.json``.
    """
    if workflow_name:
        workflow_path = _resolve_workflow_path(workflow_name)
    else:
        workflow_path = os.getenv("WORKFLOW_JSON_PATH") or os.path.join(
            _workflows_dir(), "workflow.json"
        )
    with open(workflow_path, "r") as f:
        return json.load(f)


def load_workflow_template(workflow_name: Optional[str] = None) -> Dict[str, Any]:
    """Public accessor for a workflow graph (used by the API for introspection)."""
    return _load_workflow_json(workflow_name)


def _patch_clip_device(workflow_data: Dict[str, Any]) -> None:
    """Deployment-owned device override; the CLIP type stays as authored in the JSON."""
    clip_node = _find_workflow_node(
        workflow_data,
        class_type="CLIPLoader",
        required_inputs={"type"},
        legacy_id="39",
    )
    if not clip_node:
        return
    clip_inputs = _workflow_node_inputs(clip_node)
    clip_device = os.getenv("COMFYUI_CLIP_DEVICE")
    if "device" in clip_inputs and clip_device:
        clip_inputs["device"] = clip_device


def workflow_has_load_image(workflow_data: Dict[str, Any]) -> bool:
    """True when the graph has a LoadImage node with a literal image input."""
    return _find_load_image_node(workflow_data) is not None


def _find_load_image_node(workflow_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    for node in workflow_data.values():
        if not isinstance(node, dict) or node.get("class_type") != "LoadImage":
            continue
        inputs = _workflow_node_inputs(node)
        if "image" in inputs and not isinstance(inputs.get("image"), list):
            return node
    return None


def patch_load_image(workflow_data: Dict[str, Any], image_filename: str) -> bool:
    """Point the workflow's LoadImage node at an uploaded ComfyUI filename."""
    node = _find_load_image_node(workflow_data)
    if node is None:
        return False
    _workflow_node_inputs(node)["image"] = image_filename
    return True


def find_library_image(filename: str) -> Optional[str]:
    """Resolve a bare library filename to its path in PROCESSED_DIR, or None."""
    if (
        not filename
        or "/" in filename
        or "\\" in filename
        or ".." in filename
    ):
        return None
    from backend.config import GlobalConfig

    path = os.path.join(GlobalConfig.PROCESSED_DIR, filename)
    return path if os.path.isfile(path) else None


async def resolve_image_overrides(
    workflow_data: Dict[str, Any],
    overrides: Dict[str, Dict[str, Any]],
    upload,
) -> None:
    """Upload library images referenced by LoadImage overrides to ComfyUI.

    The Workflow Parameters panel lets the user point a LoadImage node at a
    file from the image library; ComfyUI only knows its own uploaded
    filenames, so each such value is uploaded via ``upload(path)`` and
    replaced in place with the name ComfyUI assigned. Values that don't match
    a library file (e.g. a name already uploaded to ComfyUI) pass through
    untouched.
    """
    for node_id, patch in (overrides or {}).items():
        node = workflow_data.get(node_id)
        if not isinstance(node, dict) or node.get("class_type") != "LoadImage":
            continue
        value = (patch or {}).get("image")
        if not isinstance(value, str):
            continue
        local_path = find_library_image(value)
        if local_path:
            patch["image"] = await upload(local_path)


def _split_subject_environment(cleaned_prompt: str) -> Tuple[Optional[str], Optional[str]]:
    """Return ``(full_text, env_text)``; accept legacy ``#Subject`` prompts."""
    sub_match = _FULL_PROMPT_RE.search(cleaned_prompt)
    env_match = _ENVIRONMENT_RE.search(cleaned_prompt)
    if sub_match and env_match:
        return (
            f"#Prompt\n{sub_match.group(1).strip()}",
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

    def load_template(self, workflow_name: Optional[str] = None) -> Dict[str, Any]:
        return _load_workflow_json(workflow_name)

    def build_workflow(self, inputs: GenerationInputs) -> Dict[str, Any]:
        cleaned_prompt = _clean_prompt(inputs.prompt)
        workflow_data = self.load_template(inputs.workflow_name)

        _patch_clip_device(workflow_data)
        self.inject_prompt(workflow_data, cleaned_prompt)

        # Reference/source image (uploaded to ComfyUI beforehand) feeds the
        # LoadImage node when the graph has one (e.g. control-net workflows).
        if inputs.images:
            patch_load_image(workflow_data, inputs.images[0])

        # Seeds, LoRA, dimensions, CLIP type, etc. all belong to the workflow
        # JSON now and are edited per-run through workflow_overrides.
        apply_workflow_overrides(workflow_data, inputs.workflow_overrides)
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
        full_prompt, _ = _split_subject_environment(cleaned_prompt)
        _inject_single_prompt(workflow_data, full_prompt or cleaned_prompt)


@register
class SubjectEnvironmentPipeline(ComfyImagePipeline):
    """Full-scene and environment prompts drive late/early conditioning nodes.

    Falls back to a single combined node when the workflow has no split nodes,
    preserving the original generate_image behaviour.
    """

    pipeline_type = "image.subject_environment"
    label = "Subject + Environment"

    def inject_prompt(self, workflow_data: Dict[str, Any], cleaned_prompt: str) -> None:
        full_text, env_text = _split_subject_environment(cleaned_prompt)
        if full_text and env_text and _inject_split_prompt(
            workflow_data, full_text, env_text
        ):
            return
        _inject_single_prompt(workflow_data, full_text or cleaned_prompt)

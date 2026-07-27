"""Core abstractions for the generation pipeline subsystem.

Design: Strategy + Registry, with a Template-Method ``run`` skeleton.

Each concrete pipeline is one interchangeable generation *strategy*. The only
part that varies between pipelines is :meth:`GenerationPipeline.build_workflow`
— everything else (validation hook, submission through the single engine seam)
lives in the shared base. Pipelines register themselves under a stable
``pipeline_type`` string so callers can resolve them via :func:`get_pipeline`
instead of branching on backend/structure at the call site.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import html
import re
from urllib.parse import unquote
from typing import Any, Dict, List, Optional



def clean_lora_name(val: Optional[str]) -> Optional[str]:
    """Normalize a LoRA filename: unescape HTML/URL encoding iteratively and ensure .safetensors suffix."""
    if not val or not isinstance(val, str):
        return None
    cleaned = val.strip()
    if not cleaned or cleaned.lower() == "none":
        return None
    for _ in range(5):
        prev = cleaned
        cleaned = html.unescape(cleaned)
        cleaned = unquote(cleaned)
        if cleaned == prev:
            break
    cleaned = cleaned.strip()
    if not cleaned or cleaned.lower() == "none":
        return None
    # Normalize ComfyUI Cloud repository separator convention (__ instead of / or -)
    cleaned = re.sub(r"^khiemle[/\s_-]+xz-comfy[/\s_-]+", "khiemle__xz-comfy__", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^Macincesht[/\s_-]+ff-loras[/\s_-]+", "Macincesht__ff-loras__", cleaned, flags=re.IGNORECASE)
    if not cleaned.lower().endswith(".safetensors"):
        cleaned += ".safetensors"
    return cleaned


LOCKED_INPUT_KEYS: Dict[str, str] = {
    "text": "Set from the prompt",
    "device": "Controlled by deployment (COMFYUI_CLIP_DEVICE)",
}


def _infer_param_type(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    return "string"


def describe_workflow_parameters(workflow_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """List every editable (non-wiring) node input from a workflow graph.

    List-valued inputs are node connections and are excluded. Inputs whose key
    is in ``LOCKED_INPUT_KEYS`` are returned but flagged ``locked`` so the UI can
    show them greyed-out (they are owned by the app / prompt / deployment).
    """
    nodes: List[Dict[str, Any]] = []
    for node_id, node in workflow_data.items():
        if not isinstance(node, dict) or "inputs" not in node:
            continue
        title = node.get("_meta", {}).get("title") or node.get("class_type", node_id)
        inputs: List[Dict[str, Any]] = []
        for key, value in node.get("inputs", {}).items():
            if isinstance(value, list):  # node connection (wiring), not a value
                continue
            locked_reason = LOCKED_INPUT_KEYS.get(key)
            inputs.append({
                "key": key,
                "value": value,
                "type": _infer_param_type(value),
                "locked": locked_reason is not None,
                "locked_reason": locked_reason,
            })
        if inputs:
            nodes.append({
                "node_id": node_id,
                "class_type": node.get("class_type", ""),
                "title": title,
                "inputs": inputs,
            })
    return nodes


def _coerce_to(existing: Any, value: Any) -> Any:
    """Coerce ``value`` to the type of ``existing`` (best-effort)."""
    try:
        if isinstance(existing, bool):
            return bool(value)
        if isinstance(existing, int):
            return int(value)
        if isinstance(existing, float):
            return float(value)
        return type(existing)(value)
    except (TypeError, ValueError):
        return existing  # leave the original value untouched on bad input


def _split_overrides(
    workflow_data: Dict[str, Any], overrides: Dict[str, Dict[str, Any]]
) -> tuple:
    """Split overrides into applicable targets and unresolved ``node.key`` labels.

    One walk shared by :func:`apply_workflow_overrides` and
    :func:`find_unresolved_overrides` so what gets applied and what gets
    reported as stale can never drift apart. Locked keys are by-design skips,
    not staleness, so they appear in neither list.
    """
    targets = []
    unresolved = []
    for node_id, patch in overrides.items():
        node = workflow_data.get(node_id)
        node_inputs = node.get("inputs") if isinstance(node, dict) else None
        if not isinstance(node_inputs, dict):
            node_inputs = None
        for key, value in (patch or {}).items():
            if key in LOCKED_INPUT_KEYS:
                continue
            if (
                node_inputs is None
                or key not in node_inputs
                or isinstance(node_inputs[key], list)
            ):
                unresolved.append(f"{node_id}.{key}")
                continue
            targets.append((node_inputs, key, value))
    return targets, unresolved


def apply_workflow_overrides(
    workflow_data: Dict[str, Any], overrides: Dict[str, Dict[str, Any]]
) -> None:
    """Apply per-run node-input overrides in place.

    Skips locked keys, unknown nodes, and keys not already present as a
    non-list input. Coerces each value to the existing value's type. Defensive
    by design: a stale panel must never raise here.
    """
    if not overrides:
        return
    targets, _ = _split_overrides(workflow_data, overrides)
    for node_inputs, key, value in targets:
        if key == "lora_name" and isinstance(value, str):
            cleaned = clean_lora_name(value)
            if cleaned:
                node_inputs[key] = cleaned
        else:
            node_inputs[key] = _coerce_to(node_inputs[key], value)


def find_unresolved_overrides(
    workflow_data: Dict[str, Any], overrides: Dict[str, Dict[str, Any]]
) -> List[str]:
    """``"<node_id>.<input_key>"`` for every override the graph no longer accepts.

    :func:`apply_workflow_overrides` drops these silently, so a row saved
    against an older revision of the workflow generates with the graph's
    defaults instead of the values someone actually chose. Workflow JSON is
    read fresh at dispatch, which is what lets a row go stale in place.
    """
    if not overrides:
        return []
    _, unresolved = _split_overrides(workflow_data, overrides)
    return unresolved


@dataclass
class GenerationInputs:
    """Engine-agnostic inputs shared by every generation pipeline.

    Image pipelines use ``prompt`` plus the LoRA / dimension / seed fields.
    Video pipelines additionally use ``images`` — an *ordered* list whose
    per-entry role is defined by the chosen pipeline (e.g. ``[first]``,
    ``[first, last]``, ``[first, middle, last]``).
    """

    prompt: str = ""
    lora_name: Optional[str] = None
    kol_persona: Optional[str] = None
    strength_model: Optional[str] = None
    seed_strategy: str = "random"
    base_seed: int = 0
    width: str = "1024"
    height: str = "1600"
    clip_model_type: str = "qwen_image"
    images: List[str] = field(default_factory=list)
    options: Dict[str, Any] = field(default_factory=dict)
    workflow_overrides: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    workflow_name: Optional[str] = None  # which workflows/*.json to build from


class PipelineError(Exception):
    """Base error for the pipeline subsystem."""


class UnknownPipelineError(PipelineError, KeyError):
    """Raised when no pipeline is registered for a requested ``pipeline_type``."""


class PipelineInputError(PipelineError, ValueError):
    """Raised when inputs don't satisfy a pipeline's requirements."""


class GenerationPipeline(ABC):
    """One interchangeable generation strategy.

    Subclasses set ``pipeline_type`` / ``media_type`` and implement
    :meth:`build_workflow`. The shared :meth:`run` validates inputs, builds the
    workflow, and submits it through the single engine seam.
    """

    pipeline_type: str = ""
    media_type: str = ""  # "image" | "video"
    label: str = ""  # human-friendly name for the selector
    available: bool = True  # False for typed stubs that cannot run yet

    def validate(self, inputs: GenerationInputs) -> None:
        """Enforce per-pipeline input requirements. No-op by default."""

    @abstractmethod
    def build_workflow(self, inputs: GenerationInputs) -> Dict[str, Any]:
        """Return the fully-patched ComfyUI workflow graph for ``inputs``."""

    def load_template(self, workflow_name: Optional[str] = None) -> Dict[str, Any]:
        """Return the raw workflow graph this pipeline builds from."""
        raise NotImplementedError(
            f"{self.pipeline_type} does not expose a workflow template"
        )

    def describe_parameters(self, workflow_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """Introspect this pipeline's workflow JSON into editable parameters."""
        return describe_workflow_parameters(self.load_template(workflow_name))

    async def run(self, inputs: GenerationInputs, client: Any = None) -> str:
        """Validate → build → submit. Returns the ComfyUI ``prompt_id``.

        ``client`` is the single engine seam: any object exposing an async
        ``queue_prompt(workflow)``. Defaults to the shared ComfyUI client.
        """
        self.validate(inputs)
        workflow = self.build_workflow(inputs)
        if client is None:
            from backend.third_parties.comfyui_client import get_client

            client = get_client()
        return await client.queue_prompt(workflow)


_REGISTRY: Dict[str, GenerationPipeline] = {}


def register(cls: type) -> type:
    """Class decorator: instantiate and register a pipeline by ``pipeline_type``.

    Pipelines are stateless, so a single shared instance is registered (the
    same singleton-style instance management used elsewhere in the codebase).
    """
    instance = cls()
    if not instance.pipeline_type:
        raise PipelineError(f"{cls.__name__} has no pipeline_type")
    _REGISTRY[instance.pipeline_type] = instance
    return cls


def get_pipeline(pipeline_type: str) -> GenerationPipeline:
    """Resolve a registered pipeline, or raise :class:`UnknownPipelineError`."""
    try:
        return _REGISTRY[pipeline_type]
    except KeyError:
        raise UnknownPipelineError(
            f"No pipeline registered for '{pipeline_type}'. "
            f"Available: {sorted(_REGISTRY)}"
        )


def available_pipelines() -> List[str]:
    """Sorted list of every registered ``pipeline_type``."""
    return sorted(_REGISTRY)


def pipelines_metadata() -> List[Dict[str, Any]]:
    """Selector-facing metadata for every registered pipeline."""
    return [
        {
            "pipeline_type": p.pipeline_type,
            "media_type": p.media_type,
            "label": p.label or p.pipeline_type,
            "available": p.available,
        }
        for p in sorted(_REGISTRY.values(), key=lambda x: x.pipeline_type)
    ]

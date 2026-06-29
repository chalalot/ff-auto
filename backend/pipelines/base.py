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
from typing import Any, Dict, List, Optional

from backend.utils.constants import DEFAULT_NEGATIVE_PROMPT


@dataclass
class GenerationInputs:
    """Engine-agnostic inputs shared by every generation pipeline.

    Image pipelines use ``prompt`` plus the LoRA / dimension / seed fields.
    Video pipelines additionally use ``images`` — an *ordered* list whose
    per-entry role is defined by the chosen pipeline (e.g. ``[first]``,
    ``[first, last]``, ``[first, middle, last]``).
    """

    prompt: str = ""
    negative_prompt: str = DEFAULT_NEGATIVE_PROMPT
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

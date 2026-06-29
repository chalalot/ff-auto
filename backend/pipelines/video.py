"""Image-to-video ComfyUI pipelines (typed stubs).

These declare the shape of the upcoming frame-config pipelines — how many input
images each requires — and validate that contract today, but defer workflow
construction. Implementing :meth:`build_workflow` for each is the next slice.
"""
from __future__ import annotations

from typing import Any, Dict

from .base import (
    GenerationInputs,
    GenerationPipeline,
    PipelineInputError,
    register,
)


class ComfyVideoPipeline(GenerationPipeline):
    """Base for image-to-video ComfyUI pipelines.

    ``required_images`` declares the exact number of ordered input frames the
    pipeline consumes; :meth:`validate` enforces it. :meth:`build_workflow` is
    intentionally unimplemented until each variant is built out.
    """

    media_type = "video"
    available = False  # typed stubs — build_workflow not implemented yet
    required_images: int = 0

    def validate(self, inputs: GenerationInputs) -> None:
        if len(inputs.images) != self.required_images:
            raise PipelineInputError(
                f"{self.pipeline_type} requires exactly {self.required_images} "
                f"image(s), got {len(inputs.images)}"
            )

    def build_workflow(self, inputs: GenerationInputs) -> Dict[str, Any]:
        raise NotImplementedError(
            f"{self.pipeline_type} is a typed stub — not yet implemented"
        )


@register
class FirstFramePipeline(ComfyVideoPipeline):
    """1 image + prompt → video seeded from the first frame."""

    pipeline_type = "video.first_frame"
    label = "First frame"
    required_images = 1


@register
class FirstLastFramePipeline(ComfyVideoPipeline):
    """2 images + prompt → video interpolated between first and last frames."""

    pipeline_type = "video.first_last_frame"
    label = "First + Last frame"
    required_images = 2


@register
class FirstMiddleLastFramePipeline(ComfyVideoPipeline):
    """3 images + prompt → video through first, middle, and last frames."""

    pipeline_type = "video.first_middle_last_frame"
    label = "First + Middle + Last frame"
    required_images = 3

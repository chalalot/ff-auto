"""CrewAI tool wrapper around the shared multimodal completion seam.

A CrewAI agent's own messages are text-only, so a crew can only get an image in
front of a model through a tool call. Workflows that are NOT a crew should call
:func:`backend.services.vision_llm.complete` directly instead — that keeps the
pixels in the same request as the reasoning, with no text summary in between.
"""

import logging
from typing import Optional, Type

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

from backend.services import vision_llm

logger = logging.getLogger(__name__)

# The tool route answers a bounded question about one image; the cap keeps a
# chatty model from returning an essay into the agent's context.
_TOOL_MAX_TOKENS = 1000


class VisionToolInput(BaseModel):
    """Input schema for VisionTool when image_path is required."""
    image_path: str = Field(..., description="The absolute local file path to the image to analyze. This argument is MANDATORY.")
    prompt: str = Field(..., description="The question or instruction for the vision model about the image.")
    system_prompt: Optional[str] = Field(default=None, description="Optional system-level role and output contract.")

class VisionToolFixedInput(BaseModel):
    """Input schema for VisionTool when image_path is fixed."""
    prompt: str = Field(..., description="The question or instruction for the vision model about the image.")
    system_prompt: Optional[str] = Field(default=None, description="Optional system-level role and output contract.")

class VisionTool(BaseTool):
    name: str = "Vision Tool"
    description: str = (
        "A tool that uses a vision model to analyze images. "
        "It takes a prompt and returns a text description."
    )
    args_schema: Type[BaseModel] = VisionToolInput
    fixed_image_path: Optional[str] = None
    model_name: str = "gpt-4o"

    def __init__(self, fixed_image_path: Optional[str] = None, model_name: str = "gpt-4o", **kwargs):
        super().__init__(**kwargs)
        self.model_name = model_name
        if fixed_image_path:
            self.fixed_image_path = fixed_image_path
            self.args_schema = VisionToolFixedInput
            self.description = f"A tool that uses {self.model_name} to analyze the SPECIFIC image currently being processed. It takes a prompt and returns a text description."

    def _run(
        self,
        prompt: str,
        image_path: Optional[str] = None,
        system_prompt: Optional[str] = None,
    ) -> str:
        # A fixed path is bound by the workflow, so the agent cannot choose which
        # file gets read.
        effective_path = self.fixed_image_path or image_path

        logger.info(
            "[VisionTool] _run called. Fixed path: %r, Arg path: %r, Model: %s",
            self.fixed_image_path, image_path, self.model_name,
        )

        if not effective_path:
            return "Error: No image path provided. The tool requires an image path."

        try:
            return vision_llm.complete(
                model_name=self.model_name,
                prompt=prompt,
                image_path=effective_path,
                system_prompt=system_prompt,
                max_tokens=_TOOL_MAX_TOKENS,
            )
        except Exception as exc:
            # Tools must hand the agent a string it can react to, never raise
            # into the crew loop.
            logger.error("[VisionTool] vision call failed: %s", exc)
            return f"Error processing image: {exc}"

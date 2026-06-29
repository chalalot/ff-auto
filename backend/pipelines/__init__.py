"""Generation pipeline subsystem (Strategy + Registry).

Importing this package registers every built-in pipeline so that
:func:`get_pipeline` can resolve them by ``pipeline_type``.
"""
from .base import (
    GenerationInputs,
    GenerationPipeline,
    PipelineError,
    PipelineInputError,
    UnknownPipelineError,
    available_pipelines,
    describe_workflow_parameters,
    get_pipeline,
    pipelines_metadata,
    register,
)

# Importing these modules runs the @register decorators.
from . import image  # noqa: F401,E402  (registers image pipelines)
from . import video  # noqa: F401,E402  (registers video pipelines)

__all__ = [
    "GenerationInputs",
    "GenerationPipeline",
    "PipelineError",
    "PipelineInputError",
    "UnknownPipelineError",
    "available_pipelines",
    "describe_workflow_parameters",
    "get_pipeline",
    "pipelines_metadata",
    "register",
]

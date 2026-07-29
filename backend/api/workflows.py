"""Pipeline and workflow-graph routes.

Split out of :mod:`backend.api.workspace`: everything about *what can run*
(pipeline selectors, workflow JSON introspection, and the workflow file
library CRUD) lives here; dispatching work and managing images stays in
workspace. Mounted under the same ``/api/workspace`` prefix so every URL is
unchanged.
"""
import logging
from typing import List

from fastapi import APIRouter, HTTPException, UploadFile, File

from backend.models.workspace import (
    PipelineInfo,
    WorkflowParametersResponse,
    WorkflowFileParametersResponse,
    WorkflowSummary,
    WorkflowGraphResponse,
    WorkflowCreateRequest,
    WorkflowSaveRequest,
    WorkflowRenameRequest,
    WorkflowDuplicateRequest,
    WorkflowMutationResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _get_available_pipeline(pipeline_type: str):
    """Resolve a runnable pipeline or raise 400 (unknown or unavailable)."""
    from backend.pipelines import UnknownPipelineError, get_pipeline

    try:
        pipeline = get_pipeline(pipeline_type)
    except UnknownPipelineError:
        raise HTTPException(status_code=400, detail=f"Unknown pipeline_type '{pipeline_type}'")
    if not pipeline.available:
        raise HTTPException(
            status_code=400,
            detail=f"pipeline_type '{pipeline_type}' is not available yet",
        )
    return pipeline


@router.get("/image-pipelines", response_model=List[str])
def list_image_pipelines():
    """Available image generation pipeline types, for the caller to choose from."""
    from backend.pipelines import available_pipelines, get_pipeline

    return [pt for pt in available_pipelines() if get_pipeline(pt).media_type == "image"]


@router.get("/pipelines", response_model=List[PipelineInfo])
def list_pipelines():
    """All registered pipelines (image + video) with selector metadata."""
    from backend.pipelines import pipelines_metadata

    return pipelines_metadata()


@router.get("/pipelines/{pipeline_type}/parameters", response_model=WorkflowParametersResponse)
def get_pipeline_parameters(pipeline_type: str):
    """Editable workflow parameters introspected from the pipeline's JSON."""
    pipeline = _get_available_pipeline(pipeline_type)
    return {"pipeline_type": pipeline_type, "nodes": pipeline.describe_parameters()}


@router.get("/workflows", response_model=List[str])
def list_workflows():
    """Workflow JSON graphs available in the workflows directory, for selection."""
    from backend.pipelines import list_workflow_files

    return list_workflow_files()


@router.get("/workflows/{workflow_name}/parameters", response_model=WorkflowFileParametersResponse)
def get_workflow_parameters(workflow_name: str):
    """Editable parameters introspected from the selected workflow JSON file."""
    from backend.pipelines import (
        describe_workflow_parameters,
        list_workflow_files,
        load_workflow_template,
    )

    if workflow_name not in list_workflow_files():
        raise HTTPException(status_code=404, detail=f"Unknown workflow '{workflow_name}'")
    return {
        "workflow": workflow_name,
        "nodes": describe_workflow_parameters(load_workflow_template(workflow_name)),
    }


# ---------------------------------------------------------------------------
# Workflow file management (create / edit / rename / duplicate / import / delete)
#
# Declared before the parameterized `/workflows/{workflow_name}` routes so the
# literal paths (`/library`, `/import`) can never be swallowed as a filename.
# ---------------------------------------------------------------------------

def _workflow_op(fn, *args, **kwargs):
    """Run a workflow_library call, mapping its errors onto HTTP status codes."""
    from backend.services.workflow_library import (
        WorkflowConflictError,
        WorkflowNotFoundError,
        WorkflowValidationError,
    )

    try:
        return fn(*args, **kwargs)
    except WorkflowNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except WorkflowConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except WorkflowValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Could not write workflow file: {exc}")


@router.get("/workflows/library", response_model=List[WorkflowSummary])
def list_workflow_library():
    """Every workflow file with node count, size and validity, for management."""
    from backend.services.workflow_library import summarize_workflows

    return summarize_workflows()


@router.post("/workflows/import", response_model=WorkflowMutationResponse)
async def import_workflow_file(file: UploadFile = File(...)):
    """Store an uploaded ComfyUI API-format workflow JSON in the workflows dir."""
    from backend.services.workflow_library import import_workflow

    raw = await file.read()
    return {"name": _workflow_op(import_workflow, file.filename or "imported.json", raw)}


@router.post("/workflows", response_model=WorkflowMutationResponse)
def create_workflow_file(body: WorkflowCreateRequest):
    """Create a new workflow — a starter graph when none is supplied."""
    from backend.services.workflow_library import create_workflow

    return {"name": _workflow_op(create_workflow, body.name, body.graph)}


@router.get("/workflows/{workflow_name}/graph", response_model=WorkflowGraphResponse)
def get_workflow_graph(workflow_name: str):
    """Open a workflow for editing: always its text, plus the graph if it parses.

    A malformed file is returned with ``graph: null`` and an ``error`` rather
    than a 4xx, so the raw editor can be used to fix it.
    """
    from backend.services.workflow_library import (
        WorkflowValidationError,
        normalize_name,
        parse_graph,
        read_workflow_text,
    )

    raw = _workflow_op(read_workflow_text, workflow_name)
    graph, error = None, None
    try:
        graph = parse_graph(raw)
    except WorkflowValidationError as exc:
        error = str(exc)
    return {
        "name": _workflow_op(normalize_name, workflow_name),
        "raw": raw,
        "graph": graph,
        "error": error,
    }


@router.put("/workflows/{workflow_name}", response_model=WorkflowMutationResponse)
def save_workflow_file(workflow_name: str, body: WorkflowSaveRequest):
    """Overwrite a workflow with a validated graph."""
    from backend.services.workflow_library import save_workflow

    return {"name": _workflow_op(save_workflow, workflow_name, body.graph)}


@router.post("/workflows/{workflow_name}/duplicate", response_model=WorkflowMutationResponse)
def duplicate_workflow_file(workflow_name: str, body: WorkflowDuplicateRequest):
    from backend.services.workflow_library import duplicate_workflow

    return {"name": _workflow_op(duplicate_workflow, workflow_name, body.new_name)}


@router.post("/workflows/{workflow_name}/rename", response_model=WorkflowMutationResponse)
def rename_workflow_file(workflow_name: str, body: WorkflowRenameRequest):
    from backend.services.workflow_library import rename_workflow

    return {"name": _workflow_op(rename_workflow, workflow_name, body.new_name)}


@router.delete("/workflows/{workflow_name}", response_model=WorkflowMutationResponse)
def delete_workflow_file(workflow_name: str):
    from backend.services.workflow_library import delete_workflow

    return {"name": _workflow_op(delete_workflow, workflow_name)}

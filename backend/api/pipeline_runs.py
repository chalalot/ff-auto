from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from backend.database.pipeline_runs_storage import PipelineRunsStorage

router = APIRouter()


@router.get("")
def list_pipeline_runs(
    limit: int = Query(default=20, ge=1, le=100),
    project_id: Optional[str] = None,
):
    return PipelineRunsStorage().list_runs(limit=limit, project_id=project_id)


@router.get("/{run_id}")
def get_pipeline_run(run_id: str):
    trace = PipelineRunsStorage().get_run_with_steps(run_id)
    if trace is None:
        raise HTTPException(status_code=404, detail="Pipeline run not found")
    return trace

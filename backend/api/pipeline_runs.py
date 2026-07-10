from fastapi import APIRouter, HTTPException

from backend.database.pipeline_runs_storage import PipelineRunsStorage

router = APIRouter()


@router.get("/{run_id}")
def get_pipeline_run(run_id: str):
    trace = PipelineRunsStorage().get_run_with_steps(run_id)
    if trace is None:
        raise HTTPException(status_code=404, detail="Pipeline run not found")
    return trace

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from backend.database.pipeline_runs_storage import IN_FLIGHT, PipelineRunsStorage

router = APIRouter()


@router.get("")
def list_pipeline_runs(
    limit: int = Query(default=20, ge=1, le=100),
    project_id: Optional[str] = None,
    in_flight: bool = Query(
        default=False,
        description="Only runs no worker has finished (queued/running), any age.",
    ),
):
    return PipelineRunsStorage().list_runs(
        limit=limit,
        project_id=project_id,
        statuses=IN_FLIGHT if in_flight else None,
    )


@router.get("/{run_id}")
def get_pipeline_run(run_id: str):
    trace = PipelineRunsStorage().get_run_with_steps(run_id)
    if trace is None:
        raise HTTPException(status_code=404, detail="Pipeline run not found")
    return trace


@router.post("/{run_id}/fail")
def fail_pipeline_run(run_id: str):
    """Close out a run whose worker never finished it.

    A queued run that was never picked up (or a running one whose worker died)
    stays in flight forever: the history list keeps polling it every 5s and the
    run reads as live work that isn't happening.
    """
    storage = PipelineRunsStorage()
    row = storage.fail_stalled_run(
        run_id, {"message": "Marked failed from the UI: run was never finished."}
    )
    if row is not None:
        return row
    if storage.get_run_with_steps(run_id) is None:
        raise HTTPException(status_code=404, detail="Pipeline run not found")
    raise HTTPException(
        status_code=409,
        detail=f"Run is already finished; only {IN_FLIGHT} runs can be marked failed.",
    )

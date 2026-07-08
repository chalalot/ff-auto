from fastapi import APIRouter, Depends, HTTPException, Query

from backend.api.deps import get_evaluation_service
from backend.api.identity import Identity, get_identity
from backend.models.evaluation import (
    EvaluationListResponse,
    EvaluationRequest,
    EvaluationResult,
)
from backend.services.evaluation import EvaluationService

router = APIRouter()


@router.post("", response_model=EvaluationResult)
def create_evaluation(
    body: EvaluationRequest,
    svc: EvaluationService = Depends(get_evaluation_service),
    identity: Identity = Depends(get_identity),
):
    return svc.evaluate(body, project_id=identity.project_id, member_id=identity.member_id)


@router.get("", response_model=EvaluationListResponse)
def list_evaluations(
    limit: int = Query(50, ge=1, le=200),
    media_path: str | None = Query(None, min_length=1),
    project_id: str | None = Query(None),
    svc: EvaluationService = Depends(get_evaluation_service),
):
    return EvaluationListResponse(
        items=svc.list_evaluations(limit=limit, media_path=media_path, project_id=project_id)
    )


@router.get("/{evaluation_id}", response_model=EvaluationResult)
def get_evaluation(
    evaluation_id: int,
    svc: EvaluationService = Depends(get_evaluation_service),
):
    result = svc.get_evaluation(evaluation_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Evaluation not found")
    return result

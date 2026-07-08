from fastapi import APIRouter, Depends, Query

from backend.api.deps import get_analysis_service
from backend.models.analysis import AnalysisResponse
from backend.services.analysis import AnalysisService

router = APIRouter()


@router.get("", response_model=AnalysisResponse)
def list_analysis(
    status: str = Query("all", pattern="^(all|pending|approved|disapproved)$"),
    evaluated: str = Query("all", pattern="^(all|yes|no)$"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    project_id: str | None = Query(None),
    svc: AnalysisService = Depends(get_analysis_service),
):
    return svc.get_analysis(
        status=status, evaluated=evaluated, page=page, per_page=per_page,
        project_id=project_id,
    )

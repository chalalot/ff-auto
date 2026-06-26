from typing import List, Optional, Literal

from pydantic import BaseModel

from backend.models.evaluation import EvaluationScore

ApprovalStatus = Literal["pending", "approved", "disapproved"]
EvalRowStatus = Literal["completed", "pending", "failed", "not_evaluated"]


class AnalysisRow(BaseModel):
    filename: str
    path: str
    status: ApprovalStatus
    date: str
    created_at: float
    prompt: Optional[str] = None
    persona: Optional[str] = None
    eval_status: EvalRowStatus
    overall_score: Optional[float] = None
    scores: List[EvaluationScore] = []


class ApprovalBreakdown(BaseModel):
    approved: int
    disapproved: int
    pending: int
    approved_rate: float
    disapproved_rate: float
    pending_rate: float


class EvaluationBreakdown(BaseModel):
    evaluated: int
    not_evaluated: int
    failed: int
    evaluated_rate: float
    not_evaluated_rate: float


class AnalysisSummary(BaseModel):
    total: int
    approval: ApprovalBreakdown
    evaluation: EvaluationBreakdown
    avg_overall_score: Optional[float] = None


class AnalysisResponse(BaseModel):
    summary: AnalysisSummary
    items: List[AnalysisRow]
    total: int
    page: int
    pages: int
    per_page: int

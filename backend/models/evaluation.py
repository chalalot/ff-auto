from typing import List, Literal, Optional

from pydantic import BaseModel, Field


MediaType = Literal["image", "video"]
EvaluationStatus = Literal["pending", "completed", "failed"]


class EvaluationRequest(BaseModel):
    media_type: MediaType
    media_path: str = Field(min_length=1)
    prompt: Optional[str] = None


class EvaluationScore(BaseModel):
    dimension: str
    score: int = Field(ge=1, le=5)
    rationale: str = Field(min_length=1)


class EvaluationResult(BaseModel):
    id: int
    status: EvaluationStatus
    media_type: MediaType
    media_path: str
    prompt: Optional[str] = None
    model: str
    rubric_version: str
    scores: List[EvaluationScore] = Field(default_factory=list)
    overall_score: Optional[float] = None
    summary: Optional[str] = None
    error_message: Optional[str] = None
    created_at: str
    completed_at: Optional[str] = None


class EvaluationListResponse(BaseModel):
    items: List[EvaluationResult]

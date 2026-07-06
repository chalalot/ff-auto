import json
import re
from typing import Any, Dict, List, Optional

from backend.config import GlobalConfig
from backend.database.evaluations_storage import EvaluationsStorage
from backend.models.evaluation import EvaluationRequest, EvaluationResult, EvaluationScore
from backend.third_parties.llm_evaluator_client import LLMEvaluatorClient


RUBRIC_VERSION = "production-v1"
PRODUCTION_RUBRIC_V1 = {
    "artifact_free": {
        "definition": (
            "Measures visible generation defects unrelated to the intended style, "
            "including warped anatomy, corrupted objects, broken textures, "
            "watermarks, text glitches, flicker, or frame corruption."
        ),
        "applies_to": ["image", "video"],
        "score_anchors": {
            1: "Severe artifacts dominate the output and make it unusable.",
            3: "Some noticeable artifacts exist, but the subject and scene remain understandable.",
            5: "No obvious generation artifacts are visible at normal viewing size.",
        },
        "do_not_score": [
            "first-3s hook",
            "social media appeal",
            "platform readiness",
            "scene pacing",
        ],
    },
    "identity_consistency": {
        "definition": (
            "Measures whether the main subject, face, body, clothing, and key "
            "objects remain consistent without unwanted morphing or identity drift."
        ),
        "applies_to": ["image", "video"],
        "score_anchors": {
            1: "Subject identity or key objects are badly distorted, swapped, or unstable.",
            3: "Minor identity drift or morphing is visible but does not fully break the output.",
            5: "Subject identity and key objects remain stable and coherent.",
        },
        "do_not_score": [
            "brand fit",
            "story quality",
            "audience targeting",
            "scene transition strategy",
        ],
    },
    "visual_naturalness": {
        "definition": (
            "Measures whether lighting, perspective, anatomy, materials, shadows, "
            "and composition look physically plausible and production-ready."
        ),
        "applies_to": ["image", "video"],
        "score_anchors": {
            1: "The image or frames look clearly unnatural, physically impossible, or low quality.",
            3: "Mostly plausible visuals with visible oddities in anatomy, lighting, or perspective.",
            5: "Visuals look natural, coherent, and ready for production review.",
        },
        "do_not_score": [
            "virality",
            "caption potential",
            "first-3s hook",
            "platform readiness",
        ],
    },
    "motion_naturalness": {
        "definition": (
            "Measures whether subject, camera, fabric, hair, hands, and object "
            "motion look smooth and physically plausible over time."
        ),
        "applies_to": ["video"],
        "score_anchors": {
            1: "Motion is broken, jittery, sliding, morphing, or physically impossible.",
            3: "Motion is understandable but has visible stiffness, wobble, or minor morphing.",
            5: "Motion is smooth, temporally stable, and physically plausible.",
        },
        "do_not_score": [
            "transition smoothness between scenes",
            "first-3s hook",
            "edit pacing",
            "music sync",
        ],
    },
}


class EvaluationService:
    def __init__(
        self,
        storage: Optional[EvaluationsStorage] = None,
        evaluator_client: Optional[LLMEvaluatorClient] = None,
    ):
        self.storage = storage or EvaluationsStorage()
        self.evaluator_client = evaluator_client or LLMEvaluatorClient()
        self.model = getattr(self.evaluator_client, "model", GlobalConfig.EVALUATOR_MODEL)

    def evaluate(self, request: EvaluationRequest) -> EvaluationResult:
        evaluation_id = self.storage.create_pending(
            media_type=request.media_type,
            media_path=request.media_path,
            prompt=request.prompt,
            model=self.model,
            rubric_version=RUBRIC_VERSION,
        )

        raw_response = None
        try:
            rubric = self._rubric_for_media_type(request.media_type)
            required_dimensions = list(rubric.keys())
            raw_response = self.evaluator_client.evaluate(
                {
                    "media_type": request.media_type,
                    "media_path": request.media_path,
                    "prompt": request.prompt,
                    "rubric_version": RUBRIC_VERSION,
                    "required_dimensions": required_dimensions,
                    "rubric": rubric,
                }
            )
            scores, summary = self._parse_response(raw_response, required_dimensions)
            overall_score = round(
                sum(score["score"] for score in scores) / len(scores),
                2,
            )
            self.storage.update_completed(
                evaluation_id=evaluation_id,
                scores=scores,
                overall_score=overall_score,
                summary=summary,
                raw_response=raw_response,
            )
        except Exception as exc:
            self.storage.update_failed(
                evaluation_id=evaluation_id,
                error_message=str(exc),
                raw_response=raw_response,
            )

        result = self.get_evaluation(evaluation_id)
        if result is None:
            raise RuntimeError(f"Evaluation {evaluation_id} was not persisted.")
        return result

    def get_evaluation(self, evaluation_id: int) -> Optional[EvaluationResult]:
        row = self.storage.get_evaluation(evaluation_id)
        return self._result_from_row(row) if row else None

    def list_evaluations(
        self,
        limit: int = 50,
        media_path: Optional[str] = None,
    ) -> List[EvaluationResult]:
        return [
            self._result_from_row(row)
            for row in self.storage.list_evaluations(limit=limit, media_path=media_path)
        ]

    def _rubric_for_media_type(self, media_type: str) -> Dict[str, Dict[str, Any]]:
        return {
            dimension: guideline
            for dimension, guideline in PRODUCTION_RUBRIC_V1.items()
            if media_type in guideline["applies_to"]
        }

    def _parse_response(
        self,
        raw_response: Any,
        required_dimensions: List[str],
    ) -> tuple[List[Dict[str, Any]], Optional[str]]:
        if isinstance(raw_response, str):
            raw_response = self._parse_json_object_text(raw_response)
        if not isinstance(raw_response, dict):
            raise ValueError("Evaluator response must be a JSON object.")

        raw_scores = raw_response.get("scores")
        if not isinstance(raw_scores, list):
            raise ValueError("Evaluator response must include a scores array.")

        by_dimension: Dict[str, Dict[str, Any]] = {}
        for item in raw_scores:
            if not isinstance(item, dict):
                continue
            dimension = item.get("dimension") or item.get("metric") or item.get("name")
            if dimension not in required_dimensions:
                continue
            score = item.get("score")
            rationale = item.get("rationale")
            if not isinstance(score, int) or score < 1 or score > 5:
                raise ValueError(f"Invalid score for dimension {dimension}.")
            if not isinstance(rationale, str) or not rationale.strip():
                raise ValueError(f"Missing rationale for dimension {dimension}.")
            by_dimension[dimension] = {
                "dimension": dimension,
                "score": score,
                "rationale": rationale.strip(),
            }

        missing = [dim for dim in required_dimensions if dim not in by_dimension]
        if missing:
            raise ValueError(f"Evaluator response missing dimensions: {', '.join(missing)}")

        scores = [by_dimension[dim] for dim in required_dimensions]
        summary = raw_response.get("summary")
        if summary is not None and not isinstance(summary, str):
            raise ValueError("Evaluator summary must be text.")
        return scores, summary

    def _parse_json_object_text(self, text: str) -> Dict[str, Any]:
        stripped = re.sub(r"<thought>.*?</thought>", "", text, flags=re.DOTALL).strip()
        if not stripped:
            raise ValueError("Evaluator returned an empty response.")

        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            pass

        fenced_match = None
        for marker in ("```json", "```"):
            start = stripped.find(marker)
            if start == -1:
                continue
            start += len(marker)
            end = stripped.find("```", start)
            if end != -1:
                fenced_match = stripped[start:end].strip()
                break
        if fenced_match:
            return json.loads(fenced_match)

        start = stripped.find("{")
        end = stripped.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ValueError("Evaluator response did not contain a JSON object.")
        return json.loads(stripped[start : end + 1])

    def _result_from_row(self, row: Dict[str, Any]) -> EvaluationResult:
        return EvaluationResult(
            id=row["id"],
            status=row["status"],
            media_type=row["media_type"],
            media_path=row["media_path"],
            prompt=row.get("prompt"),
            model=row["model"],
            rubric_version=row["rubric_version"],
            scores=[EvaluationScore(**score) for score in row.get("scores", [])],
            overall_score=row.get("overall_score"),
            summary=row.get("summary"),
            error_message=row.get("error_message"),
            created_at=str(row["created_at"]),
            completed_at=str(row["completed_at"]) if row.get("completed_at") else None,
        )

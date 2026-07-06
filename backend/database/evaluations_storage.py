import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select, update

from .db_utils import format_legacy_ts as _format_ts
from .engine import session_scope
from .models import Evaluation

logger = logging.getLogger(__name__)


class EvaluationsStorage:
    """Postgres storage adapter for media evaluation attempts."""

    def __init__(self):
        # Schema is owned by Alembic; nothing to initialize here.
        pass

    def create_pending(
        self,
        media_type: str,
        media_path: str,
        prompt: Optional[str],
        model: str,
        rubric_version: str,
    ) -> int:
        with session_scope() as session:
            row = Evaluation(
                media_type=media_type,
                media_path=media_path,
                prompt=prompt,
                model=model,
                rubric_version=rubric_version,
                status="pending",
            )
            session.add(row)
            session.flush()
            return row.id

    def update_completed(
        self,
        evaluation_id: int,
        scores: List[Dict[str, Any]],
        overall_score: float,
        summary: Optional[str],
        raw_response: Any,
    ) -> None:
        with session_scope() as session:
            session.execute(
                update(Evaluation)
                .where(Evaluation.id == evaluation_id)
                .values(
                    status="completed",
                    scores_json=json.dumps(scores),
                    overall_score=overall_score,
                    summary=summary,
                    error_message=None,
                    raw_response=self._json_dumps(raw_response),
                    completed_at=datetime.now(timezone.utc),
                )
            )

    def update_failed(
        self,
        evaluation_id: int,
        error_message: str,
        raw_response: Any = None,
    ) -> None:
        with session_scope() as session:
            session.execute(
                update(Evaluation)
                .where(Evaluation.id == evaluation_id)
                .values(
                    status="failed",
                    scores_json="[]",
                    overall_score=None,
                    summary=None,
                    error_message=error_message,
                    raw_response=self._json_dumps(raw_response),
                    completed_at=datetime.now(timezone.utc),
                )
            )

    def get_evaluation(self, evaluation_id: int) -> Optional[Dict[str, Any]]:
        with session_scope() as session:
            row = session.get(Evaluation, evaluation_id)
            return self._decode_row(row) if row else None

    def list_evaluations(
        self,
        limit: int = 50,
        media_path: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        with session_scope() as session:
            stmt = select(Evaluation).order_by(Evaluation.id.desc()).limit(limit)
            if media_path is not None:
                stmt = stmt.where(Evaluation.media_path == media_path)
            rows = session.execute(stmt).scalars().all()
            return [self._decode_row(row) for row in rows]

    def get_latest_for_paths(self, paths: List[str]) -> Dict[str, Dict[str, Any]]:
        if not paths:
            return {}
        with session_scope() as session:
            stmt = (
                select(Evaluation)
                .where(Evaluation.media_path.in_(paths))
                .order_by(Evaluation.id.asc())
            )
            rows = session.execute(stmt).scalars().all()
            # Higher id wins because we iterate ascending and overwrite.
            latest: Dict[str, Dict[str, Any]] = {}
            for row in rows:
                decoded = self._decode_row(row)
                latest[decoded["media_path"]] = decoded
            return latest

    def get_score_summary(self) -> Dict[str, Any]:
        with session_scope() as session:
            stmt = select(Evaluation).order_by(Evaluation.id.asc())
            rows = session.execute(stmt).scalars().all()
            latest: Dict[str, Dict[str, Any]] = {}
            for row in rows:
                decoded = self._decode_row(row)
                latest[decoded["media_path"]] = decoded

        evaluated_paths = set()
        failed_paths = set()
        scores = []
        for path, row in latest.items():
            if row["status"] == "completed":
                evaluated_paths.add(path)
                if row.get("overall_score") is not None:
                    scores.append(row["overall_score"])
            elif row["status"] == "failed":
                failed_paths.add(path)

        avg = round(sum(scores) / len(scores), 2) if scores else None
        return {
            "evaluated": len(evaluated_paths),
            "failed": len(failed_paths),
            "avg_overall_score": avg,
            "evaluated_paths": evaluated_paths,
            "failed_paths": failed_paths,
        }

    def _decode_row(self, row: Evaluation) -> Dict[str, Any]:
        return {
            "id": row.id,
            "media_type": row.media_type,
            "media_path": row.media_path,
            "prompt": row.prompt,
            "model": row.model,
            "rubric_version": row.rubric_version,
            "status": row.status,
            "overall_score": row.overall_score,
            "summary": row.summary,
            "error_message": row.error_message,
            "raw_response": row.raw_response,
            "created_at": _format_ts(row.created_at),
            "completed_at": _format_ts(row.completed_at),
            "scores": json.loads(row.scores_json or "[]"),
        }

    def _json_dumps(self, value: Any) -> Optional[str]:
        if value is None:
            return None
        if isinstance(value, str):
            return value
        return json.dumps(value)

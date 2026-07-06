import json
import logging
import sqlite3
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class EvaluationsStorage:
    """SQLite storage adapter for media evaluation attempts."""

    def __init__(self, db_path: str = "evaluations.db"):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self):
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS evaluations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    media_type TEXT NOT NULL,
                    media_path TEXT NOT NULL,
                    prompt TEXT,
                    model TEXT NOT NULL,
                    rubric_version TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    scores_json TEXT NOT NULL DEFAULT '[]',
                    overall_score REAL,
                    summary TEXT,
                    error_message TEXT,
                    raw_response TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP
                );
                """
            )
            conn.commit()
        except Exception as exc:
            logger.error(f"Failed to initialize evaluations table: {exc}")
            raise
        finally:
            conn.close()

    def create_pending(
        self,
        media_type: str,
        media_path: str,
        prompt: Optional[str],
        model: str,
        rubric_version: str,
    ) -> int:
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO evaluations (
                    media_type, media_path, prompt, model, rubric_version, status
                )
                VALUES (?, ?, ?, ?, ?, 'pending')
                """,
                (media_type, media_path, prompt, model, rubric_version),
            )
            row_id = cursor.lastrowid
            conn.commit()
            return row_id
        finally:
            conn.close()

    def update_completed(
        self,
        evaluation_id: int,
        scores: List[Dict[str, Any]],
        overall_score: float,
        summary: Optional[str],
        raw_response: Any,
    ) -> None:
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                UPDATE evaluations
                SET status = 'completed',
                    scores_json = ?,
                    overall_score = ?,
                    summary = ?,
                    error_message = NULL,
                    raw_response = ?,
                    completed_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    json.dumps(scores),
                    overall_score,
                    summary,
                    self._json_dumps(raw_response),
                    evaluation_id,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def update_failed(
        self,
        evaluation_id: int,
        error_message: str,
        raw_response: Any = None,
    ) -> None:
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                UPDATE evaluations
                SET status = 'failed',
                    scores_json = '[]',
                    overall_score = NULL,
                    summary = NULL,
                    error_message = ?,
                    raw_response = ?,
                    completed_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (error_message, self._json_dumps(raw_response), evaluation_id),
            )
            conn.commit()
        finally:
            conn.close()

    def get_evaluation(self, evaluation_id: int) -> Optional[Dict[str, Any]]:
        conn = self._get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT * FROM evaluations WHERE id = ?", (evaluation_id,))
            row = cursor.fetchone()
            return self._decode_row(row) if row else None
        finally:
            conn.close()

    def list_evaluations(
        self,
        limit: int = 50,
        media_path: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        conn = self._get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        try:
            if media_path is None:
                cursor.execute(
                    """
                    SELECT * FROM evaluations
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (limit,),
                )
            else:
                cursor.execute(
                    """
                    SELECT * FROM evaluations
                    WHERE media_path = ?
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (media_path, limit),
                )
            return [self._decode_row(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def get_latest_for_paths(self, paths: List[str]) -> Dict[str, Dict[str, Any]]:
        if not paths:
            return {}
        conn = self._get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        try:
            placeholders = ",".join("?" for _ in paths)
            cursor.execute(
                f"""
                SELECT * FROM evaluations
                WHERE media_path IN ({placeholders})
                ORDER BY id ASC
                """,
                tuple(paths),
            )
            # Higher id wins because we iterate ascending and overwrite.
            latest: Dict[str, Dict[str, Any]] = {}
            for row in cursor.fetchall():
                decoded = self._decode_row(row)
                latest[decoded["media_path"]] = decoded
            return latest
        finally:
            conn.close()

    def get_score_summary(self) -> Dict[str, Any]:
        conn = self._get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT * FROM evaluations ORDER BY id ASC")
            latest: Dict[str, Dict[str, Any]] = {}
            for row in cursor.fetchall():
                decoded = self._decode_row(row)
                latest[decoded["media_path"]] = decoded
        finally:
            conn.close()

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

    def _decode_row(self, row: sqlite3.Row) -> Dict[str, Any]:
        data = dict(row)
        data["scores"] = json.loads(data.pop("scores_json") or "[]")
        return data

    def _json_dumps(self, value: Any) -> Optional[str]:
        if value is None:
            return None
        if isinstance(value, str):
            return value
        return json.dumps(value)

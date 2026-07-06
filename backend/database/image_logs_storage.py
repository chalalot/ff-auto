import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, select, update

from .engine import session_scope
from .models import ImageLog

logger = logging.getLogger(__name__)

# Legacy sqlite CURRENT_TIMESTAMP format; ExecutionRecord.created_at is a str.
_TS_FORMAT = "%Y-%m-%d %H:%M:%S"


def _format_ts(value: Optional[datetime]) -> Optional[str]:
    if value is None:
        return None
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc)
    return value.strftime(_TS_FORMAT)


def _row_dict(row: ImageLog) -> dict:
    return {
        "id": row.id,
        "execution_id": row.execution_id,
        "prompt": row.prompt,
        "persona": row.persona,
        "image_ref_path": row.image_ref_path,
        "result_image_path": row.result_image_path,
        "status": row.status,
        "created_at": _format_ts(row.created_at),
    }


class ImageLogsStorage:
    """
    Postgres storage adapter for image generation logs.
    """

    def __init__(self):
        """Initialize storage. Schema is owned by Alembic."""
        pass

    def log_execution(self, execution_id: str, prompt: str, image_ref_path: str = None, persona: str = None) -> int:
        """
        Log a new execution.

        Returns:
            The inserted row ID.
        """
        try:
            with session_scope() as session:
                row = ImageLog(
                    execution_id=execution_id,
                    prompt=prompt,
                    persona=persona,
                    image_ref_path=image_ref_path,
                    result_image_path=None,
                    status="pending",
                )
                session.add(row)
                session.flush()
                return row.id
        except Exception as e:
            logger.error(f"Failed to log execution: {e}")
            raise

    def get_pending_executions(self):
        """
        Get all executions where status is 'pending'.

        Returns:
            List of dictionaries representing rows.
        """
        try:
            with session_scope() as session:
                rows = session.execute(
                    select(ImageLog).where(ImageLog.status == "pending")
                ).scalars().all()
                return [_row_dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to fetch pending executions: {e}")
            return []

    def update_result_path(self, execution_id: str, result_image_path: str, new_ref_path: str = None):
        """
        Update the result_image_path for a given execution_id and set status to 'completed'.
        Optionally update image_ref_path if it was moved/renamed.
        """
        try:
            values = {"result_image_path": result_image_path, "status": "completed"}
            if new_ref_path:
                values["image_ref_path"] = new_ref_path
            with session_scope() as session:
                session.execute(
                    update(ImageLog)
                    .where(ImageLog.execution_id == execution_id)
                    .values(**values)
                )
        except Exception as e:
            logger.error(f"Failed to update result path for {execution_id}: {e}")
            raise

    def log_failed_execution(self, image_ref_path: str, error_message: str, persona: str = None) -> int:
        """Log an execution that failed before reaching ComfyUI (e.g. vision refusal)."""
        synthetic_id = f"failed_{uuid.uuid4().hex[:12]}"
        try:
            with session_scope() as session:
                row = ImageLog(
                    execution_id=synthetic_id,
                    prompt=error_message,
                    persona=persona,
                    image_ref_path=image_ref_path,
                    result_image_path=None,
                    status="failed",
                )
                session.add(row)
                session.flush()
                return row.id
        except Exception as e:
            logger.error(f"Failed to log failed execution: {e}")
            raise

    def mark_as_failed(self, execution_id: str):
        """
        Mark an execution as failed.
        """
        try:
            with session_scope() as session:
                session.execute(
                    update(ImageLog)
                    .where(ImageLog.execution_id == execution_id)
                    .values(status="failed")
                )
        except Exception as e:
            logger.error(f"Failed to mark execution {execution_id} as failed: {e}")
            raise

    def get_execution_by_result_path(self, result_image_path: str):
        """Get execution details by result image path.

        A single execution can produce several result images (variations); their
        paths are stored comma-joined in ``result_image_path``. We therefore match
        in three escalating steps:
          1. exact value (single-image executions),
          2. membership in the comma-joined list,
          3. basename match — so lookups still succeed when the caller's path
             prefix differs from the stored one (e.g. the gallery scans a
             different mount than the worker that wrote the row).
        """
        try:
            with session_scope() as session:
                # Step 1: exact match (fast path for single-image executions).
                row = session.execute(
                    select(ImageLog).where(
                        ImageLog.result_image_path == result_image_path
                    )
                ).scalars().first()
                if row:
                    return _row_dict(row)

                # Steps 2 & 3: narrow candidates by basename, then verify in Python.
                target_base = os.path.basename(result_image_path)
                if not target_base:
                    return None
                candidates = session.execute(
                    select(ImageLog).where(
                        ImageLog.result_image_path.like(f"%{target_base}%")
                    )
                ).scalars().all()
                for row in candidates:
                    parts = [p for p in (row.result_image_path or "").split(",") if p]
                    if result_image_path in parts:
                        return _row_dict(row)
                    if target_base in {os.path.basename(p) for p in parts}:
                        return _row_dict(row)
                return None
        except Exception as e:
            logger.error(f"Failed to fetch execution by path: {e}")
            return None

    def get_recent_executions(self, limit: int = 50):
        """Get recent executions ordered by creation time descending."""
        try:
            with session_scope() as session:
                rows = session.execute(
                    select(ImageLog).order_by(ImageLog.id.desc()).limit(limit)
                ).scalars().all()
                return [_row_dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to fetch recent executions: {e}")
            return []

    def get_ref_path_use_counts(self) -> dict:
        """Return {image_ref_path: count} for all non-null ref paths."""
        try:
            with session_scope() as session:
                rows = session.execute(
                    select(ImageLog.image_ref_path, func.count())
                    .where(ImageLog.image_ref_path.is_not(None))
                    .group_by(ImageLog.image_ref_path)
                ).all()
                return {path: count for path, count in rows}
        except Exception as e:
            logger.error(f"Failed to get ref path use counts: {e}")
            return {}

    def get_all_completed_executions(self):
        """Get all completed executions (where result_image_path is not null)."""
        try:
            with session_scope() as session:
                rows = session.execute(
                    select(ImageLog).where(ImageLog.result_image_path.is_not(None))
                ).scalars().all()
                return [_row_dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to fetch all completed executions: {e}")
            return []

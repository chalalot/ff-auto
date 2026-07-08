import logging
from typing import Optional

from sqlalchemy import func, select, update

from .db_utils import format_legacy_ts as _format_ts
from .engine import session_scope
from .models import VideoLog

logger = logging.getLogger(__name__)


def _row_dict(row: VideoLog) -> dict:
    return {
        "id": row.id,
        "batch_id": row.batch_id,
        "execution_id": row.execution_id,
        "prompt": row.prompt,
        "source_image_path": row.source_image_path,
        "video_output_path": row.video_output_path,
        "status": row.status,
        "created_at": _format_ts(row.created_at),
        "filename_id": row.filename_id,
    }


class VideoLogsStorage:
    """
    Postgres storage adapter for video generation logs.
    """

    def __init__(self):
        """Initialize storage. Schema is owned by Alembic."""
        pass

    def log_execution(self, execution_id: str, prompt: str, source_image_path: str = None, batch_id: str = None, filename_id: str = None, project_id: str = None, created_by_member_id: str = None) -> int:
        """
        Log a new execution.

        Returns:
            The inserted row ID.
        """
        try:
            with session_scope() as session:
                row = VideoLog(
                    execution_id=execution_id,
                    prompt=prompt,
                    source_image_path=source_image_path,
                    video_output_path=None,
                    status="pending",
                    batch_id=batch_id,
                    filename_id=filename_id,
                    project_id=project_id,
                    created_by_member_id=created_by_member_id,
                )
                session.add(row)
                session.flush()
                return row.id
        except Exception as e:
            logger.error(f"Failed to log execution: {e}")
            raise

    def update_result(self, execution_id: str, video_output_path: str = None, status: str = 'completed'):
        """
        Update the result for a given execution_id.
        """
        try:
            values = {"status": status}
            if video_output_path:
                values["video_output_path"] = video_output_path
            with session_scope() as session:
                session.execute(
                    update(VideoLog)
                    .where(VideoLog.execution_id == execution_id)
                    .values(**values)
                )
        except Exception as e:
            logger.error(f"Failed to update result for {execution_id}: {e}")
            raise

    def get_execution(self, execution_id: str):
        """Get execution details by execution ID."""
        try:
            with session_scope() as session:
                row = session.execute(
                    select(VideoLog).where(VideoLog.execution_id == execution_id)
                ).scalars().first()
                return _row_dict(row) if row else None
        except Exception as e:
            logger.error(f"Failed to fetch execution: {e}")
            return None

    def get_recent_executions(self, limit: int = 50):
        """Get recent executions ordered by creation time descending."""
        try:
            with session_scope() as session:
                rows = session.execute(
                    select(VideoLog).order_by(VideoLog.id.desc()).limit(limit)
                ).scalars().all()
                return [_row_dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to fetch recent executions: {e}")
            return []

    def get_incomplete_batches(self):
        """
        Get list of batch_ids that have pending tasks.
        Returns distinct batch_ids and their timestamps.
        """
        try:
            with session_scope() as session:
                # A batch with at least one non-terminal (pending) row is
                # incomplete. created_at is the batch's earliest row time.
                rows = session.execute(
                    select(
                        VideoLog.batch_id,
                        func.min(VideoLog.created_at).label("created_at"),
                        func.count().label("count"),
                    )
                    .where(
                        VideoLog.batch_id.is_not(None),
                        VideoLog.status.not_in(["completed", "failed"]),
                    )
                    .group_by(VideoLog.batch_id)
                    .order_by(func.min(VideoLog.created_at).desc())
                ).all()
                return [
                    {
                        "batch_id": batch_id,
                        "created_at": _format_ts(created_at),
                        "count": count,
                    }
                    for batch_id, created_at, count in rows
                ]
        except Exception as e:
            logger.error(f"Failed to fetch incomplete batches: {e}")
            return []

    def get_batch_executions(self, batch_id: str):
        """
        Get all executions for a specific batch.
        """
        try:
            with session_scope() as session:
                rows = session.execute(
                    select(VideoLog)
                    .where(VideoLog.batch_id == batch_id)
                    .order_by(VideoLog.id.asc())
                ).scalars().all()
                return [_row_dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to fetch batch executions: {e}")
            return []

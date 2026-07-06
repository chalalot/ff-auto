import json
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import delete, select, update

from .engine import session_scope
from .models import RunpodJob

logger = logging.getLogger(__name__)


def _row_dict(row: RunpodJob) -> dict:
    return {
        "id": row.id,
        "job_id": row.job_id,
        "endpoint_id": row.endpoint_id,
        "lora_name": row.lora_name,
        "submitted_at": row.submitted_at,
        "job_input": json.loads(row.job_input) if row.job_input else {},
        "status": row.status,
        "output": json.loads(row.output) if row.output else None,
        "updated_at": row.updated_at,
    }


class RunpodJobsStorage:
    def __init__(self):
        # Schema is owned by Alembic; nothing to initialize here.
        pass

    def insert(
        self,
        job_id: str,
        endpoint_id: str,
        lora_name: str,
        submitted_at: str,
        job_input: dict,
    ) -> None:
        """Insert a job record. job_id is unique; inserting a duplicate
        raises IntegrityError — matching the legacy sqlite behavior, where
        the UNIQUE constraint surfaced the collision to the caller instead
        of silently keeping the stale row."""
        try:
            with session_scope() as session:
                session.add(
                    RunpodJob(
                        job_id=job_id,
                        endpoint_id=endpoint_id,
                        lora_name=lora_name,
                        submitted_at=submitted_at,
                        job_input=json.dumps(job_input),
                        status=None,
                        output=None,
                        updated_at=None,
                    )
                )
        except Exception as e:
            logger.error(f"[runpod_jobs] insert failed: {e}")
            raise

    def update_status(
        self,
        job_id: str,
        status: str,
        output: Optional[dict] = None,
    ) -> None:
        try:
            with session_scope() as session:
                values = {
                    "status": status,
                    "updated_at": datetime.utcnow().isoformat(),
                }
                # Legacy COALESCE(?, output): only overwrite when provided.
                if output is not None:
                    values["output"] = json.dumps(output)
                session.execute(
                    update(RunpodJob)
                    .where(RunpodJob.job_id == job_id)
                    .values(**values)
                )
        except Exception as e:
            logger.error(f"[runpod_jobs] update_status failed: {e}")
            raise

    def get_job(self, job_id: str) -> Optional[dict]:
        with session_scope() as session:
            row = session.execute(
                select(RunpodJob).where(RunpodJob.job_id == job_id)
            ).scalars().first()
            return _row_dict(row) if row else None

    def delete_job(self, job_id: str) -> None:
        with session_scope() as session:
            session.execute(delete(RunpodJob).where(RunpodJob.job_id == job_id))

    def list_jobs(self, limit: int = 100) -> list[dict]:
        with session_scope() as session:
            rows = session.execute(
                select(RunpodJob).order_by(RunpodJob.id.desc()).limit(limit)
            ).scalars().all()
            return [_row_dict(row) for row in rows]

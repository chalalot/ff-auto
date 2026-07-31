"""
Postgres storage for the phase-2 prompt review queue.

State machine (all transitions guarded by WHERE clauses so concurrent
callers — double-clicks, two reviewers, celery redelivery — are safe):

    pending_review -> approved -> dispatched -> completed | failed
    pending_review | failed -> discarded
    failed -> approved (retry via claim_for_dispatch)
"""
import logging
import math
import uuid
from typing import Optional

from sqlalchemy import func, select, update

from .db_utils import format_legacy_ts as _format_ts
from .engine import session_scope
from .models import GenerationRequest

logger = logging.getLogger(__name__)

PENDING_REVIEW = "pending_review"
APPROVED = "approved"
DISPATCHED = "dispatched"
COMPLETED = "completed"
FAILED = "failed"
DISCARDED = "discarded"

ALL_STATUSES = {PENDING_REVIEW, APPROVED, DISPATCHED, COMPLETED, FAILED, DISCARDED}


class InvalidStateError(Exception):
    """Raised when an operation is illegal for the row's current status."""


def _row_dict(row: GenerationRequest) -> dict:
    return {
        "id": row.id,
        "batch_id": row.batch_id,
        "source_image_path": row.source_image_path,
        "original_prompt": row.original_prompt,
        "prompt": row.prompt,
        "provider": row.provider,
        "workflow_name": row.workflow_name,
        "settings": row.settings or {},
        "status": row.status,
        "execution_id": row.execution_id,
        "result_path": row.result_path,
        "error": row.error,
        "project_id": row.project_id,
        "created_by_member_id": row.created_by_member_id,
        "created_at": _format_ts(row.created_at),
        "updated_at": _format_ts(row.updated_at),
    }


class GenerationRequestsStorage:
    """Schema is owned by Alembic; this class only reads/writes rows."""

    def create_requests(
        self,
        items: list,
        batch_id: Optional[str] = None,
        project_id: Optional[str] = None,
        created_by_member_id: Optional[str] = None,
    ) -> dict:
        batch = batch_id or uuid.uuid4().hex
        ids = []
        with session_scope() as session:
            for item in items:
                row = GenerationRequest(
                    id=uuid.uuid4().hex,
                    batch_id=batch,
                    source_image_path=item["source_image_path"],
                    original_prompt=item["prompt"],
                    prompt=item["prompt"],
                    provider=item["provider"],
                    workflow_name=item.get("workflow_name"),
                    settings=item.get("settings") or {},
                    status=PENDING_REVIEW,
                    project_id=project_id,
                    created_by_member_id=created_by_member_id,
                )
                session.add(row)
                ids.append(row.id)
        return {"batch_id": batch, "request_ids": ids}

    def get_request(self, request_id: str) -> Optional[dict]:
        with session_scope() as session:
            row = session.get(GenerationRequest, request_id)
            return _row_dict(row) if row else None

    def list_requests(
        self,
        status: Optional[str] = None,
        batch_id: Optional[str] = None,
        project_id: Optional[str] = None,
        providers: Optional[list] = None,
        page: int = 1,
        per_page: int = 50,
    ) -> dict:
        # Scope (project/batch/provider) applies to both the page and the
        # per-status counts; `status` narrows the page only, so a caller
        # filtering to one status still sees the whole breakdown.
        #
        # `providers` is what keeps the image and video surfaces honest: both
        # write into this one queue, so a counter that ignores provider reports
        # video work as image work.
        scope = []
        if batch_id:
            scope.append(GenerationRequest.batch_id == batch_id)
        if project_id == "unassigned":
            scope.append(GenerationRequest.project_id.is_(None))
        elif project_id:
            scope.append(GenerationRequest.project_id == project_id)
        if providers:
            scope.append(GenerationRequest.provider.in_(providers))

        with session_scope() as session:
            query = select(GenerationRequest).where(*scope)
            if status:
                query = query.where(GenerationRequest.status == status)
            total = session.execute(
                select(func.count()).select_from(query.subquery())
            ).scalar() or 0
            rows = session.execute(
                query.order_by(GenerationRequest.created_at.desc(),
                               GenerationRequest.id.desc())
                .offset((page - 1) * per_page)
                .limit(per_page)
            ).scalars().all()
            # One GROUP BY instead of six queries. Independent of pagination so
            # the Flow rail's stage counters stay right past `per_page`.
            status_counts = dict(
                session.execute(
                    select(GenerationRequest.status, func.count())
                    .where(*scope)
                    .group_by(GenerationRequest.status)
                ).all()
            )
            return {
                "items": [_row_dict(r) for r in rows],
                "total": total,
                "page": page,
                "pages": max(1, math.ceil(total / per_page)),
                "status_counts": status_counts,
            }

    def update_request(
        self,
        request_id: str,
        prompt: Optional[str] = None,
        settings: Optional[dict] = None,
    ) -> Optional[dict]:
        values = {"updated_at": func.now()}
        if prompt is not None:
            values["prompt"] = prompt
        if settings is not None:
            values["settings"] = settings
        with session_scope() as session:
            row = session.execute(
                update(GenerationRequest)
                .where(
                    GenerationRequest.id == request_id,
                    GenerationRequest.status.in_([PENDING_REVIEW, FAILED, COMPLETED]),
                )
                .values(**values)
                .returning(GenerationRequest)
            ).scalars().first()
            if row is not None:
                return _row_dict(row)
            current = session.get(GenerationRequest, request_id)
            if current is None:
                return None
            raise InvalidStateError(
                f"Request {request_id} is {current.status!r}; only "
                f"{PENDING_REVIEW!r}/{FAILED!r}/{COMPLETED!r} rows can be edited."
            )

    def discard_request(self, request_id: str) -> Optional[dict]:
        with session_scope() as session:
            row = session.execute(
                update(GenerationRequest)
                .where(
                    GenerationRequest.id == request_id,
                    GenerationRequest.status.in_([PENDING_REVIEW, FAILED]),
                )
                .values(status=DISCARDED, updated_at=func.now())
                .returning(GenerationRequest)
            ).scalars().first()
            if row is not None:
                return _row_dict(row)
            current = session.get(GenerationRequest, request_id)
            if current is None:
                return None
            raise InvalidStateError(
                f"Request {request_id} is {current.status!r}; only "
                f"{PENDING_REVIEW!r}/{FAILED!r} rows can be discarded."
            )

    def claim_for_dispatch(self, ids: list) -> list:
        """Approve the claimable subset of ``ids`` atomically (idempotent)."""
        if not ids:
            return []
        with session_scope() as session:
            claimed = session.execute(
                update(GenerationRequest)
                .where(
                    GenerationRequest.id.in_(ids),
                    GenerationRequest.status.in_([PENDING_REVIEW, FAILED]),
                )
                .values(status=APPROVED, error=None, updated_at=func.now())
                .returning(GenerationRequest.id)
            ).scalars().all()
        # Preserve caller order for deterministic responses.
        claimed_set = set(claimed)
        return [i for i in ids if i in claimed_set]

    def begin_dispatch(self, request_id: str) -> Optional[dict]:
        """approved -> dispatched. Returns the row, or None if not claimable
        (already dispatched by a redelivered task, or never approved)."""
        with session_scope() as session:
            row = session.execute(
                update(GenerationRequest)
                .where(
                    GenerationRequest.id == request_id,
                    GenerationRequest.status == APPROVED,
                )
                .values(status=DISPATCHED, updated_at=func.now())
                .returning(GenerationRequest)
            ).scalars().first()
            return _row_dict(row) if row else None

    def set_execution(self, request_id: str, execution_id: str) -> None:
        with session_scope() as session:
            session.execute(
                update(GenerationRequest)
                .where(GenerationRequest.id == request_id)
                .values(execution_id=execution_id, updated_at=func.now())
            )

    def mark_failed(self, request_id: str, error: str) -> Optional[dict]:
        """approved/dispatched -> failed.

        Returns the updated row, or None if it wasn't in flight. Worker callers
        ignore the return; the reaper endpoint uses it to tell 404 from 409.
        """
        with session_scope() as session:
            row = session.execute(
                update(GenerationRequest)
                .where(
                    GenerationRequest.id == request_id,
                    GenerationRequest.status.in_([APPROVED, DISPATCHED]),
                )
                .values(status=FAILED, error=error, updated_at=func.now())
                .returning(GenerationRequest)
            ).scalars().first()
            return _row_dict(row) if row else None

    def get_by_execution_id(self, execution_id: str) -> Optional[dict]:
        """The request that produced an execution, whatever state it ended in.

        A batch dispatches one request per execution, so this is unambiguous.
        """
        with session_scope() as session:
            row = session.execute(
                select(GenerationRequest)
                .where(GenerationRequest.execution_id == execution_id)
                .order_by(GenerationRequest.created_at.desc())
            ).scalars().first()
            return _row_dict(row) if row else None

    def mark_completed_by_execution(
        self, execution_id: str, result_path: Optional[str] = None
    ) -> bool:
        with session_scope() as session:
            rows = session.execute(
                update(GenerationRequest)
                .where(
                    GenerationRequest.execution_id == execution_id,
                    GenerationRequest.status == DISPATCHED,
                )
                .values(
                    status=COMPLETED, result_path=result_path,
                    updated_at=func.now(),
                )
                .returning(GenerationRequest.id)
            ).scalars().all()
            return len(rows) > 0

    def mark_failed_by_execution(self, execution_id: str, error: str) -> bool:
        with session_scope() as session:
            rows = session.execute(
                update(GenerationRequest)
                .where(
                    GenerationRequest.execution_id == execution_id,
                    GenerationRequest.status == DISPATCHED,
                )
                .values(status=FAILED, error=error, updated_at=func.now())
                .returning(GenerationRequest.id)
            ).scalars().all()
            return len(rows) > 0

    def clone_request(self, request_id: str) -> dict:
        """Clone a completed or failed request back to pending_review.

        Creates a **new** row so the original execution history is preserved.
        Raises ``InvalidStateError`` if the source row is not completed/failed.
        """
        with session_scope() as session:
            source = session.get(GenerationRequest, request_id)
            if source is None:
                raise KeyError(f"Request {request_id} not found")
            if source.status not in (COMPLETED, FAILED):
                raise InvalidStateError(
                    f"Request {request_id} is {source.status!r}; only "
                    f"{COMPLETED!r}/{FAILED!r} rows can be re-dispatched."
                )
            new_row = GenerationRequest(
                id=uuid.uuid4().hex,
                batch_id=uuid.uuid4().hex,
                source_image_path=source.source_image_path,
                original_prompt=source.prompt,
                prompt=source.prompt,
                provider=source.provider,
                workflow_name=source.workflow_name,
                settings=source.settings or {},
                status=PENDING_REVIEW,
                project_id=source.project_id,
                created_by_member_id=source.created_by_member_id,
            )
            session.add(new_row)
            session.flush()
            return _row_dict(new_row)

    def clone_requests_bulk(self, request_ids: list) -> list:
        """Clone multiple completed/failed requests back to pending_review.

        Returns a list of newly created row dicts.  Rows that are not in a
        clonable state are silently skipped.
        """
        if not request_ids:
            return []
        created = []
        with session_scope() as session:
            sources = session.execute(
                select(GenerationRequest).where(
                    GenerationRequest.id.in_(request_ids),
                    GenerationRequest.status.in_([COMPLETED, FAILED]),
                )
            ).scalars().all()
            batch_id = uuid.uuid4().hex
            for source in sources:
                new_row = GenerationRequest(
                    id=uuid.uuid4().hex,
                    batch_id=batch_id,
                    source_image_path=source.source_image_path,
                    original_prompt=source.prompt,
                    prompt=source.prompt,
                    provider=source.provider,
                    workflow_name=source.workflow_name,
                    settings=source.settings or {},
                    status=PENDING_REVIEW,
                    project_id=source.project_id,
                    created_by_member_id=source.created_by_member_id,
                )
                session.add(new_row)
                created.append(new_row)
            session.flush()
            return [_row_dict(r) for r in created]


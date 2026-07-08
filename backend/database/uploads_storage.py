"""Postgres storage for upload records (phase 3 Assets tab)."""
import math
import uuid
from typing import Optional

from sqlalchemy import func, select

from .db_utils import format_legacy_ts as _format_ts
from .engine import session_scope
from .models import Upload


def _row_dict(row: Upload) -> dict:
    return {
        "id": row.id,
        "filename": row.filename,
        "path": row.path,
        "kind": row.kind,
        "project_id": row.project_id,
        "created_by_member_id": row.created_by_member_id,
        "created_at": _format_ts(row.created_at),
    }


class UploadsStorage:
    """Schema is owned by Alembic; this class only reads/writes rows."""

    def add_upload(
        self,
        filename: str,
        path: str,
        kind: str,
        project_id: Optional[str] = None,
        created_by_member_id: Optional[str] = None,
    ) -> dict:
        with session_scope() as session:
            row = Upload(
                id=uuid.uuid4().hex,
                filename=filename,
                path=path,
                kind=kind,
                project_id=project_id,
                created_by_member_id=created_by_member_id,
            )
            session.add(row)
            session.flush()
            return _row_dict(row)

    def get_upload(self, upload_id: str) -> Optional[dict]:
        with session_scope() as session:
            row = session.get(Upload, upload_id)
            return _row_dict(row) if row else None

    def list_uploads(
        self,
        project_id: Optional[str] = None,
        page: int = 1,
        per_page: int = 50,
    ) -> dict:
        with session_scope() as session:
            query = select(Upload)
            if project_id == "unassigned":
                query = query.where(Upload.project_id.is_(None))
            elif project_id:
                query = query.where(Upload.project_id == project_id)
            total = session.execute(
                select(func.count()).select_from(query.subquery())
            ).scalar() or 0
            rows = session.execute(
                query.order_by(Upload.created_at.desc(), Upload.id.desc())
                .offset((page - 1) * per_page)
                .limit(per_page)
            ).scalars().all()
            return {
                "items": [_row_dict(r) for r in rows],
                "total": total,
                "page": page,
                "pages": max(1, math.ceil(total / per_page)),
            }

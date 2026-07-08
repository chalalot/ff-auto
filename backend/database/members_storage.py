"""Postgres storage for members (phase 3 lightweight identity)."""
import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from .db_utils import format_legacy_ts as _format_ts
from .engine import session_scope
from .models import Member


class MembersStorage:
    """Schema is owned by Alembic; this class only reads/writes rows."""

    def get_or_create(self, name: str) -> str:
        """Return the member id for ``name``, creating the row if needed.
        Race-safe: concurrent first-sight requests both land on the same row
        via ON CONFLICT DO NOTHING + re-select."""
        clean = name.strip()
        with session_scope() as session:
            session.execute(
                pg_insert(Member)
                .values(id=uuid.uuid4().hex, name=clean)
                .on_conflict_do_nothing(index_elements=["name"])
            )
            return session.execute(
                select(Member.id).where(Member.name == clean)
            ).scalar_one()

    def list_members(self) -> list:
        with session_scope() as session:
            rows = session.execute(
                select(Member).order_by(Member.name.asc())
            ).scalars().all()
            return [
                {"id": r.id, "name": r.name, "created_at": _format_ts(r.created_at)}
                for r in rows
            ]

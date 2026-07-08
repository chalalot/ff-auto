"""Postgres storage for projects and project membership (phase 3)."""
import uuid
from typing import Optional

from sqlalchemy import delete, func, select, update

from .db_utils import format_legacy_ts as _format_ts
from .engine import session_scope
from .models import (
    CaptionExport, Evaluation, GenerationRequest, ImageLog, Post, Project,
    ProjectMember, Run, VideoLog,
)

# table name -> (model, primary-key coercion). runpod_jobs is deliberately
# absent: infra rows are never project-scoped.
ASSIGNABLE_TABLES = {
    "generation_requests": (GenerationRequest, str),
    "image_logs": (ImageLog, int),
    "video_logs": (VideoLog, int),
    "evaluations": (Evaluation, int),
    "runs": (Run, str),
    "posts": (Post, str),
    "caption_exports": (CaptionExport, int),
}


def _row_dict(row: Project, member_ids: list) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "description": row.description,
        "owner_member_id": row.owner_member_id,
        "created_at": _format_ts(row.created_at),
        "archived_at": _format_ts(row.archived_at) if row.archived_at else None,
        "member_ids": member_ids,
    }


class ProjectsStorage:
    """Schema is owned by Alembic; this class only reads/writes rows."""

    def create_project(
        self,
        name: str,
        description: Optional[str] = None,
        owner_member_id: Optional[str] = None,
    ) -> dict:
        with session_scope() as session:
            row = Project(
                id=uuid.uuid4().hex,
                name=name.strip(),
                description=description,
                owner_member_id=owner_member_id,
            )
            session.add(row)
            if owner_member_id:
                session.add(ProjectMember(project_id=row.id, member_id=owner_member_id))
            session.flush()
            return _row_dict(row, [owner_member_id] if owner_member_id else [])

    def list_projects(self, include_archived: bool = False) -> list:
        with session_scope() as session:
            query = select(Project).order_by(Project.created_at.desc(), Project.id.desc())
            if not include_archived:
                query = query.where(Project.archived_at.is_(None))
            rows = session.execute(query).scalars().all()
            memberships = session.execute(select(ProjectMember)).all()
            by_project: dict = {}
            for (pm,) in memberships:
                by_project.setdefault(pm.project_id, []).append(pm.member_id)
            return [_row_dict(r, by_project.get(r.id, [])) for r in rows]

    def get_project(self, project_id: str) -> Optional[dict]:
        with session_scope() as session:
            row = session.get(Project, project_id)
            if row is None:
                return None
            return _row_dict(row, self._member_ids(session, project_id))

    def _member_ids(self, session, project_id: str) -> list:
        return list(session.execute(
            select(ProjectMember.member_id)
            .where(ProjectMember.project_id == project_id)
            .order_by(ProjectMember.member_id)
        ).scalars())

    def update_project(
        self,
        project_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        archived: Optional[bool] = None,
    ) -> Optional[dict]:
        values: dict = {}
        if name is not None:
            values["name"] = name.strip()
        if description is not None:
            values["description"] = description
        if archived is True:
            values["archived_at"] = func.now()
        elif archived is False:
            values["archived_at"] = None
        with session_scope() as session:
            if values:
                row = session.execute(
                    update(Project)
                    .where(Project.id == project_id)
                    .values(**values)
                    .returning(Project)
                ).scalars().first()
            else:
                row = session.get(Project, project_id)
            if row is None:
                return None
            return _row_dict(row, self._member_ids(session, project_id))

    def exists(self, project_id: str) -> bool:
        with session_scope() as session:
            return session.get(Project, project_id) is not None

    def add_member(self, project_id: str, member_id: str) -> None:
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        with session_scope() as session:
            session.execute(
                pg_insert(ProjectMember)
                .values(project_id=project_id, member_id=member_id)
                .on_conflict_do_nothing()
            )

    def remove_member(self, project_id: str, member_id: str) -> None:
        with session_scope() as session:
            session.execute(
                delete(ProjectMember).where(
                    ProjectMember.project_id == project_id,
                    ProjectMember.member_id == member_id,
                )
            )

    def list_member_ids(self, project_id: str) -> list:
        with session_scope() as session:
            return self._member_ids(session, project_id)

    def assign_rows(self, project_id: str, table: str, ids: list) -> int:
        """Set project_id on the given rows. Unknown ids are skipped; the
        caller validates ``table`` against ASSIGNABLE_TABLES."""
        model, pk_type = ASSIGNABLE_TABLES[table]
        coerced = []
        for raw in ids:
            try:
                coerced.append(pk_type(raw))
            except (TypeError, ValueError):
                continue
        if not coerced:
            return 0
        with session_scope() as session:
            result = session.execute(
                update(model).where(model.id.in_(coerced)).values(project_id=project_id)
            )
            return result.rowcount

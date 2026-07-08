# Phase 3 — Projects & Members Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Lightweight identity (member picker, no passwords) and project grouping: every created row is stamped with `created_by_member_id` + `project_id`, and each project gets a tabbed workspace over the existing pages.

**Architecture:** Header-based identity (`X-Member-Name`, `X-Project-Id`) resolved by a FastAPI dependency at ingress; row-creating endpoints stamp; Celery completion paths copy scoping from the `generation_requests` row so workers never see headers. Gallery/Analysis are filesystem scans, so their project filter joins against `image_logs` result filenames.

**Tech Stack:** FastAPI + SQLAlchemy 2.0 + Alembic (Postgres 16), Celery, React 18 + TanStack Query + shadcn/ui + axios.

**Spec:** `docs/superpowers/specs/2026-07-08-phase3-projects-members-design.md`

**Note on the Evaluations tab:** no standalone Evaluations page exists in the frontend (evaluation data renders inside the Analysis page). The project workspace therefore has tabs **Gallery / Review / Analysis / Assets**; evaluations surface through the Analysis tab's existing `evaluated` filters. The evaluations *API* still gets a `project_id` filter (Task 8).

## Global Constraints

- **Never run tests against live containers.** Backend tests run in a disposable container against the throwaway `docker-compose.test.yml` Postgres only. Start it once: `docker compose -f docker-compose.test.yml up -d`.
- **Run pytest per-file** (full `tests/` has ~24 known pollution failures unrelated to this work). Use the runner below.
- **Frontend verification:** `cd frontend && ./node_modules/.bin/tsc -b --force` (raw binary — the RTK proxy mangles tsc output). Expected on success: no output, exit 0.
- **`tests/` is gitignored** — stage test files with `git add -f`.
- **Never print/echo values of `DB_PASSWORD` or `POSTGRES_PASSWORD`.**
- Commit trailer on every commit: `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`
- Backend test runner (save once as `/tmp/runtests.sh`, `chmod +x`):

```bash
#!/usr/bin/env bash
# Run a single pytest file inside a throwaway container against postgres-test.
set -euo pipefail
REPO=/home/dmin/ff-auto
FILE="$1"; shift || true
docker run --rm \
  --network ff-auto_default \
  -e TEST_DATABASE_URL=postgresql://test:test@postgres-test:5432/ffauto_test \
  -e PYTHONPATH=/app \
  -v "$REPO/backend:/app/backend:ro" \
  -v "$REPO/tests:/app/tests:ro" \
  -v "$REPO/alembic.ini:/app/alembic.ini:ro" \
  -w /app \
  ff-auto-backend:latest \
  pytest "$FILE" "$@"
```

---

### Task 1: Migration 0003 + SQLAlchemy models

**Files:**
- Create: `backend/database/alembic/versions/0003_projects_members.py`
- Modify: `backend/database/models.py` (append new models; add 2 columns to 7 existing models)
- Test: `tests/test_phase3_schema.py`

**Interfaces:**
- Produces: models `Member`, `Project`, `ProjectMember`, `Upload`; columns `project_id: Optional[str]` + `created_by_member_id: Optional[str]` on `GenerationRequest`, `ImageLog`, `VideoLog`, `Evaluation`, `Run`, `Post`, `CaptionExport`. All later tasks rely on these exact attribute names.

- [ ] **Step 1: Write the failing test**

```python
"""Schema assertions for migration 0003 (projects & members)."""
from sqlalchemy import inspect

SCOPED_TABLES = [
    "generation_requests", "image_logs", "video_logs", "evaluations",
    "runs", "posts", "caption_exports",
]


def test_new_tables_exist(migrated_engine):
    names = set(inspect(migrated_engine).get_table_names())
    assert {"members", "projects", "project_members", "uploads"} <= names


def test_scoping_columns_added(migrated_engine):
    insp = inspect(migrated_engine)
    for table in SCOPED_TABLES:
        cols = {c["name"]: c for c in insp.get_columns(table)}
        assert "project_id" in cols, table
        assert "created_by_member_id" in cols, table
        assert cols["project_id"]["nullable"] is True, table
        assert cols["created_by_member_id"]["nullable"] is True, table


def test_runpod_jobs_stays_global(migrated_engine):
    cols = {c["name"] for c in inspect(migrated_engine).get_columns("runpod_jobs")}
    assert "project_id" not in cols


def test_members_name_unique(migrated_engine):
    insp = inspect(migrated_engine)
    uniques = insp.get_unique_constraints("members") + [
        i for i in insp.get_indexes("members") if i.get("unique")
    ]
    assert any("name" in (u.get("column_names") or []) for u in uniques)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/tmp/runtests.sh tests/test_phase3_schema.py -v`
Expected: FAIL — `members` not in table names.

- [ ] **Step 3: Write the migration**

`backend/database/alembic/versions/0003_projects_members.py` (mirror 0002's style):

```python
"""projects, members, uploads, scoping columns

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-08

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '0003'
down_revision: Union[str, None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCOPED_TABLES = (
    'generation_requests', 'image_logs', 'video_logs', 'evaluations',
    'runs', 'posts', 'caption_exports',
)


def upgrade() -> None:
    op.create_table(
        'members',
        sa.Column('id', sa.Text(), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True),
                  server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name', name='uq_members_name'),
    )
    op.create_table(
        'projects',
        sa.Column('id', sa.Text(), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('owner_member_id', sa.Text(), nullable=True),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True),
                  server_default=sa.text('now()'), nullable=True),
        sa.Column('archived_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['owner_member_id'], ['members.id'],
                                ondelete='SET NULL'),
    )
    op.create_table(
        'project_members',
        sa.Column('project_id', sa.Text(), nullable=False),
        sa.Column('member_id', sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint('project_id', 'member_id'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['member_id'], ['members.id'], ondelete='CASCADE'),
    )
    op.create_table(
        'uploads',
        sa.Column('id', sa.Text(), nullable=False),
        sa.Column('filename', sa.Text(), nullable=False),
        sa.Column('path', sa.Text(), nullable=False),
        sa.Column('kind', sa.Text(), nullable=False),
        sa.Column('project_id', sa.Text(), nullable=True),
        sa.Column('created_by_member_id', sa.Text(), nullable=True),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True),
                  server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['created_by_member_id'], ['members.id'],
                                ondelete='SET NULL'),
    )
    op.create_index('idx_uploads_project_id', 'uploads', ['project_id'])

    for table in SCOPED_TABLES:
        op.add_column(table, sa.Column('project_id', sa.Text(), nullable=True))
        op.add_column(table, sa.Column('created_by_member_id', sa.Text(), nullable=True))
        op.create_foreign_key(
            f'fk_{table}_project_id', table, 'projects',
            ['project_id'], ['id'], ondelete='SET NULL')
        op.create_foreign_key(
            f'fk_{table}_created_by_member_id', table, 'members',
            ['created_by_member_id'], ['id'], ondelete='SET NULL')
        op.create_index(f'idx_{table}_project_id', table, ['project_id'])


def downgrade() -> None:
    for table in SCOPED_TABLES:
        op.drop_index(f'idx_{table}_project_id', table_name=table)
        op.drop_constraint(f'fk_{table}_created_by_member_id', table, type_='foreignkey')
        op.drop_constraint(f'fk_{table}_project_id', table, type_='foreignkey')
        op.drop_column(table, 'created_by_member_id')
        op.drop_column(table, 'project_id')
    op.drop_table('uploads')
    op.drop_table('project_members')
    op.drop_table('projects')
    op.drop_table('members')
```

- [ ] **Step 4: Update `backend/database/models.py`**

Append after `GenerationRequest` (match the file's existing style — `TIMESTAMP(timezone=True)` + `server_default=func.now()`):

```python
class Member(Base):
    """Lightweight identity (phase 3). No passwords — name is the login."""

    __tablename__ = "members"
    __table_args__ = (UniqueConstraint("name", name="uq_members_name"),)

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )


class Project(Base):
    """Project grouping (phase 3). DB grouping only — no physical folders."""

    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    owner_member_id: Mapped[Optional[str]] = mapped_column(
        Text, ForeignKey("members.id", ondelete="SET NULL")
    )
    created_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
    archived_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True))


class ProjectMember(Base):
    __tablename__ = "project_members"

    project_id: Mapped[str] = mapped_column(
        Text, ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    member_id: Mapped[str] = mapped_column(
        Text, ForeignKey("members.id", ondelete="CASCADE"), primary_key=True
    )


class Upload(Base):
    """Uploaded source/ref images (phase 3). Files already on disk before this
    table existed have no row and simply don't appear in project Assets."""

    __tablename__ = "uploads"
    __table_args__ = (Index("idx_uploads_project_id", "project_id"),)

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)  # "input" | "ref"
    project_id: Mapped[Optional[str]] = mapped_column(
        Text, ForeignKey("projects.id", ondelete="SET NULL")
    )
    created_by_member_id: Mapped[Optional[str]] = mapped_column(
        Text, ForeignKey("members.id", ondelete="SET NULL")
    )
    created_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
```

And add to each of the 7 scoped models (`Evaluation`, `ImageLog`, `VideoLog`, `Run`, `Post`, `CaptionExport`, `GenerationRequest`) these two columns (same two lines in each class body; also add the matching `Index(f"idx_<table>_project_id", "project_id")` to each `__table_args__`, creating the tuple where the class has none — `Evaluation`, `ImageLog`, `VideoLog`, `CaptionExport`):

```python
    project_id: Mapped[Optional[str]] = mapped_column(
        Text, ForeignKey("projects.id", ondelete="SET NULL")
    )
    created_by_member_id: Mapped[Optional[str]] = mapped_column(
        Text, ForeignKey("members.id", ondelete="SET NULL")
    )
```

NOTE: `Member`/`Project` classes must be defined BEFORE the FK strings resolve at mapper-configure time — string table refs are fine in any order, so appending at the end works.

- [ ] **Step 5: Run test to verify it passes**

Run: `/tmp/runtests.sh tests/test_phase3_schema.py -v`
Expected: 4 passed.

- [ ] **Step 6: Sanity — existing per-file suites still pass**

Run: `/tmp/runtests.sh tests/test_api_review.py -v` then `/tmp/runtests.sh tests/test_dispatch_task.py -v`
Expected: all pass (models change is additive).

- [ ] **Step 7: Commit**

```bash
git add backend/database/alembic/versions/0003_projects_members.py backend/database/models.py
git add -f tests/test_phase3_schema.py
git commit -m "feat(db): migration 0003 — members/projects/uploads + scoping columns"
```

---

### Task 2: Members storage + identity dependency + /api/members

**Files:**
- Create: `backend/database/members_storage.py`
- Create: `backend/api/identity.py`
- Create: `backend/api/members.py`
- Modify: `backend/main.py` (register router)
- Test: `tests/test_phase3_identity.py`

**Interfaces:**
- Consumes: `Member` model (Task 1); `session_scope` from `backend.database.engine`; `format_legacy_ts` from `backend.database.db_utils`.
- Produces: `MembersStorage.get_or_create(name: str) -> str` (returns member id), `MembersStorage.list_members() -> list[dict]` (`{id, name, created_at}`); `Identity` dataclass with `member_id: Optional[str]`, `project_id: Optional[str]`; `get_identity` FastAPI dependency. Tasks 3–7 depend on `Identity`/`get_identity` exactly as defined here.

- [ ] **Step 1: Write the failing test**

```python
"""Identity resolution: X-Member-Name auto-create, X-Project-Id validation."""
import pytest

from backend.database.members_storage import MembersStorage


@pytest.fixture
def members(clean_tables):
    return MembersStorage()


def test_get_or_create_is_idempotent(members):
    a = members.get_or_create("Khang")
    b = members.get_or_create("Khang")
    assert a == b
    assert [m["name"] for m in members.list_members()] == ["Khang"]


def test_members_api_list_and_create(client, members):
    r = client.post("/api/members", json={"name": "Emi"})
    assert r.status_code == 200
    assert r.json()["name"] == "Emi"
    r = client.get("/api/members")
    assert r.status_code == 200
    assert [m["name"] for m in r.json()] == ["Emi"]


def test_blank_member_name_rejected(client, clean_tables):
    r = client.post("/api/members", json={"name": "   "})
    assert r.status_code == 422


def test_header_auto_creates_member_once(client, members):
    # Any identity-consuming endpoint works; /api/members POST double-creates
    # nothing, so use it twice with the header on a different name.
    headers = {"X-Member-Name": "HeaderUser"}
    client.get("/api/members", headers=headers)  # GET does not consume identity
    from backend.api.identity import get_identity
    ident1 = get_identity(x_member_name="HeaderUser", x_project_id=None)
    ident2 = get_identity(x_member_name="HeaderUser", x_project_id=None)
    assert ident1.member_id == ident2.member_id
    assert len(members.list_members()) == 1


def test_unknown_project_header_is_ignored(clean_tables):
    from backend.api.identity import get_identity
    ident = get_identity(x_member_name=None, x_project_id="nonexistent")
    assert ident.member_id is None
    assert ident.project_id is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/tmp/runtests.sh tests/test_phase3_identity.py -v`
Expected: FAIL — `ModuleNotFoundError: backend.database.members_storage`.

- [ ] **Step 3: Implement `backend/database/members_storage.py`**

```python
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
```

- [ ] **Step 4: Implement `backend/api/identity.py`**

```python
"""Header-based identity (phase 3). No auth — X-Member-Name is trusted.

Both headers are optional and both failure modes are silent by design:
a missing member stamps nothing (content lands in "Unassigned"), and a
stale/unknown project id from localStorage must never brick the UI.
"""
from dataclasses import dataclass
from typing import Optional

from fastapi import Header


@dataclass
class Identity:
    member_id: Optional[str]
    project_id: Optional[str]


def get_identity(
    x_member_name: Optional[str] = Header(default=None),
    x_project_id: Optional[str] = Header(default=None),
) -> Identity:
    member_id = None
    name = (x_member_name or "").strip()
    if name:
        from backend.database.members_storage import MembersStorage

        member_id = MembersStorage().get_or_create(name)

    project_id = None
    if x_project_id:
        from backend.database.projects_storage import ProjectsStorage

        if ProjectsStorage().exists(x_project_id):
            project_id = x_project_id
    return Identity(member_id=member_id, project_id=project_id)
```

NOTE: `ProjectsStorage` arrives in Task 3. Until then, make the project block tolerant so Task 2's tests pass:

```python
    project_id = None
    if x_project_id:
        try:
            from backend.database.projects_storage import ProjectsStorage

            if ProjectsStorage().exists(x_project_id):
                project_id = x_project_id
        except ImportError:
            project_id = None
```

Keep the `try/except ImportError` removed in Task 3 Step 4 (Task 3 makes the import real).

- [ ] **Step 5: Implement `backend/api/members.py`**

```python
"""Members API (phase 3)."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.database.members_storage import MembersStorage

router = APIRouter()


class MemberCreateRequest(BaseModel):
    name: str


class MemberItem(BaseModel):
    id: str
    name: str
    created_at: str | None = None


@router.get("", response_model=list[MemberItem])
def list_members():
    return MembersStorage().list_members()


@router.post("", response_model=MemberItem)
def create_member(body: MemberCreateRequest):
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Member name must not be blank")
    storage = MembersStorage()
    member_id = storage.get_or_create(name)
    return next(m for m in storage.list_members() if m["id"] == member_id)
```

- [ ] **Step 6: Register in `backend/main.py`**

Add to the `from backend.api import (...)` block: `members as members_module,` and after the review router line:

```python
app.include_router(members_module.router, prefix="/api/members", tags=["members"])
```

- [ ] **Step 7: Run test to verify it passes**

Run: `/tmp/runtests.sh tests/test_phase3_identity.py -v`
Expected: 5 passed.

- [ ] **Step 8: Commit**

```bash
git add backend/database/members_storage.py backend/api/identity.py backend/api/members.py backend/main.py
git add -f tests/test_phase3_identity.py
git commit -m "feat(identity): members storage, X-Member-Name/X-Project-Id dependency, /api/members"
```

---

### Task 3: Projects storage + /api/projects

**Files:**
- Create: `backend/database/projects_storage.py`
- Create: `backend/models/project.py`
- Create: `backend/api/projects.py`
- Modify: `backend/main.py` (register router), `backend/api/identity.py` (drop the ImportError guard)
- Test: `tests/test_phase3_projects.py`

**Interfaces:**
- Consumes: `Project`, `ProjectMember` models (Task 1); `Identity`/`get_identity` (Task 2).
- Produces: `ProjectsStorage` with `create_project(name, description=None, owner_member_id=None) -> dict`, `list_projects(include_archived=False) -> list[dict]`, `get_project(project_id) -> Optional[dict]`, `update_project(project_id, name=None, description=None, archived=None) -> Optional[dict]`, `exists(project_id) -> bool`, `add_member(project_id, member_id) -> None`, `remove_member(project_id, member_id) -> None`, `list_member_ids(project_id) -> list[str]`. Project dict shape: `{id, name, description, owner_member_id, created_at, archived_at, member_ids}`.

- [ ] **Step 1: Write the failing test**

```python
"""Projects CRUD + membership + archived visibility."""
import pytest

from backend.database.members_storage import MembersStorage
from backend.database.projects_storage import ProjectsStorage


@pytest.fixture
def storage(clean_tables):
    return ProjectsStorage()


def test_create_list_get(client, storage):
    r = client.post("/api/projects", json={"name": "Emi Q3", "description": "campaign"},
                    headers={"X-Member-Name": "Khang"})
    assert r.status_code == 200
    proj = r.json()
    assert proj["name"] == "Emi Q3"
    assert proj["owner_member_id"] is not None  # stamped from header

    r = client.get("/api/projects")
    assert [p["id"] for p in r.json()] == [proj["id"]]

    assert storage.exists(proj["id"]) is True
    assert storage.exists("nope") is False


def test_archive_hides_from_default_list(client, storage):
    pid = storage.create_project("temp")["id"]
    r = client.patch(f"/api/projects/{pid}", json={"archived": True})
    assert r.status_code == 200
    assert r.json()["archived_at"] is not None
    assert client.get("/api/projects").json() == []
    listed = client.get("/api/projects", params={"include_archived": "true"}).json()
    assert [p["id"] for p in listed] == [pid]


def test_patch_unknown_project_404(client, clean_tables):
    assert client.patch("/api/projects/nope", json={"name": "x"}).status_code == 404


def test_membership_add_remove(client, storage):
    pid = storage.create_project("p")["id"]
    mid = MembersStorage().get_or_create("Ana")
    r = client.post(f"/api/projects/{pid}/members", json={"member_id": mid})
    assert r.status_code == 200
    assert storage.list_member_ids(pid) == [mid]
    r = client.delete(f"/api/projects/{pid}/members/{mid}")
    assert r.status_code == 200
    assert storage.list_member_ids(pid) == []


def test_identity_resolves_valid_project(storage):
    from backend.api.identity import get_identity
    pid = storage.create_project("live")["id"]
    ident = get_identity(x_member_name=None, x_project_id=pid)
    assert ident.project_id == pid
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/tmp/runtests.sh tests/test_phase3_projects.py -v`
Expected: FAIL — `ModuleNotFoundError: backend.database.projects_storage`.

- [ ] **Step 3: Implement `backend/database/projects_storage.py`**

```python
"""Postgres storage for projects and project membership (phase 3)."""
import uuid
from typing import Optional

from sqlalchemy import delete, func, select, update

from .db_utils import format_legacy_ts as _format_ts
from .engine import session_scope
from .models import Project, ProjectMember


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
```

- [ ] **Step 4: Implement `backend/models/project.py`**

```python
from typing import List, Optional

from pydantic import BaseModel


class ProjectCreateRequest(BaseModel):
    name: str
    description: Optional[str] = None


class ProjectPatchRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    archived: Optional[bool] = None


class ProjectItem(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    owner_member_id: Optional[str] = None
    created_at: Optional[str] = None
    archived_at: Optional[str] = None
    member_ids: List[str] = []


class ProjectMemberRequest(BaseModel):
    member_id: str
```

Then `backend/api/projects.py`:

```python
"""Projects API (phase 3)."""
from fastapi import APIRouter, Depends, HTTPException, Query

from backend.api.identity import Identity, get_identity
from backend.database.projects_storage import ProjectsStorage
from backend.models.project import (
    ProjectCreateRequest,
    ProjectItem,
    ProjectMemberRequest,
    ProjectPatchRequest,
)

router = APIRouter()


@router.get("", response_model=list[ProjectItem])
def list_projects(include_archived: bool = Query(default=False)):
    return ProjectsStorage().list_projects(include_archived=include_archived)


@router.post("", response_model=ProjectItem)
def create_project(
    body: ProjectCreateRequest,
    identity: Identity = Depends(get_identity),
):
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Project name must not be blank")
    return ProjectsStorage().create_project(
        name, description=body.description, owner_member_id=identity.member_id
    )


@router.patch("/{project_id}", response_model=ProjectItem)
def patch_project(project_id: str, body: ProjectPatchRequest):
    row = ProjectsStorage().update_project(
        project_id, name=body.name, description=body.description,
        archived=body.archived,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return row


@router.post("/{project_id}/members", response_model=ProjectItem)
def add_project_member(project_id: str, body: ProjectMemberRequest):
    storage = ProjectsStorage()
    if not storage.exists(project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    storage.add_member(project_id, body.member_id)
    return storage.get_project(project_id)


@router.delete("/{project_id}/members/{member_id}", response_model=ProjectItem)
def remove_project_member(project_id: str, member_id: str):
    storage = ProjectsStorage()
    if not storage.exists(project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    storage.remove_member(project_id, member_id)
    return storage.get_project(project_id)
```

Register in `backend/main.py` (import `projects as projects_module,` in the api import block):

```python
app.include_router(projects_module.router, prefix="/api/projects", tags=["projects"])
```

Finally, in `backend/api/identity.py`, remove the `try/except ImportError` guard added in Task 2 (keep the plain import + `exists()` check).

- [ ] **Step 5: Run tests**

Run: `/tmp/runtests.sh tests/test_phase3_projects.py -v` then `/tmp/runtests.sh tests/test_phase3_identity.py -v`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add backend/database/projects_storage.py backend/models/project.py backend/api/projects.py backend/api/identity.py backend/main.py
git add -f tests/test_phase3_projects.py
git commit -m "feat(projects): projects storage, CRUD/archive/membership API"
```

---

### Task 4: Bulk assign-to-project endpoint

**Files:**
- Modify: `backend/database/projects_storage.py`, `backend/models/project.py`, `backend/api/projects.py`
- Test: append to `tests/test_phase3_projects.py`

**Interfaces:**
- Produces: `ProjectsStorage.assign_rows(project_id: str, table: str, ids: list) -> int`; module constant `ASSIGNABLE_TABLES: dict`; `POST /api/projects/{id}/assign` body `{"table": str, "ids": [str]}` → `{"updated": int}`; unknown table → 422; unknown ids skipped.

- [ ] **Step 1: Write the failing tests (append to `tests/test_phase3_projects.py`)**

```python
def test_assign_rows_moves_bucket(client, storage):
    from backend.database.generation_requests_storage import GenerationRequestsStorage
    pid = storage.create_project("assignee")["id"]
    created = GenerationRequestsStorage().create_requests([{
        "source_image_path": "/x/img.png", "prompt": "p", "provider": "comfy_image",
        "settings": {},
    }])
    rid = created["request_ids"][0]
    r = client.post(f"/api/projects/{pid}/assign",
                    json={"table": "generation_requests", "ids": [rid, "ghost"]})
    assert r.status_code == 200
    assert r.json()["updated"] == 1
    row = GenerationRequestsStorage().get_request(rid)
    assert row["project_id"] == pid


def test_assign_unknown_table_422(client, storage):
    pid = storage.create_project("p422")["id"]
    r = client.post(f"/api/projects/{pid}/assign",
                    json={"table": "runpod_jobs", "ids": ["1"]})
    assert r.status_code == 422


def test_assign_int_pk_table_coerces_ids(client, storage):
    from backend.database.image_logs_storage import ImageLogsStorage
    pid = storage.create_project("intpk")["id"]
    row_id = ImageLogsStorage().log_execution(execution_id="e1", prompt="p")
    r = client.post(f"/api/projects/{pid}/assign",
                    json={"table": "image_logs", "ids": [str(row_id), "not-an-int"]})
    assert r.status_code == 200
    assert r.json()["updated"] == 1
```

NOTE: `get_request` returning `project_id` lands in Task 6; for THIS task assert via a direct select instead:

```python
    from sqlalchemy import select, text
    from backend.database.engine import session_scope
    with session_scope() as session:
        val = session.execute(
            text("SELECT project_id FROM generation_requests WHERE id = :i"), {"i": rid}
        ).scalar()
    assert val == pid
```

Use the `session_scope` variant now; Task 6 may simplify it.

- [ ] **Step 2: Run to verify failure**

Run: `/tmp/runtests.sh tests/test_phase3_projects.py -v -k assign`
Expected: FAIL — 404 on `/assign` route.

- [ ] **Step 3: Implement**

Append to `backend/database/projects_storage.py`:

```python
from .models import (  # noqa: E402  (extend the existing models import instead)
    CaptionExport, Evaluation, GenerationRequest, ImageLog, Post, Run, VideoLog,
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
```

(Merge these names into the single `from .models import ...` at the top of the file rather than a second import.)

Method on `ProjectsStorage`:

```python
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
```

`backend/models/project.py` additions:

```python
class AssignRequest(BaseModel):
    table: str
    ids: List[str]


class AssignResponse(BaseModel):
    updated: int
```

`backend/api/projects.py` endpoint (import `ASSIGNABLE_TABLES`, `AssignRequest`, `AssignResponse`):

```python
@router.post("/{project_id}/assign", response_model=AssignResponse)
def assign_to_project(project_id: str, body: AssignRequest):
    from backend.database.projects_storage import ASSIGNABLE_TABLES

    storage = ProjectsStorage()
    if not storage.exists(project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    if body.table not in ASSIGNABLE_TABLES:
        raise HTTPException(
            status_code=422,
            detail=f"table must be one of: {', '.join(sorted(ASSIGNABLE_TABLES))}",
        )
    return AssignResponse(updated=storage.assign_rows(project_id, body.table, body.ids))
```

- [ ] **Step 4: Run tests, expect pass**

Run: `/tmp/runtests.sh tests/test_phase3_projects.py -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add backend/database/projects_storage.py backend/models/project.py backend/api/projects.py
git add -f tests/test_phase3_projects.py
git commit -m "feat(projects): bulk assign-to-project endpoint for gradual adoption"
```

---

### Task 5: Uploads table — stamping at upload + /api/uploads

**Files:**
- Create: `backend/database/uploads_storage.py`
- Create: `backend/api/uploads.py`
- Modify: `backend/api/workspace.py` (`/upload` ~line 133, `/ref-images/upload` ~line 219), `backend/main.py`
- Test: `tests/test_phase3_uploads.py`

**Interfaces:**
- Consumes: `Upload` model (Task 1); `Identity`/`get_identity` (Task 2); `svc.save_ref_image(filename, data) -> str` (existing — returns saved path).
- Produces: `UploadsStorage.add_upload(filename, path, kind, project_id=None, created_by_member_id=None) -> dict`; `UploadsStorage.list_uploads(project_id=None, page=1, per_page=50) -> dict` (`{items, total, page, pages}`); `UploadsStorage.get_upload(upload_id) -> Optional[dict]`; `GET /api/uploads?project_id=` and `GET /api/uploads/{id}/thumbnail`. Upload dict: `{id, filename, path, kind, project_id, created_by_member_id, created_at}`.

- [ ] **Step 1: Write the failing test**

```python
"""Uploads: rows stamped at upload time; per-project listing; safe thumbnails."""
import io

import pytest
from PIL import Image

from backend.database.projects_storage import ProjectsStorage
from backend.database.uploads_storage import UploadsStorage


@pytest.fixture
def project_id(clean_tables):
    return ProjectsStorage().create_project("uploads-proj")["id"]


def _png_file():
    buf = io.BytesIO()
    Image.new("RGB", (10, 10)).save(buf, format="PNG")
    buf.seek(0)
    return ("files", ("pic.png", buf, "image/png"))


def test_upload_creates_stamped_row(client, project_id):
    r = client.post(
        "/api/workspace/upload",
        files=[_png_file()],
        headers={"X-Member-Name": "Uploader", "X-Project-Id": project_id},
    )
    assert r.status_code == 200
    listing = UploadsStorage().list_uploads(project_id=project_id)
    assert listing["total"] == 1
    row = listing["items"][0]
    assert row["kind"] == "input"
    assert row["project_id"] == project_id
    assert row["created_by_member_id"] is not None


def test_upload_without_headers_lands_unassigned(client, clean_tables):
    r = client.post("/api/workspace/upload", files=[_png_file()])
    assert r.status_code == 200
    listing = UploadsStorage().list_uploads(project_id="unassigned")
    assert listing["total"] == 1
    assert listing["items"][0]["project_id"] is None


def test_ref_upload_kind_ref(client, project_id):
    r = client.post(
        "/api/workspace/ref-images/upload",
        files=[_png_file()],
        headers={"X-Project-Id": project_id},
    )
    assert r.status_code == 200
    listing = UploadsStorage().list_uploads(project_id=project_id)
    assert listing["items"][0]["kind"] == "ref"


def test_uploads_api_list_and_thumbnail(client, project_id):
    client.post("/api/workspace/upload", files=[_png_file()],
                headers={"X-Project-Id": project_id})
    r = client.get("/api/uploads", params={"project_id": project_id})
    assert r.status_code == 200
    upload_id = r.json()["items"][0]["id"]
    r = client.get(f"/api/uploads/{upload_id}/thumbnail")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/jpeg"


def test_thumbnail_refuses_row_with_escaped_path(client, clean_tables):
    row = UploadsStorage().add_upload(
        filename="passwd", path="/etc/passwd", kind="input")
    r = client.get(f"/api/uploads/{row['id']}/thumbnail")
    assert r.status_code == 404
```

- [ ] **Step 2: Run to verify failure**

Run: `/tmp/runtests.sh tests/test_phase3_uploads.py -v`
Expected: FAIL — `ModuleNotFoundError: backend.database.uploads_storage`.

- [ ] **Step 3: Implement `backend/database/uploads_storage.py`**

```python
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
```

- [ ] **Step 4: Implement `backend/api/uploads.py`**

Reuse review.py's containment helpers (import them — do not duplicate):

```python
"""Uploads API (phase 3 Assets tab)."""
import io
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel

from backend.api.review import _source_path_in_roots
from backend.database.uploads_storage import UploadsStorage

logger = logging.getLogger(__name__)
router = APIRouter()

THUMBNAIL_SIZE = (256, 256)


class UploadItem(BaseModel):
    id: str
    filename: str
    path: str
    kind: str
    project_id: Optional[str] = None
    created_by_member_id: Optional[str] = None
    created_at: Optional[str] = None


class UploadListResponse(BaseModel):
    items: list[UploadItem]
    total: int
    page: int
    pages: int


@router.get("", response_model=UploadListResponse)
def list_uploads(
    project_id: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=200),
):
    return UploadsStorage().list_uploads(
        project_id=project_id, page=page, per_page=per_page
    )


@router.get("/{upload_id}/thumbnail")
def upload_thumbnail(upload_id: str):
    from PIL import Image

    row = UploadsStorage().get_upload(upload_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Upload not found")
    source = _source_path_in_roots(row["path"])
    if source is None or not source.is_file():
        raise HTTPException(status_code=404, detail="Upload file not found")
    try:
        with Image.open(source) as img:
            img.thumbnail(THUMBNAIL_SIZE)
            buf = io.BytesIO()
            img.convert("RGB").save(buf, format="JPEG", quality=80)
    except Exception:
        logger.exception("Thumbnail generation failed for upload %s", upload_id)
        raise HTTPException(status_code=500, detail="Thumbnail generation failed")
    return Response(content=buf.getvalue(), media_type="image/jpeg")
```

Register in `backend/main.py` (import `uploads as uploads_module,`):

```python
app.include_router(uploads_module.router, prefix="/api/uploads", tags=["uploads"])
```

- [ ] **Step 5: Stamp at upload time in `backend/api/workspace.py`**

Add imports near the top: `from backend.api.identity import Identity, get_identity` and `from backend.database.uploads_storage import UploadsStorage`.

`upload_images` (the `/upload` route, ~line 133) becomes:

```python
@router.post("/upload")
async def upload_images(
    files: List[UploadFile] = File(...),
    svc: ImageProcessingService = Depends(get_image_processing_service),
    identity: Identity = Depends(get_identity),
):
    """Save uploaded images directly into PROCESSED_DIR (unified library)."""
    saved = []
    uploads = UploadsStorage()
    for f in files:
        data = await f.read()
        try:
            path = svc.save_ref_image(f.filename or "upload", data)
            saved.append(Path(path).name)
            uploads.add_upload(
                filename=Path(path).name, path=str(path), kind="input",
                project_id=identity.project_id,
                created_by_member_id=identity.member_id,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    return {"saved": saved, "count": len(saved)}
```

`upload_ref_images` (~line 219): same pattern — capture `path = svc.save_ref_image(...)` and add `uploads.add_upload(filename=Path(path).name, path=str(path), kind="ref", project_id=identity.project_id, created_by_member_id=identity.member_id)` inside the loop, with `identity: Identity = Depends(get_identity)` added to the signature.

- [ ] **Step 6: Run tests, expect pass**

Run: `/tmp/runtests.sh tests/test_phase3_uploads.py -v` then `/tmp/runtests.sh tests/test_api_workspace.py -v`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add backend/database/uploads_storage.py backend/api/uploads.py backend/api/workspace.py backend/main.py
git add -f tests/test_phase3_uploads.py
git commit -m "feat(uploads): uploads table stamped at upload time + /api/uploads"
```

---

### Task 6: Stamp generation_requests (API ingress + worker threading)

**Files:**
- Modify: `backend/database/generation_requests_storage.py` (`create_requests`, `_row_dict`), `backend/models/review.py` (`ReviewCreateRequest`, `ReviewRequestItem`), `backend/api/review.py` (`create_requests` endpoint), `backend/services/image_processing.py` (`dispatch_processing` ~line 106), `backend/tasks.py` (`process_image_task` ~line 137, `async_process_image` ~line 184)
- Test: append to `tests/test_api_review.py`

**Interfaces:**
- Consumes: `Identity`/`get_identity` (Task 2).
- Produces: `GenerationRequestsStorage.create_requests(items, batch_id=None, project_id=None, created_by_member_id=None)`; row dicts (and `ReviewRequestItem`) gain `project_id: Optional[str]` and `created_by_member_id: Optional[str]`; `dispatch_processing(..., project_id=None, member_id=None)`; `process_image_task`/`async_process_image` gain `project_id=None, created_by_member_id=None` params. Task 7 reads `row["project_id"]` / `row["created_by_member_id"]` off the dispatch row.

- [ ] **Step 1: Write the failing tests (append to `tests/test_api_review.py`)**

```python
def test_create_requests_stamped_from_headers(client, storage):
    from backend.database.projects_storage import ProjectsStorage
    pid = ProjectsStorage().create_project("rev-proj")["id"]
    r = client.post("/api/review/requests", json=_payload(),
                    headers={"X-Member-Name": "Reviewer", "X-Project-Id": pid})
    assert r.status_code == 200
    item = client.get("/api/review/requests").json()["items"][0]
    assert item["project_id"] == pid
    assert item["created_by_member_id"] is not None


def test_create_requests_without_headers_unstamped(client, storage):
    client.post("/api/review/requests", json=_payload())
    item = client.get("/api/review/requests").json()["items"][0]
    assert item["project_id"] is None
    assert item["created_by_member_id"] is None
```

- [ ] **Step 2: Run to verify failure**

Run: `/tmp/runtests.sh tests/test_api_review.py -v -k stamped`
Expected: FAIL — KeyError/None mismatch on `project_id`.

- [ ] **Step 3: Implement**

`backend/database/generation_requests_storage.py` — `create_requests` signature and row:

```python
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
```

`_row_dict` gains two entries (after `"error"`):

```python
        "project_id": row.project_id,
        "created_by_member_id": row.created_by_member_id,
```

`backend/models/review.py` — `ReviewRequestItem` gains (after `error`):

```python
    project_id: Optional[str] = None
    created_by_member_id: Optional[str] = None
```

`backend/api/review.py` — `create_requests` endpoint:

```python
from backend.api.identity import Identity, get_identity

@router.post("/requests", response_model=ReviewCreateResponse)
def create_requests(
    body: ReviewCreateRequest,
    storage: GenerationRequestsStorage = Depends(GenerationRequestsStorage),
    identity: Identity = Depends(get_identity),
):
    for item in body.items:
        if _source_path_in_roots(item.source_image_path) is None:
            raise HTTPException(
                status_code=422,
                detail="source_image_path is outside the allowed image directories",
            )
    return storage.create_requests(
        [item.model_dump() for item in body.items],
        batch_id=body.batch_id,
        project_id=identity.project_id,
        created_by_member_id=identity.member_id,
    )
```

`backend/services/image_processing.py` — `dispatch_processing` gains `project_id: Optional[str] = None, member_id: Optional[str] = None` params (before `prepare`), and the `celery_app.send_task` kwargs dict gains:

```python
                "project_id": project_id,
                "created_by_member_id": member_id,
```

`backend/api/workspace.py` — `/process` endpoint gains `identity: Identity = Depends(get_identity)` and passes `project_id=identity.project_id, member_id=identity.member_id` into `svc.dispatch_processing(...)`.

`backend/tasks.py` — `process_image_task` gains trailing params `project_id=None, created_by_member_id=None` and forwards both into `async_process_image(...)`; `async_process_image` gains the same params and passes them to the queue write:

```python
    created = GenerationRequestsStorage().create_requests(
        [
            {
                "source_image_path": dest_image_path,
                "prompt": prompt_content,
                "provider": "comfy_image",
                "workflow_name": workflow_name,
                "settings": settings,
            }
            for prompt_content in prompts
        ],
        project_id=project_id,
        created_by_member_id=created_by_member_id,
    )
```

- [ ] **Step 4: Run tests, expect pass**

Run: `/tmp/runtests.sh tests/test_api_review.py -v` then `/tmp/runtests.sh tests/test_services_image_processing.py -v` and `/tmp/runtests.sh tests/test_pipelines_api.py -v`
Expected: all pass (existing tests unaffected — new params all default to None).

- [ ] **Step 5: Frontend contract touch-up**

Add to `frontend/src/types/review.ts` on `ReviewRequestItem`:

```ts
  project_id?: string | null
  created_by_member_id?: string | null
```

Verify: `cd frontend && ./node_modules/.bin/tsc -b --force` — exit 0.

- [ ] **Step 6: Commit**

```bash
git add backend/database/generation_requests_storage.py backend/models/review.py backend/api/review.py backend/services/image_processing.py backend/api/workspace.py backend/tasks.py frontend/src/types/review.ts
git add -f tests/test_api_review.py
git commit -m "feat(review): stamp generation_requests with project/member through API and worker"
```

---

### Task 7: Propagate scoping to image/video logs; stamp evaluations + caption_exports

**Files:**
- Modify: `backend/database/image_logs_storage.py` (`log_execution` ~line 37), `backend/database/video_logs_storage.py` (`log_execution`), `backend/services/video.py` (`queue_video` ~line 52, `queue_video_comfy` ~line 87), `backend/tasks.py` (`dispatch_generation_request_task` ~line 477), `backend/database/evaluations_storage.py` (`create_pending` ~line 22), `backend/services/evaluation.py` (`evaluate` ~line 99), `backend/api/evaluations.py` (`create_evaluation`), `backend/database/caption_exports_storage.py` (`insert` ~line 28), `backend/api/workspace.py` (both caption-export insert call sites, ~lines 507 & 553)
- Test: `tests/test_phase3_propagation.py`

**Interfaces:**
- Consumes: Task 6's stamped `generation_requests` row dict (`row["project_id"]`, `row["created_by_member_id"]`).
- Produces: `ImageLogsStorage.log_execution(..., project_id=None, created_by_member_id=None)`; `VideoLogsStorage.log_execution(..., project_id=None, created_by_member_id=None)`; `VideoService.queue_video(...)`/`queue_video_comfy(...)` gain `project_id=None, created_by_member_id=None`; `EvaluationsStorage.create_pending(..., project_id=None, created_by_member_id=None)`; `EvaluationService.evaluate(request, project_id=None, member_id=None)`; `CaptionExportsStorage.insert(..., project_id=None, created_by_member_id=None)`.

- [ ] **Step 1: Write the failing test**

```python
"""Scoping copies from generation_requests to logs; ingress stamps evals/exports."""
from unittest.mock import MagicMock, patch

import pytest

from backend.database.generation_requests_storage import GenerationRequestsStorage
from backend.database.image_logs_storage import ImageLogsStorage
from backend.database.projects_storage import ProjectsStorage
from backend.database.members_storage import MembersStorage


@pytest.fixture
def scoped_request(clean_tables):
    pid = ProjectsStorage().create_project("prop-proj")["id"]
    mid = MembersStorage().get_or_create("Propagator")
    created = GenerationRequestsStorage().create_requests(
        [{
            "source_image_path": "/x/img.png", "prompt": "p",
            "provider": "comfy_image", "settings": {},
        }],
        project_id=pid, created_by_member_id=mid,
    )
    rid = created["request_ids"][0]
    GenerationRequestsStorage().claim_for_dispatch([rid])
    return rid, pid, mid


def test_dispatch_copies_scoping_to_image_log(scoped_request):
    rid, pid, mid = scoped_request
    from backend import tasks as tasks_mod

    fake_client = MagicMock()
    fake_client.generate_image = MagicMock()
    with patch.object(tasks_mod, "get_instances",
                      return_value=(MagicMock(), fake_client, ImageLogsStorage())), \
         patch.object(tasks_mod.asyncio, "run", return_value="exec-prop-1"), \
         patch.object(tasks_mod.download_execution_task, "apply_async"):
        tasks_mod.dispatch_generation_request_task.run(rid)

    logs = ImageLogsStorage()
    record = logs.get_execution("exec-prop-1")
    assert record["project_id"] == pid
    assert record["created_by_member_id"] == mid


def test_evaluation_create_stamped(client, clean_tables, monkeypatch):
    pid = ProjectsStorage().create_project("eval-proj")["id"]
    from backend.services.evaluation import EvaluationService
    monkeypatch.setattr(
        EvaluationService, "evaluate",
        lambda self, request, project_id=None, member_id=None: {
            "id": 1, "status": "pending", "media_type": request.media_type,
            "media_path": request.media_path, "project_id": project_id,
        },
    )
    r = client.post("/api/evaluations",
                    json={"media_type": "image", "media_path": "/x/a.png"},
                    headers={"X-Project-Id": pid})
    assert r.status_code == 200
```

NOTE for the implementer: `ImageLogsStorage` may not have a `get_execution(execution_id)` accessor returning the new columns — check the file; if the existing getter (e.g. `get_execution_by_result_path` / pending-executions readers) doesn't expose them, read via SQL in the test instead:

```python
    from sqlalchemy import text
    from backend.database.engine import session_scope
    with session_scope() as session:
        rec = session.execute(text(
            "SELECT project_id, created_by_member_id FROM image_logs WHERE execution_id = :e"
        ), {"e": "exec-prop-1"}).one()
    assert rec.project_id == pid and rec.created_by_member_id == mid
```

The monkeypatched-`evaluate` test asserts only that the API layer passes identity through; verify the storage stamping directly with an extra test:

```python
def test_evaluations_storage_create_pending_stamps(clean_tables):
    from backend.database.evaluations_storage import EvaluationsStorage
    pid = ProjectsStorage().create_project("es-proj")["id"]
    eid = EvaluationsStorage().create_pending(
        media_type="image", media_path="/x/a.png", prompt=None,
        model="m", rubric_version="v1", project_id=pid,
    )
    rows = EvaluationsStorage().list_evaluations(limit=5)
    assert any(r["id"] == eid for r in rows)
```

- [ ] **Step 2: Run to verify failure**

Run: `/tmp/runtests.sh tests/test_phase3_propagation.py -v`
Expected: FAIL — `log_execution() got an unexpected keyword argument 'project_id'` (or SQL columns NULL).

- [ ] **Step 3: Implement**

`backend/database/image_logs_storage.py` — `log_execution` gains `project_id: str = None, created_by_member_id: str = None` params; pass both into the `ImageLog(...)` constructor.

`backend/database/video_logs_storage.py` — same two params on its `log_execution`, passed into `VideoLog(...)`.

`backend/services/video.py` — `queue_video` and `queue_video_comfy` gain `project_id: Optional[str] = None, created_by_member_id: Optional[str] = None` params; forward both into their internal `video_logs` `log_execution` calls.

`backend/tasks.py` `dispatch_generation_request_task` — thread the row's scoping:

```python
            image_storage.log_execution(
                execution_id=execution_id,
                prompt=row["prompt"],
                image_ref_path=row["source_image_path"],
                persona=settings.get("persona"),
                project_id=row.get("project_id"),
                created_by_member_id=row.get("created_by_member_id"),
            )
```

and for both video providers add `project_id=row.get("project_id"), created_by_member_id=row.get("created_by_member_id")` to the `queue_video(...)` / `queue_video_comfy(...)` calls.

`backend/database/evaluations_storage.py` — `create_pending` gains the two optional params, passed into `Evaluation(...)`.

`backend/services/evaluation.py` — `evaluate(self, request, project_id=None, member_id=None)`; forward into `self.storage.create_pending(..., project_id=project_id, created_by_member_id=member_id)`.

`backend/api/evaluations.py`:

```python
from backend.api.identity import Identity, get_identity

@router.post("", response_model=EvaluationResult)
def create_evaluation(
    body: EvaluationRequest,
    svc: EvaluationService = Depends(get_evaluation_service),
    identity: Identity = Depends(get_identity),
):
    return svc.evaluate(body, project_id=identity.project_id, member_id=identity.member_id)
```

`backend/database/caption_exports_storage.py` — `insert` gains the two optional params into `CaptionExport(...)`. Both `workspace.py` caption-export endpoints gain `identity: Identity = Depends(get_identity)` and pass `project_id=identity.project_id, created_by_member_id=identity.member_id` into `db.insert(...)`.

- [ ] **Step 4: Run tests, expect pass**

Run: `/tmp/runtests.sh tests/test_phase3_propagation.py -v`, then regression: `/tmp/runtests.sh tests/test_dispatch_task.py -v`, `/tmp/runtests.sh tests/test_evaluations.py -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add backend/database/image_logs_storage.py backend/database/video_logs_storage.py backend/services/video.py backend/tasks.py backend/database/evaluations_storage.py backend/services/evaluation.py backend/api/evaluations.py backend/database/caption_exports_storage.py backend/api/workspace.py
git add -f tests/test_phase3_propagation.py
git commit -m "feat(scoping): propagate project/member to logs; stamp evaluations and caption exports"
```

---

### Task 8: `project_id` filters on list endpoints (review, gallery, analysis, evaluations)

**Files:**
- Modify: `backend/database/generation_requests_storage.py` (`list_requests`), `backend/api/review.py` (`list_requests`), `backend/database/image_logs_storage.py` (new helpers), `backend/services/gallery.py` (`list_images`), `backend/api/gallery.py` (`list_images`), `backend/services/analysis.py` (`get_analysis`), `backend/api/analysis.py`, `backend/database/evaluations_storage.py` (`list_evaluations`), `backend/api/evaluations.py` (`list_evaluations`)
- Test: `tests/test_phase3_scoping_filters.py`

**Interfaces:**
- Produces: every listed endpoint accepts optional `project_id` query param — a project id or the literal `"unassigned"`; `ImageLogsStorage.get_project_result_basenames(project_id: str) -> set` and `ImageLogsStorage.get_assigned_result_basenames() -> set`.

- [ ] **Step 1: Write the failing test**

```python
"""Project A never sees project B rows; 'unassigned' sees only NULL rows."""
import pytest

from tests.conftest import make_png
from backend.database.generation_requests_storage import GenerationRequestsStorage
from backend.database.image_logs_storage import ImageLogsStorage
from backend.database.projects_storage import ProjectsStorage


@pytest.fixture
def two_projects(clean_tables):
    ps = ProjectsStorage()
    return ps.create_project("A")["id"], ps.create_project("B")["id"]


def _mk_request(project_id=None, prompt="p"):
    return GenerationRequestsStorage().create_requests(
        [{"source_image_path": "/x/i.png", "prompt": prompt,
          "provider": "comfy_image", "settings": {}}],
        project_id=project_id,
    )["request_ids"][0]


def test_review_list_scoped(client, two_projects):
    pa, pb = two_projects
    _mk_request(pa, "in-a"); _mk_request(pb, "in-b"); _mk_request(None, "loose")

    items = client.get("/api/review/requests", params={"project_id": pa}).json()["items"]
    assert [i["prompt"] for i in items] == ["in-a"]

    items = client.get("/api/review/requests",
                       params={"project_id": "unassigned"}).json()["items"]
    assert [i["prompt"] for i in items] == ["loose"]

    assert client.get("/api/review/requests").json()["total"] == 3


def test_gallery_list_scoped(client, two_projects, _temp_dirs):
    pa, pb = two_projects
    logs = ImageLogsStorage()
    out = _temp_dirs["OUTPUT_DIR"]
    make_png(out, "a_img.png"); make_png(out, "b_img.png"); make_png(out, "loose.png")
    logs.log_execution(execution_id="ea", prompt="p",
                       project_id=pa, created_by_member_id=None)
    logs.update_result_path(execution_id="ea", result_image_path=f"{out}/a_img.png")
    logs.log_execution(execution_id="eb", prompt="p",
                       project_id=pb, created_by_member_id=None)
    logs.update_result_path(execution_id="eb", result_image_path=f"{out}/b_img.png")

    names = [i["filename"] for i in client.get(
        "/api/gallery/images", params={"status": "pending", "project_id": pa}
    ).json()["items"]]
    assert names == ["a_img.png"]

    names = [i["filename"] for i in client.get(
        "/api/gallery/images", params={"status": "pending", "project_id": "unassigned"}
    ).json()["items"]]
    assert names == ["loose.png"]  # file with no assigned DB row


def test_analysis_scoped(client, two_projects, _temp_dirs):
    pa, _ = two_projects
    out = _temp_dirs["OUTPUT_DIR"]
    make_png(out, "an_a.png")
    logs = ImageLogsStorage()
    logs.log_execution(execution_id="eaa", prompt="p", project_id=pa)
    logs.update_result_path(execution_id="eaa", result_image_path=f"{out}/an_a.png")
    data = client.get("/api/analysis", params={"project_id": pa}).json()
    assert [i["filename"] for i in data["items"]] == ["an_a.png"]


def test_evaluations_list_scoped(client, two_projects):
    pa, pb = two_projects
    from backend.database.evaluations_storage import EvaluationsStorage
    es = EvaluationsStorage()
    es.create_pending(media_type="image", media_path="/a.png", prompt=None,
                      model="m", rubric_version="v", project_id=pa)
    es.create_pending(media_type="image", media_path="/b.png", prompt=None,
                      model="m", rubric_version="v", project_id=pb)
    es.create_pending(media_type="image", media_path="/c.png", prompt=None,
                      model="m", rubric_version="v")
    items = client.get("/api/evaluations", params={"project_id": pa}).json()["items"]
    assert [i["media_path"] for i in items] == ["/a.png"]
    items = client.get("/api/evaluations",
                       params={"project_id": "unassigned"}).json()["items"]
    assert [i["media_path"] for i in items] == ["/c.png"]
```

NOTE: check `update_result_path`'s actual signature in `backend/database/image_logs_storage.py` before writing the test (it exists — used by tasks.py and gallery.py — but verify parameter names) and adjust the calls to match. The gallery/analysis tests may leave stray files in OUTPUT_DIR for later tests in the same file — use distinct filenames per test (as above) so listings assert on exact sets that include only that test's files, or clean OUTPUT_DIR at test start:

```python
import os
for f in os.listdir(out):
    p = os.path.join(out, f)
    if os.path.isfile(p):
        os.remove(p)
```

Put that cleanup at the top of each filesystem-dependent test.

- [ ] **Step 2: Run to verify failure**

Run: `/tmp/runtests.sh tests/test_phase3_scoping_filters.py -v`
Expected: FAIL — filters not applied (all rows returned).

- [ ] **Step 3: Implement backend filters**

`generation_requests_storage.list_requests` — add param + where clause:

```python
    def list_requests(
        self,
        status: Optional[str] = None,
        batch_id: Optional[str] = None,
        project_id: Optional[str] = None,
        page: int = 1,
        per_page: int = 50,
    ) -> dict:
        with session_scope() as session:
            query = select(GenerationRequest)
            if status:
                query = query.where(GenerationRequest.status == status)
            if batch_id:
                query = query.where(GenerationRequest.batch_id == batch_id)
            if project_id == "unassigned":
                query = query.where(GenerationRequest.project_id.is_(None))
            elif project_id:
                query = query.where(GenerationRequest.project_id == project_id)
            ...  # rest unchanged
```

`backend/api/review.py` `list_requests` — add `project_id: str | None = Query(default=None),` and forward it.

`backend/database/image_logs_storage.py` — two helpers (result paths can be comma-joined lists of variation paths):

```python
import os
from sqlalchemy import select
from .models import ImageLog

    def _basenames(self, values) -> set:
        names = set()
        for value in values:
            for part in (value or "").split(","):
                part = part.strip()
                if part:
                    names.add(os.path.basename(part))
        return names

    def get_project_result_basenames(self, project_id: str) -> set:
        """Basenames of result images logged under ``project_id``."""
        with session_scope() as session:
            values = session.execute(
                select(ImageLog.result_image_path).where(
                    ImageLog.result_image_path.isnot(None),
                    ImageLog.project_id == project_id,
                )
            ).scalars().all()
            return self._basenames(values)

    def get_assigned_result_basenames(self) -> set:
        """Basenames of result images that belong to ANY project."""
        with session_scope() as session:
            values = session.execute(
                select(ImageLog.result_image_path).where(
                    ImageLog.result_image_path.isnot(None),
                    ImageLog.project_id.isnot(None),
                )
            ).scalars().all()
            return self._basenames(values)
```

`backend/services/gallery.py` `list_images` — filter the scan before pagination:

```python
    def list_images(
        self,
        status: str = "pending",
        page: int = 1,
        per_page: int = 20,
        project_id: Optional[str] = None,
    ) -> dict:
        directory = self._dir_for_status(status)
        all_files = self._scan_dir(directory)
        if project_id == "unassigned":
            assigned = self.storage.get_assigned_result_basenames()
            all_files = [(f, m) for f, m in all_files if f not in assigned]
        elif project_id:
            allowed = self.storage.get_project_result_basenames(project_id)
            all_files = [(f, m) for f, m in all_files if f in allowed]
        total = len(all_files)
        ...  # rest unchanged
```

`backend/api/gallery.py` `list_images` — add `project_id: Optional[str] = Query(None),` and forward.

`backend/services/analysis.py` `get_analysis` — add `project_id: Optional[str] = None` param; right after the status filter on `all_rows`:

```python
        if project_id == "unassigned":
            assigned = self.gallery.storage.get_assigned_result_basenames()
            all_rows = [r for r in all_rows if r[0] not in assigned]
        elif project_id:
            allowed = self.gallery.storage.get_project_result_basenames(project_id)
            all_rows = [r for r in all_rows if r[0] in allowed]
```

`backend/api/analysis.py` — add `project_id: str | None = Query(None),` and forward.

`backend/database/evaluations_storage.py` `list_evaluations` — add `project_id: Optional[str] = None`:

```python
            if project_id == "unassigned":
                stmt = stmt.where(Evaluation.project_id.is_(None))
            elif project_id is not None:
                stmt = stmt.where(Evaluation.project_id == project_id)
```

`backend/api/evaluations.py` `list_evaluations` — add `project_id: str | None = Query(None),` and forward.

- [ ] **Step 4: Run tests, expect pass**

Run: `/tmp/runtests.sh tests/test_phase3_scoping_filters.py -v`, plus regressions: `/tmp/runtests.sh tests/test_api_gallery.py -v`, `/tmp/runtests.sh tests/test_api_analysis.py -v`, `/tmp/runtests.sh tests/test_services_analysis.py -v`, `/tmp/runtests.sh tests/test_api_review.py -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add backend/database/generation_requests_storage.py backend/api/review.py backend/database/image_logs_storage.py backend/services/gallery.py backend/api/gallery.py backend/services/analysis.py backend/api/analysis.py backend/database/evaluations_storage.py backend/api/evaluations.py
git add -f tests/test_phase3_scoping_filters.py
git commit -m "feat(scoping): project_id filters on review/gallery/analysis/evaluations lists"
```

---

### Task 9: Frontend identity plumbing (localStorage, headers, picker, selector)

**Files:**
- Create: `frontend/src/lib/identity.ts`, `frontend/src/types/project.ts`, `frontend/src/api/members.ts`, `frontend/src/api/projects.ts`, `frontend/src/api/uploads.ts`, `frontend/src/components/shared/MemberPickerModal.tsx`, `frontend/src/components/shared/ProjectSelector.tsx`
- Modify: `frontend/src/lib/api-client.ts`, `frontend/src/components/shared/Layout.tsx`

**Interfaces:**
- Consumes: `/api/members`, `/api/projects`, `/api/uploads` (Tasks 2/3/5).
- Produces: `identity.ts` exports `getMemberName(): string | null`, `setMemberName(name: string): void`, `getProjectId(): string | null`, `setProjectId(id: string | null): void`, `subscribeIdentity(fn: () => void): () => void`; `membersApi`, `projectsApi`, `uploadsApi` modules; `MemberPickerModal` (no props), `ProjectSelector` (no props). Task 10 uses all of these.

- [ ] **Step 1: `frontend/src/lib/identity.ts`**

```ts
// localStorage-backed identity. Sent as headers on every API call (see
// api-client.ts); components re-render via the subscribe mechanism.
const MEMBER_KEY = 'ff.memberName'
const PROJECT_KEY = 'ff.projectId'

const listeners = new Set<() => void>()

function notify() {
  listeners.forEach(fn => fn())
}

export function getMemberName(): string | null {
  return localStorage.getItem(MEMBER_KEY)
}

export function setMemberName(name: string): void {
  localStorage.setItem(MEMBER_KEY, name.trim())
  notify()
}

export function getProjectId(): string | null {
  return localStorage.getItem(PROJECT_KEY)
}

export function setProjectId(id: string | null): void {
  if (id) localStorage.setItem(PROJECT_KEY, id)
  else localStorage.removeItem(PROJECT_KEY)
  notify()
}

export function subscribeIdentity(fn: () => void): () => void {
  listeners.add(fn)
  return () => listeners.delete(fn)
}
```

- [ ] **Step 2: Header injection in `frontend/src/lib/api-client.ts`**

Add after the axios instance creation (import from `./identity`):

```ts
import { getMemberName, getProjectId } from './identity'

apiClient.interceptors.request.use(config => {
  const member = getMemberName()
  const project = getProjectId()
  if (member) config.headers['X-Member-Name'] = member
  if (project) config.headers['X-Project-Id'] = project
  return config
})
```

- [ ] **Step 3: Types + API modules**

`frontend/src/types/project.ts`:

```ts
export interface Member {
  id: string
  name: string
  created_at?: string | null
}

export interface Project {
  id: string
  name: string
  description?: string | null
  owner_member_id?: string | null
  created_at?: string | null
  archived_at?: string | null
  member_ids: string[]
}

export interface UploadItem {
  id: string
  filename: string
  path: string
  kind: 'input' | 'ref'
  project_id?: string | null
  created_by_member_id?: string | null
  created_at?: string | null
}

export interface UploadListResponse {
  items: UploadItem[]
  total: number
  page: number
  pages: number
}
```

`frontend/src/api/members.ts`:

```ts
import { apiClient } from '@/lib/api-client'
import type { Member } from '@/types/project'

export const membersApi = {
  list: () => apiClient.get<Member[]>('/members').then(r => r.data),
  create: (name: string) =>
    apiClient.post<Member>('/members', { name }).then(r => r.data),
}
```

`frontend/src/api/projects.ts`:

```ts
import { apiClient } from '@/lib/api-client'
import type { Project } from '@/types/project'

export const projectsApi = {
  list: (includeArchived = false) =>
    apiClient
      .get<Project[]>('/projects', { params: { include_archived: includeArchived } })
      .then(r => r.data),
  create: (name: string, description?: string) =>
    apiClient.post<Project>('/projects', { name, description }).then(r => r.data),
  patch: (id: string, body: { name?: string; description?: string; archived?: boolean }) =>
    apiClient.patch<Project>(`/projects/${id}`, body).then(r => r.data),
  assign: (id: string, table: string, ids: string[]) =>
    apiClient
      .post<{ updated: number }>(`/projects/${id}/assign`, { table, ids })
      .then(r => r.data),
}
```

`frontend/src/api/uploads.ts`:

```ts
import { apiClient } from '@/lib/api-client'
import type { UploadListResponse } from '@/types/project'

export const uploadsApi = {
  list: (params: { project_id?: string; page?: number; per_page?: number }) =>
    apiClient.get<UploadListResponse>('/uploads', { params }).then(r => r.data),
  getThumbnailUrl: (id: string) => `/api/uploads/${id}/thumbnail`,
}
```

- [ ] **Step 4: `MemberPickerModal` + `ProjectSelector`**

`frontend/src/components/shared/MemberPickerModal.tsx` — blocking overlay shown when no member is stored. Uses existing shadcn primitives (`Button`, `Input`); check `frontend/src/components/ui/` for available components and match import style:

```tsx
import React, { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { membersApi } from '@/api/members'
import { getMemberName, setMemberName } from '@/lib/identity'

export const MemberPickerModal: React.FC = () => {
  const [current, setCurrent] = useState(getMemberName())
  const [draft, setDraft] = useState('')
  const { data: members = [] } = useQuery({
    queryKey: ['members'],
    queryFn: membersApi.list,
    enabled: current === null,
  })

  if (current) return null

  const choose = async (name: string) => {
    const clean = name.trim()
    if (!clean) return
    await membersApi.create(clean)
    setMemberName(clean)
    setCurrent(clean)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 backdrop-blur-sm">
      <div className="w-full max-w-sm rounded-lg border bg-card p-6 space-y-4">
        <div>
          <h2 className="text-lg font-semibold">Who's working?</h2>
          <p className="text-sm text-muted-foreground">
            Pick your name — everything you create is tagged with it.
          </p>
        </div>
        {members.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {members.map(m => (
              <Button key={m.id} variant="outline" size="sm" onClick={() => choose(m.name)}>
                {m.name}
              </Button>
            ))}
          </div>
        )}
        <form
          className="flex gap-2"
          onSubmit={e => { e.preventDefault(); void choose(draft) }}
        >
          <Input
            value={draft}
            onChange={e => setDraft(e.target.value)}
            placeholder="Or type a new name"
            autoFocus
          />
          <Button type="submit" disabled={!draft.trim()}>Join</Button>
        </form>
      </div>
    </div>
  )
}
```

`frontend/src/components/shared/ProjectSelector.tsx` — dropdown in the sidebar. Use the existing shadcn `Select` (same import pattern as `WorkflowParametersPanel.tsx`):

```tsx
import React, { useSyncExternalStore } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { projectsApi } from '@/api/projects'
import { getProjectId, setProjectId, subscribeIdentity } from '@/lib/identity'

const NONE = '__none__'

export const ProjectSelector: React.FC = () => {
  const projectId = useSyncExternalStore(subscribeIdentity, getProjectId)
  const { data: projects = [] } = useQuery({
    queryKey: ['projects'],
    queryFn: () => projectsApi.list(),
  })

  return (
    <Select
      value={projectId ?? NONE}
      onValueChange={v => setProjectId(v === NONE ? null : v)}
    >
      <SelectTrigger className="w-full text-xs">
        <SelectValue placeholder="No project" />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={NONE}>No project</SelectItem>
        {projects.map(p => (
          <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}
```

- [ ] **Step 5: Mount both in `frontend/src/components/shared/Layout.tsx`**

Import `MemberPickerModal` and `ProjectSelector`. Inside the returned JSX: render `<MemberPickerModal />` as the first child of the root `div`, and add the selector under the logo block in the sidebar (`<aside>`, after the `p-4 border-b` div):

```tsx
        <div className="hidden lg:block p-2 border-b">
          <ProjectSelector />
        </div>
```

- [ ] **Step 6: Verify + commit**

Run: `cd frontend && ./node_modules/.bin/tsc -b --force`
Expected: exit 0, no output. If `@/components/ui/input` does not exist, check `frontend/src/components/ui/` for the equivalent (e.g. use a plain `<input className="...">` styled like the codebase's inputs).

```bash
git add frontend/src/lib/identity.ts frontend/src/lib/api-client.ts frontend/src/types/project.ts frontend/src/api/members.ts frontend/src/api/projects.ts frontend/src/api/uploads.ts frontend/src/components/shared/MemberPickerModal.tsx frontend/src/components/shared/ProjectSelector.tsx frontend/src/components/shared/Layout.tsx
git commit -m "feat(frontend): member picker, project selector, identity headers on every call"
```

---

### Task 10: Projects pages — list + per-project tabbed workspace

**Files:**
- Create: `frontend/src/pages/ProjectsPage.tsx`, `frontend/src/pages/ProjectWorkspacePage.tsx`, `frontend/src/components/workspace/AssetsPanel.tsx`
- Modify: `frontend/src/App.tsx` (routes), `frontend/src/components/shared/Layout.tsx` (nav item), `frontend/src/pages/ReviewQueuePage.tsx`, `frontend/src/pages/GalleryPage.tsx`, `frontend/src/pages/AnalysisPage.tsx` (accept optional `projectId` prop), `frontend/src/api/review.ts`, `frontend/src/api/gallery.ts`, `frontend/src/api/analysis.ts` (accept `project_id` param)

**Interfaces:**
- Consumes: Task 9's api modules and identity lib; Task 8's `project_id` query params.
- Produces: routes `/projects` and `/projects/:projectId`; page components accept `projectId?: string`.

- [ ] **Step 1: Thread `project_id` through the api modules**

`frontend/src/api/review.ts` — the `listRequests` params type gains `project_id?: string` (axios passes it through automatically since the whole params object is forwarded; just extend the type).

`frontend/src/api/gallery.ts` — the list function's params gain `project_id?: string`.

`frontend/src/api/analysis.ts` — the `list` params gain `project_id?: string`.

- [ ] **Step 2: Give the three pages an optional `projectId` prop**

Pattern (apply to all three):

```tsx
export const ReviewQueuePage: React.FC<{ projectId?: string }> = ({ projectId }) => {
```

and add the param to the page's list query — for ReviewQueuePage:

```tsx
  const { data, isLoading } = useQuery({
    queryKey: ['review-requests', statusFilter, projectId ?? 'all'],
    queryFn: () =>
      reviewApi.listRequests({
        status: statusFilter === 'all' ? undefined : statusFilter,
        per_page: 200,
        project_id: projectId,
      }),
    refetchInterval: 5000,
  })
```

GalleryPage and AnalysisPage: same — add `projectId` to each list queryKey and pass `project_id: projectId` in the api call params. Existing routes render the components without the prop, so the global pages are unchanged ("All projects" view).

- [ ] **Step 3: `frontend/src/components/workspace/AssetsPanel.tsx`**

```tsx
import React from 'react'
import { useQuery } from '@tanstack/react-query'
import { Loader2 } from 'lucide-react'
import { uploadsApi } from '@/api/uploads'

export const AssetsPanel: React.FC<{ projectId: string }> = ({ projectId }) => {
  const { data, isLoading } = useQuery({
    queryKey: ['uploads', projectId],
    queryFn: () => uploadsApi.list({ project_id: projectId, per_page: 200 }),
  })

  if (isLoading) {
    return (
      <div className="flex justify-center py-12">
        <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
      </div>
    )
  }
  const items = data?.items ?? []
  if (items.length === 0) {
    return (
      <p className="text-sm text-muted-foreground text-center py-12">
        No uploads in this project yet. Files uploaded from the Workspace while
        this project is active will appear here.
      </p>
    )
  }
  return (
    <div className="grid grid-cols-[repeat(auto-fill,minmax(140px,1fr))] gap-3 p-4">
      {items.map(u => (
        <figure key={u.id} className="space-y-1">
          <img
            src={uploadsApi.getThumbnailUrl(u.id)}
            alt={u.filename}
            className="aspect-square w-full rounded object-cover bg-muted"
            onError={e => { (e.target as HTMLImageElement).style.visibility = 'hidden' }}
          />
          <figcaption className="truncate text-[11px] text-muted-foreground">
            <span className="mr-1 rounded bg-muted px-1 font-mono text-[10px]">{u.kind}</span>
            {u.filename}
          </figcaption>
        </figure>
      ))}
    </div>
  )
}
```

- [ ] **Step 4: `frontend/src/pages/ProjectsPage.tsx`**

```tsx
import React, { useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Archive, FolderOpen, Loader2, Plus } from 'lucide-react'
import { projectsApi } from '@/api/projects'
import { getProjectId, setProjectId } from '@/lib/identity'

export const ProjectsPage: React.FC = () => {
  const queryClient = useQueryClient()
  const [name, setName] = useState('')
  const { data: projects = [], isLoading } = useQuery({
    queryKey: ['projects'],
    queryFn: () => projectsApi.list(),
  })

  const invalidate = () => void queryClient.invalidateQueries({ queryKey: ['projects'] })
  const createMutation = useMutation({
    mutationFn: (n: string) => projectsApi.create(n),
    onSuccess: () => { setName(''); invalidate() },
  })
  const archiveMutation = useMutation({
    mutationFn: (id: string) => projectsApi.patch(id, { archived: true }),
    onSuccess: (_data, id) => {
      if (getProjectId() === id) setProjectId(null)
      invalidate()
    },
  })

  return (
    <div className="flex flex-col h-full">
      <div className="p-4 border-b flex items-center justify-between gap-4">
        <h1 className="text-xl font-bold">Projects</h1>
        <form
          className="flex gap-2"
          onSubmit={e => { e.preventDefault(); if (name.trim()) createMutation.mutate(name.trim()) }}
        >
          <Input
            value={name}
            onChange={e => setName(e.target.value)}
            placeholder="New project name"
            className="w-56"
          />
          <Button type="submit" disabled={!name.trim() || createMutation.isPending}>
            <Plus className="w-4 h-4 mr-2" />Create
          </Button>
        </form>
      </div>
      <div className="flex-1 overflow-auto p-4">
        {isLoading ? (
          <div className="flex justify-center py-12">
            <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
          </div>
        ) : projects.length === 0 ? (
          <p className="text-sm text-muted-foreground text-center py-12">
            No projects yet. Create one to start grouping your work.
          </p>
        ) : (
          <div className="space-y-2">
            {projects.map(p => (
              <div key={p.id} className="flex items-center gap-3 rounded-md border p-3">
                <FolderOpen className="w-5 h-5 text-muted-foreground shrink-0" />
                <div className="flex-1 min-w-0">
                  <Link to={`/projects/${p.id}`} className="font-medium hover:underline">
                    {p.name}
                  </Link>
                  {p.description && (
                    <p className="text-sm text-muted-foreground truncate">{p.description}</p>
                  )}
                </div>
                <span className="text-xs text-muted-foreground">
                  {p.member_ids.length} member{p.member_ids.length !== 1 ? 's' : ''}
                </span>
                <Button
                  variant="ghost" size="icon" title="Archive"
                  onClick={() => archiveMutation.mutate(p.id)}
                >
                  <Archive className="w-4 h-4" />
                </Button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
```

- [ ] **Step 5: `frontend/src/pages/ProjectWorkspacePage.tsx`**

```tsx
import React, { useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { ArrowLeft } from 'lucide-react'
import { projectsApi } from '@/api/projects'
import { GalleryPage } from '@/pages/GalleryPage'
import { ReviewQueuePage } from '@/pages/ReviewQueuePage'
import { AnalysisPage } from '@/pages/AnalysisPage'
import { AssetsPanel } from '@/components/workspace/AssetsPanel'

type Tab = 'gallery' | 'review' | 'analysis' | 'assets'

export const ProjectWorkspacePage: React.FC = () => {
  const { projectId = '' } = useParams()
  const [tab, setTab] = useState<Tab>('gallery')
  const { data: projects = [] } = useQuery({
    queryKey: ['projects', 'all'],
    queryFn: () => projectsApi.list(true),
  })
  const project = projects.find(p => p.id === projectId)

  return (
    <div className="flex flex-col h-full">
      <div className="p-4 border-b flex items-center gap-4">
        <Link to="/projects" className="text-muted-foreground hover:text-foreground">
          <ArrowLeft className="w-4 h-4" />
        </Link>
        <h1 className="text-xl font-bold truncate">{project?.name ?? 'Project'}</h1>
        <Tabs value={tab} onValueChange={v => setTab(v as Tab)} className="ml-auto">
          <TabsList>
            <TabsTrigger value="gallery">Gallery</TabsTrigger>
            <TabsTrigger value="review">Review</TabsTrigger>
            <TabsTrigger value="analysis">Analysis</TabsTrigger>
            <TabsTrigger value="assets">Assets</TabsTrigger>
          </TabsList>
        </Tabs>
      </div>
      <div className="flex-1 min-h-0 overflow-auto">
        {tab === 'gallery' && <GalleryPage projectId={projectId} />}
        {tab === 'review' && <ReviewQueuePage projectId={projectId} />}
        {tab === 'analysis' && <AnalysisPage projectId={projectId} />}
        {tab === 'assets' && <AssetsPanel projectId={projectId} />}
      </div>
    </div>
  )
}
```

- [ ] **Step 6: Project-name chip on the global Review page**

Spec: global pages gain a project-name column *where rows are DB-backed*. Review rows are the DB-backed list (gallery/analysis items are filesystem scans and don't carry `project_id`), so only `ReviewQueuePage` gets it. When rendered WITHOUT a `projectId` prop, show each row's project name as a badge. In `ReviewQueuePage`:

```tsx
import { projectsApi } from '@/api/projects'

// inside the component (top level, next to the list query):
const { data: allProjects = [] } = useQuery({
  queryKey: ['projects', 'all'],
  queryFn: () => projectsApi.list(true),
  enabled: !projectId,
})
const projectNames = new Map(allProjects.map(p => [p.id, p.name]))
```

Thread `projectName` into `RequestRow` (add `projectName?: string` to its props; pass `projectName={item.project_id ? projectNames.get(item.project_id) : undefined}` only when `!projectId`) and render it in the row's badge cluster after the provider badge:

```tsx
        {projectName && (
          <Badge variant="outline" className="text-xs">{projectName}</Badge>
        )}
```

- [ ] **Step 7: Routes + nav**

`frontend/src/App.tsx` — import both pages; inside the `<Route path="/" element={<Layout />}>` block add:

```tsx
            <Route path="projects" element={<ProjectsPage />} />
            <Route path="projects/:projectId" element={<ProjectWorkspacePage />} />
```

`frontend/src/components/shared/Layout.tsx` — add to `navItems` (after Review; `FolderOpen` from lucide-react):

```tsx
  { to: '/projects', label: 'Projects', icon: FolderOpen },
```

- [ ] **Step 8: Verify + commit**

Run: `cd frontend && ./node_modules/.bin/tsc -b --force`
Expected: exit 0. Fix any prop-type or unused-import diagnostics before committing.

```bash
git add frontend/src/pages/ProjectsPage.tsx frontend/src/pages/ProjectWorkspacePage.tsx frontend/src/components/workspace/AssetsPanel.tsx frontend/src/App.tsx frontend/src/components/shared/Layout.tsx frontend/src/pages/ReviewQueuePage.tsx frontend/src/pages/GalleryPage.tsx frontend/src/pages/AnalysisPage.tsx frontend/src/api/review.ts frontend/src/api/gallery.ts frontend/src/api/analysis.ts
git commit -m "feat(frontend): projects list + per-project tabbed workspace reusing existing pages"
```

---

### Task 11: Contract check + deploy note

**Files:**
- Modify: `docs/superpowers/plans/phase1-cutover-runbook.md` (append migration note) — or note in commit message only.

- [ ] **Step 1: Run the api-contract-checker agent** over the phase-3 surface (members, projects, uploads, review/gallery/analysis/evaluations param changes). Fix every reported mismatch (backend Pydantic ↔ `frontend/src/types` ↔ api modules).

- [ ] **Step 2: Final regression sweep (per-file)**

```bash
/tmp/runtests.sh tests/test_phase3_schema.py
/tmp/runtests.sh tests/test_phase3_identity.py
/tmp/runtests.sh tests/test_phase3_projects.py
/tmp/runtests.sh tests/test_phase3_uploads.py
/tmp/runtests.sh tests/test_phase3_propagation.py
/tmp/runtests.sh tests/test_phase3_scoping_filters.py
/tmp/runtests.sh tests/test_api_review.py
/tmp/runtests.sh tests/test_api_gallery.py
/tmp/runtests.sh tests/test_api_workspace.py
/tmp/runtests.sh tests/test_dispatch_task.py
cd frontend && ./node_modules/.bin/tsc -b --force
```

Expected: every file green; tsc exit 0.

- [ ] **Step 3: Commit any contract fixes**

```bash
git add -A backend frontend
git commit -m "fix(contract): align phase-3 API models with frontend types"
```

(Skip if the checker found nothing.)

**Deploy note (for the operator):** this phase ships migration 0003. On the VM:

```bash
git pull
docker compose build
docker compose run --rm --no-deps backend alembic upgrade head
docker compose up -d
```

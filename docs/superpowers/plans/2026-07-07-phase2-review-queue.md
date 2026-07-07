# Phase 2: Prompt Review Queue Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every generation (image via ComfyUI, video via Kling API or ComfyUI kling.json) stops auto-dispatching and instead lands in a persistent `generation_requests` review queue where a human edits/approves prompts before anything is sent to a provider.

**Architecture:** New `generation_requests` table (Alembic migration `0002`) + `GenerationRequestsStorage` state machine (`pending_review → approved → dispatched → completed|failed`, plus `discarded`; `failed` is re-claimable for retry). A new `/api/review` router owns list/create/edit/discard/dispatch. Dispatch enqueues one Celery `dispatch_generation_request_task` per row, which routes by `provider` to the existing ComfyUI image client, Kling API client, or ComfyUI video path. The image pipeline's `async_process_image` stops calling `client.generate_image` and writes queue rows instead; the video page's generate endpoints are deleted and the frontend sends to the queue.

**Tech Stack:** SQLAlchemy 2.0 + Alembic (Postgres 16), FastAPI + Pydantic, Celery (queues `image`/`video`), React 18 + TanStack Query + shadcn/ui.

**Spec:** `docs/superpowers/specs/2026-07-06-production-readiness-design.md` (Phase 2 section). Scope decision (user, 2026-07-07): review queue covers **image AND video** generation.

## Global Constraints

- Tests run ONLY against the throwaway Postgres: `docker compose -f docker-compose.test.yml up -d` first. NEVER against live containers or real mounted data dirs.
- Run pytest **per file** (`pytest tests/<file> -v`); the full suite has ~24 known pollution failures.
- Frontend type-check with raw `./node_modules/.bin/tsc -b --force` from `frontend/` (the RTK proxy mangles tsc output — do not trust `npx tsc` through it).
- Schema changes ONLY via Alembic migration (no create-if-missing DDL anywhere).
- Status values, exact: `pending_review`, `approved`, `dispatched`, `completed`, `failed`, `discarded`.
- Provider values, exact: `kling` (Kling API video), `comfy_video` (ComfyUI kling.json video), `comfy_image` (ComfyUI image pipeline).
- No skip-review path: after Task 9 there is no endpoint that generates without a queue row.
- Work on branch `z-image-gallery-updates`. Commit after every task.
- Storage modules follow the existing pattern: `session_scope()` from `backend/database/engine.py`, `_row_dict` helpers, `format_legacy_ts` from `backend/database/db_utils.py` for timestamps.

---

### Task 1: `GenerationRequest` model + Alembic migration 0002

**Files:**
- Modify: `backend/database/models.py` (append new model)
- Create: `backend/database/alembic/versions/0002_generation_requests.py`
- Modify: `tests/database/test_alembic_adopt.py:21-29` (EXPECTED_TABLES)
- Test: `tests/database/test_generation_requests_storage.py` (new, migration test only for now)

**Interfaces:**
- Produces: `backend.database.models.GenerationRequest` (columns exactly as below) — Tasks 2+ import it.

- [ ] **Step 1: Write the failing migration test**

Create `tests/database/test_generation_requests_storage.py`:

```python
"""
Phase 2: generation_requests review queue — migration + storage tests.

State machine: pending_review -> approved -> dispatched -> completed|failed,
plus discarded (from pending_review/failed) and failed -> approved (retry).
"""
import pytest
from sqlalchemy import inspect


def test_migration_creates_generation_requests(migrated_engine):
    inspector = inspect(migrated_engine)
    assert "generation_requests" in inspector.get_table_names()
    cols = {c["name"] for c in inspector.get_columns("generation_requests")}
    assert {
        "id", "batch_id", "source_image_path", "original_prompt", "prompt",
        "provider", "workflow_name", "settings", "status", "execution_id",
        "result_path", "error", "created_at", "updated_at",
    } <= cols
    index_names = {ix["name"] for ix in inspector.get_indexes("generation_requests")}
    assert "idx_generation_requests_status" in index_names
    assert "idx_generation_requests_batch_id" in index_names
    assert "idx_generation_requests_execution_id" in index_names
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
docker compose -f docker-compose.test.yml up -d
pytest tests/database/test_generation_requests_storage.py -v
```
Expected: FAIL — `assert "generation_requests" in ...` (table doesn't exist).

- [ ] **Step 3: Add the model to `backend/database/models.py`**

Append at the end of the file (after `Post`):

```python
class GenerationRequest(Base):
    """Prompt review queue (phase 2). All generation flows through here."""

    __tablename__ = "generation_requests"
    __table_args__ = (
        Index("idx_generation_requests_status", "status"),
        Index("idx_generation_requests_batch_id", "batch_id"),
        Index("idx_generation_requests_execution_id", "execution_id"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    batch_id: Mapped[str] = mapped_column(Text, nullable=False)
    source_image_path: Mapped[str] = mapped_column(Text, nullable=False)
    original_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    workflow_name: Mapped[Optional[str]] = mapped_column(Text)
    settings: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=sa_text("'{}'::jsonb")
    )
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="pending_review"
    )
    execution_id: Mapped[Optional[str]] = mapped_column(Text)
    result_path: Mapped[Optional[str]] = mapped_column(Text)
    error: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
```

Add to the imports at the top of `models.py`:

```python
from sqlalchemy import text as sa_text
```

(`Index`, `Text`, `func`, `JSONB`, `TIMESTAMP` are already imported.)

- [ ] **Step 4: Write the migration**

Create `backend/database/alembic/versions/0002_generation_requests.py`:

```python
"""generation_requests review queue

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0002'
down_revision: Union[str, None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'generation_requests',
        sa.Column('id', sa.Text(), nullable=False),
        sa.Column('batch_id', sa.Text(), nullable=False),
        sa.Column('source_image_path', sa.Text(), nullable=False),
        sa.Column('original_prompt', sa.Text(), nullable=False),
        sa.Column('prompt', sa.Text(), nullable=False),
        sa.Column('provider', sa.Text(), nullable=False),
        sa.Column('workflow_name', sa.Text(), nullable=True),
        sa.Column('settings', postgresql.JSONB(astext_type=sa.Text()),
                  server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('status', sa.Text(), server_default='pending_review', nullable=False),
        sa.Column('execution_id', sa.Text(), nullable=True),
        sa.Column('result_path', sa.Text(), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True),
                  server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True),
                  server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_generation_requests_status', 'generation_requests', ['status'])
    op.create_index('idx_generation_requests_batch_id', 'generation_requests', ['batch_id'])
    op.create_index('idx_generation_requests_execution_id', 'generation_requests', ['execution_id'])


def downgrade() -> None:
    op.drop_table('generation_requests')
```

(No adoption guards needed — unlike 0001, this table can never pre-exist.)

- [ ] **Step 5: Update the adoption test's expected tables**

In `tests/database/test_alembic_adopt.py`, add to `EXPECTED_TABLES`:

```python
EXPECTED_TABLES = {
    "caption_exports",
    "evaluations",
    "image_logs",
    "runpod_jobs",
    "runs",
    "video_logs",
    "posts",
    "generation_requests",
}
```

Also update the same file's head assertion: change `== "0001"` to `== "0002"` in `test_upgrade_adopts_existing_runs_posts`.

- [ ] **Step 6: Run tests to verify they pass**

```bash
pytest tests/database/test_generation_requests_storage.py -v
pytest tests/database/test_alembic_adopt.py -v
pytest tests/database/test_models.py -v
```
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/database/models.py backend/database/alembic/versions/0002_generation_requests.py tests/database/test_generation_requests_storage.py tests/database/test_alembic_adopt.py
git commit -m "feat(review): add generation_requests table (migration 0002)"
```

---

### Task 2: `GenerationRequestsStorage` state machine

**Files:**
- Create: `backend/database/generation_requests_storage.py`
- Test: `tests/database/test_generation_requests_storage.py` (append)

**Interfaces:**
- Consumes: `GenerationRequest` model (Task 1), `session_scope` / `format_legacy_ts` (existing).
- Produces (Tasks 3–6 rely on these exact signatures):
  - `InvalidStateError(Exception)`
  - `GenerationRequestsStorage()` (no args) with methods:
    - `create_requests(items: list[dict], batch_id: str | None = None) -> dict` → `{"batch_id": str, "request_ids": list[str]}`; each item: `{"source_image_path", "prompt", "provider", "workflow_name"?: str|None, "settings"?: dict}`
    - `get_request(request_id: str) -> dict | None`
    - `list_requests(status: str | None = None, batch_id: str | None = None, page: int = 1, per_page: int = 50) -> dict` → `{"items", "total", "page", "pages"}`
    - `update_request(request_id, prompt=None, settings=None) -> dict | None` (only `pending_review`; wrong state raises `InvalidStateError`)
    - `discard_request(request_id: str) -> dict | None` (`pending_review`/`failed` → `discarded`)
    - `claim_for_dispatch(ids: list[str]) -> list[str]` (`pending_review`/`failed` → `approved`, returns claimed ids)
    - `begin_dispatch(request_id: str) -> dict | None` (`approved` → `dispatched`, returns row; `None` if not claimable)
    - `set_execution(request_id: str, execution_id: str) -> None`
    - `mark_failed(request_id: str, error: str) -> None`
    - `mark_completed_by_execution(execution_id: str, result_path: str | None = None) -> bool`
    - `mark_failed_by_execution(execution_id: str, error: str) -> bool`
  - Row dict keys: `id, batch_id, source_image_path, original_prompt, prompt, provider, workflow_name, settings (dict), status, execution_id, result_path, error, created_at (str|None), updated_at (str|None)`

- [ ] **Step 1: Write the failing tests**

Append to `tests/database/test_generation_requests_storage.py`:

```python
from backend.database.generation_requests_storage import (
    GenerationRequestsStorage,
    InvalidStateError,
)


@pytest.fixture
def storage(clean_tables):
    return GenerationRequestsStorage()


def _item(prompt="a prompt", provider="comfy_image", **overrides):
    item = {
        "source_image_path": "/app/processed/img.png",
        "prompt": prompt,
        "provider": provider,
        "workflow_name": "wf.json",
        "settings": {"persona": "p1", "width": 1024},
    }
    item.update(overrides)
    return item


def _create_one(storage, **overrides):
    result = storage.create_requests([_item(**overrides)])
    return result["request_ids"][0]


# ---- create / get ----

def test_create_and_get_roundtrip(storage):
    result = storage.create_requests([_item(), _item(prompt="second")])
    assert len(result["request_ids"]) == 2
    row = storage.get_request(result["request_ids"][0])
    assert row["status"] == "pending_review"
    assert row["prompt"] == "a prompt"
    assert row["original_prompt"] == "a prompt"      # immutable copy
    assert row["settings"] == {"persona": "p1", "width": 1024}  # dict, not str
    assert row["batch_id"] == result["batch_id"]
    assert row["execution_id"] is None


def test_create_uses_given_batch_id(storage):
    result = storage.create_requests([_item()], batch_id="batch-x")
    assert result["batch_id"] == "batch-x"


def test_get_missing_returns_none(storage):
    assert storage.get_request("nope") is None


# ---- list ----

def test_list_filters_and_pagination(storage):
    storage.create_requests([_item() for _ in range(3)], batch_id="b1")
    storage.create_requests([_item()], batch_id="b2")
    assert storage.list_requests(batch_id="b1")["total"] == 3
    assert storage.list_requests(status="pending_review")["total"] == 4
    assert storage.list_requests(status="completed")["total"] == 0
    page = storage.list_requests(page=1, per_page=3)
    assert len(page["items"]) == 3
    assert page["pages"] == 2


# ---- edit ----

def test_update_prompt_while_pending(storage):
    rid = _create_one(storage)
    row = storage.update_request(rid, prompt="edited")
    assert row["prompt"] == "edited"
    assert row["original_prompt"] == "a prompt"      # untouched


def test_update_settings_while_pending(storage):
    rid = _create_one(storage)
    row = storage.update_request(rid, settings={"width": 512})
    assert row["settings"] == {"width": 512}


def test_update_after_claim_raises(storage):
    rid = _create_one(storage)
    storage.claim_for_dispatch([rid])
    with pytest.raises(InvalidStateError):
        storage.update_request(rid, prompt="too late")


def test_update_missing_returns_none(storage):
    assert storage.update_request("nope", prompt="x") is None


# ---- discard ----

def test_discard_pending(storage):
    rid = _create_one(storage)
    assert storage.discard_request(rid)["status"] == "discarded"


def test_discard_dispatched_raises(storage):
    rid = _create_one(storage)
    storage.claim_for_dispatch([rid])
    storage.begin_dispatch(rid)
    with pytest.raises(InvalidStateError):
        storage.discard_request(rid)


# ---- dispatch state machine ----

def test_claim_only_pending_or_failed(storage):
    rid1 = _create_one(storage)
    rid2 = _create_one(storage)
    storage.discard_request(rid2)
    claimed = storage.claim_for_dispatch([rid1, rid2, "missing"])
    assert claimed == [rid1]
    assert storage.get_request(rid1)["status"] == "approved"


def test_claim_twice_is_idempotent(storage):
    rid = _create_one(storage)
    assert storage.claim_for_dispatch([rid]) == [rid]
    assert storage.claim_for_dispatch([rid]) == []   # double-click / two members


def test_begin_dispatch_transitions_once(storage):
    rid = _create_one(storage)
    storage.claim_for_dispatch([rid])
    row = storage.begin_dispatch(rid)
    assert row["status"] == "dispatched"
    assert storage.begin_dispatch(rid) is None       # celery redelivery no-ops


def test_begin_dispatch_requires_approved(storage):
    rid = _create_one(storage)
    assert storage.begin_dispatch(rid) is None       # still pending_review


def test_execution_and_completion(storage):
    rid = _create_one(storage)
    storage.claim_for_dispatch([rid])
    storage.begin_dispatch(rid)
    storage.set_execution(rid, "exec-1")
    assert storage.get_request(rid)["execution_id"] == "exec-1"
    assert storage.mark_completed_by_execution("exec-1", "/app/results/v.mp4") is True
    row = storage.get_request(rid)
    assert row["status"] == "completed"
    assert row["result_path"] == "/app/results/v.mp4"


def test_mark_completed_unknown_execution_is_noop(storage):
    assert storage.mark_completed_by_execution("ghost") is False


def test_failed_then_retry(storage):
    rid = _create_one(storage)
    storage.claim_for_dispatch([rid])
    storage.begin_dispatch(rid)
    storage.mark_failed(rid, "provider exploded")
    row = storage.get_request(rid)
    assert row["status"] == "failed"
    assert row["error"] == "provider exploded"
    assert storage.claim_for_dispatch([rid]) == [rid]  # retry path
    assert storage.get_request(rid)["error"] is None   # cleared on retry


def test_mark_failed_by_execution(storage):
    rid = _create_one(storage)
    storage.claim_for_dispatch([rid])
    storage.begin_dispatch(rid)
    storage.set_execution(rid, "exec-f")
    assert storage.mark_failed_by_execution("exec-f", "comfy error") is True
    assert storage.get_request(rid)["status"] == "failed"


def test_constructor_takes_no_args(clean_tables):
    with pytest.raises(TypeError):
        GenerationRequestsStorage(db_path="legacy.db")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/database/test_generation_requests_storage.py -v
```
Expected: FAIL — `ModuleNotFoundError: backend.database.generation_requests_storage`.

- [ ] **Step 3: Implement the storage module**

Create `backend/database/generation_requests_storage.py`:

```python
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
        "created_at": _format_ts(row.created_at),
        "updated_at": _format_ts(row.updated_at),
    }


class GenerationRequestsStorage:
    """Schema is owned by Alembic; this class only reads/writes rows."""

    def create_requests(self, items: list, batch_id: Optional[str] = None) -> dict:
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
        page: int = 1,
        per_page: int = 50,
    ) -> dict:
        with session_scope() as session:
            query = select(GenerationRequest)
            if status:
                query = query.where(GenerationRequest.status == status)
            if batch_id:
                query = query.where(GenerationRequest.batch_id == batch_id)
            total = session.execute(
                select(func.count()).select_from(query.subquery())
            ).scalar() or 0
            rows = session.execute(
                query.order_by(GenerationRequest.created_at.desc(),
                               GenerationRequest.id.desc())
                .offset((page - 1) * per_page)
                .limit(per_page)
            ).scalars().all()
            return {
                "items": [_row_dict(r) for r in rows],
                "total": total,
                "page": page,
                "pages": max(1, math.ceil(total / per_page)),
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
                    GenerationRequest.status == PENDING_REVIEW,
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
                f"{PENDING_REVIEW!r} rows can be edited."
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

    def mark_failed(self, request_id: str, error: str) -> None:
        with session_scope() as session:
            session.execute(
                update(GenerationRequest)
                .where(
                    GenerationRequest.id == request_id,
                    GenerationRequest.status.in_([APPROVED, DISPATCHED]),
                )
                .values(status=FAILED, error=error, updated_at=func.now())
            )

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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/database/test_generation_requests_storage.py -v
```
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/database/generation_requests_storage.py tests/database/test_generation_requests_storage.py
git commit -m "feat(review): GenerationRequestsStorage state machine"
```

---

### Task 3: Celery dispatch task + real `poll_kling_video_task`

**Files:**
- Modify: `backend/tasks.py` (append two tasks)
- Modify: `backend/celery_app.py:41-48` (task_routes)
- Modify: `backend/services/video.py:80-85` (fix phantom import — see below)
- Test: `tests/test_dispatch_task.py` (new)

**Context — pre-existing bug this task fixes:** `backend/services/video.py:82` does `from backend.tasks import poll_kling_video_task`, but that task **is not defined anywhere** — the Kling-API video path currently dies with `ImportError`. This task defines it for real.

**Interfaces:**
- Consumes: `GenerationRequestsStorage` (Task 2), existing `get_instances()`, `download_execution_task`, `DOWNLOAD_POLL_INTERVAL`, `DEFAULT_NEGATIVE_PROMPT`, `VideoService.queue_video` / `queue_video_comfy`.
- Produces:
  - `backend.tasks.dispatch_generation_request_task(request_id: str)` — Celery task; Task 5 (API) enqueues it via `.apply_async(args=[rid], queue=...)`.
  - `backend.tasks.poll_kling_video_task(task_id: str)` — Celery task; `VideoService.queue_video` keeps its existing call site.
- `comfy_image` settings dict contract (written by Task 6, read here): keys `persona, workflow_type, strength_model, seed_strategy, base_seed, width, height, lora_name, clip_model_type, pipeline_type, workflow_overrides, negative_prompt`.
- `kling` settings = `KlingSettings` model dump; `comfy_video` settings = `ComfyKlingSettings` model dump.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_dispatch_task.py`:

```python
"""
dispatch_generation_request_task: routes an approved generation_requests row
to the right provider, is idempotent, and turns provider errors into
status=failed on that row only.
"""
from unittest.mock import MagicMock, patch

import pytest

from backend.database.generation_requests_storage import GenerationRequestsStorage


@pytest.fixture
def storage(clean_tables):
    return GenerationRequestsStorage()


def _create(storage, provider, settings=None, claim=True):
    result = storage.create_requests([{
        "source_image_path": "/app/processed/img.png",
        "prompt": "a prompt",
        "provider": provider,
        "workflow_name": "wf.json",
        "settings": settings or {},
    }])
    rid = result["request_ids"][0]
    if claim:
        storage.claim_for_dispatch([rid])
    return rid


def test_dispatch_comfy_image(storage):
    from backend import tasks as tasks_module
    rid = _create(storage, "comfy_image", settings={
        "persona": "p1", "workflow_type": "turbo", "pipeline_type": "image.subject_environment",
        "width": 1024, "height": 1024,
    })

    fake_client = MagicMock()
    async def fake_generate_image(**kwargs):
        fake_client.captured = kwargs
        return "exec-img-1"
    fake_client.generate_image = fake_generate_image
    fake_image_storage = MagicMock()

    with patch.object(tasks_module, "get_instances",
                      return_value=(None, fake_client, fake_image_storage)), \
         patch.object(tasks_module.download_execution_task, "apply_async") as mock_dl:
        result = tasks_module.dispatch_generation_request_task.run(rid)

    assert result["execution_id"] == "exec-img-1"
    assert fake_client.captured["positive_prompt"] == "a prompt"
    assert fake_client.captured["pipeline_type"] == "image.subject_environment"
    fake_image_storage.log_execution.assert_called_once()
    mock_dl.assert_called_once()
    row = storage.get_request(rid)
    assert row["status"] == "dispatched"
    assert row["execution_id"] == "exec-img-1"


def test_dispatch_kling_video(storage):
    from backend import tasks as tasks_module
    rid = _create(storage, "kling", settings={"model_name": "kling-v1-6", "mode": "std"})

    with patch("backend.services.video.VideoService") as MockSvc:
        MockSvc.return_value.queue_video.return_value = "kling-task-1"
        result = tasks_module.dispatch_generation_request_task.run(rid)

    assert result["execution_id"] == "kling-task-1"
    assert storage.get_request(rid)["status"] == "dispatched"


def test_dispatch_comfy_video(storage):
    from backend import tasks as tasks_module
    rid = _create(storage, "comfy_video", settings={"mode": "std", "duration": "5"})

    with patch("backend.services.video.VideoService") as MockSvc:
        MockSvc.return_value.queue_video_comfy.return_value = "prompt-id-1"
        result = tasks_module.dispatch_generation_request_task.run(rid)

    assert result["execution_id"] == "prompt-id-1"
    assert storage.get_request(rid)["status"] == "dispatched"


def test_dispatch_provider_error_marks_failed(storage):
    from backend import tasks as tasks_module
    rid = _create(storage, "kling")

    with patch("backend.services.video.VideoService") as MockSvc:
        MockSvc.return_value.queue_video.side_effect = RuntimeError("kling down")
        result = tasks_module.dispatch_generation_request_task.run(rid)

    assert "error" in result
    row = storage.get_request(rid)
    assert row["status"] == "failed"
    assert "kling down" in row["error"]


def test_dispatch_unclaimed_row_skips(storage):
    from backend import tasks as tasks_module
    rid = _create(storage, "kling", claim=False)  # still pending_review
    result = tasks_module.dispatch_generation_request_task.run(rid)
    assert result["skipped"] is True
    assert storage.get_request(rid)["status"] == "pending_review"


def test_poll_kling_video_task_exists():
    from backend.tasks import poll_kling_video_task  # was a phantom import before
    assert poll_kling_video_task.name == "backend.tasks.poll_kling_video_task"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_dispatch_task.py -v
```
Expected: FAIL — `AttributeError: ... has no attribute 'dispatch_generation_request_task'` (and the phantom-import test fails with ImportError).

- [ ] **Step 3: Implement the tasks**

Append to `backend/tasks.py`:

```python
@celery_app.task(bind=True, name="backend.tasks.dispatch_generation_request_task")
def dispatch_generation_request_task(self, request_id: str):
    """Send ONE approved generation_requests row to its provider.

    Returns instead of raising on provider errors so a failure affects only
    this item (the rest of a dispatched selection proceeds), matching the
    phase-2 spec. begin_dispatch() is the idempotency guard: a redelivered
    task finds the row already 'dispatched' and no-ops.
    """
    from backend.database.generation_requests_storage import GenerationRequestsStorage

    storage = GenerationRequestsStorage()
    row = storage.begin_dispatch(request_id)
    if row is None:
        logger.info(f"[dispatch] {request_id} not in 'approved' state — skipping")
        return {"request_id": request_id, "skipped": True}

    provider = row["provider"]
    settings = row["settings"] or {}
    try:
        if provider == "comfy_image":
            _, client, image_storage = get_instances()
            execution_id = asyncio.run(client.generate_image(
                positive_prompt=row["prompt"],
                negative_prompt=settings.get("negative_prompt", DEFAULT_NEGATIVE_PROMPT),
                kol_persona=settings.get("persona"),
                workflow_type=settings.get("workflow_type"),
                strength_model=settings.get("strength_model"),
                seed_strategy=settings.get("seed_strategy"),
                base_seed=settings.get("base_seed"),
                width=settings.get("width"),
                height=settings.get("height"),
                lora_name=settings.get("lora_name"),
                clip_model_type=settings.get("clip_model_type", "qwen_image"),
                pipeline_type=settings.get("pipeline_type", "image.subject_environment"),
                workflow_overrides=settings.get("workflow_overrides") or {},
                workflow_name=row["workflow_name"],
            ))
            if not execution_id:
                raise RuntimeError("ComfyUI returned no execution id")
            image_storage.log_execution(
                execution_id=execution_id,
                prompt=row["prompt"],
                image_ref_path=row["source_image_path"],
                persona=settings.get("persona"),
            )
            download_execution_task.apply_async(
                args=[execution_id, row["source_image_path"]],
                countdown=DOWNLOAD_POLL_INTERVAL,
                queue="image",
            )
        elif provider == "kling":
            from backend.services.video import VideoService
            from backend.models.video import KlingSettings
            execution_id = VideoService().queue_video(
                image_path=row["source_image_path"],
                prompt=row["prompt"],
                kling_settings=KlingSettings(**settings),
                batch_id=row["batch_id"],
            )
        elif provider == "comfy_video":
            from backend.services.video import VideoService
            from backend.models.video import ComfyKlingSettings
            execution_id = VideoService().queue_video_comfy(
                image_path=row["source_image_path"],
                prompt=row["prompt"],
                comfy_settings=ComfyKlingSettings(**settings),
                batch_id=row["batch_id"],
            )
        else:
            raise ValueError(f"Unknown provider {provider!r}")

        storage.set_execution(request_id, execution_id)
        return {"request_id": request_id, "execution_id": execution_id}
    except Exception as e:
        logger.error(f"[dispatch] {request_id} ({provider}) failed: {e}")
        storage.mark_failed(request_id, str(e))
        return {"request_id": request_id, "error": str(e)}


@celery_app.task(
    bind=True,
    name="backend.tasks.poll_kling_video_task",
    max_retries=120,
    default_retry_delay=10,
)
def poll_kling_video_task(self, task_id: str):
    """Poll the Kling API until a video task reaches a terminal state.

    VideoService.get_video_status() already downloads the file and updates
    video_logs; this task exists so completion does not depend on a browser
    polling the status endpoint. (Fixes the pre-existing phantom import in
    VideoService.queue_video — this task never existed.)
    """
    from backend.services.video import VideoService

    status = VideoService().get_video_status(task_id)
    if status.status == "completed":
        return {"task_id": task_id, "status": "completed"}
    if status.status in ("failed", "error"):
        logger.error(f"[poll_kling_video_task] {task_id} -> {status.status}: {status.error_message}")
        return {"task_id": task_id, "status": status.status}
    raise self.retry()
```

- [ ] **Step 4: Register queue routes**

In `backend/celery_app.py`, add to `task_routes`:

```python
        "backend.tasks.poll_kling_video_task": {"queue": "video"},
        "backend.tasks.caption_export_task": {"queue": "image"},
```

(Leave `dispatch_generation_request_task` out of `task_routes` — the API picks its queue per-row at `apply_async` time in Task 5.)

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/test_dispatch_task.py -v
```
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/tasks.py backend/celery_app.py
git commit -m "feat(review): provider-routing dispatch task; fix phantom poll_kling_video_task"
```

---

### Task 4: Completion hooks — provider results update the queue row

**Files:**
- Modify: `backend/tasks.py` (`download_execution_task`, `poll_comfy_video_task`)
- Modify: `backend/services/video.py` (`get_video_status`)
- Test: `tests/test_dispatch_task.py` (append)

**Interfaces:**
- Consumes: `mark_completed_by_execution` / `mark_failed_by_execution` (Task 2).
- Produces: nothing new — best-effort side effects. A missing queue row (e.g. legacy executions) is a silent no-op; a hook exception must never break the host task.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_dispatch_task.py`:

```python
# ---- completion hooks ----

def _dispatched_row(storage, provider="comfy_image", execution_id="exec-hook"):
    rid = _create(storage, provider)
    storage.begin_dispatch(rid)
    storage.set_execution(rid, execution_id)
    return rid


def test_download_execution_task_completes_queue_row(storage, tmp_path, monkeypatch):
    from backend import tasks as tasks_module
    rid = _dispatched_row(storage, execution_id="exec-dl")

    fake_client = MagicMock()
    async def fake_check_status(execution_id):
        return {"status": "completed",
                "output_images": [{"node": ["comfy/path.png"]}]}
    async def fake_download(path):
        return b"png-bytes"
    fake_client.check_status = fake_check_status
    fake_client.download_image_by_path = fake_download
    fake_image_storage = MagicMock()

    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    monkeypatch.setattr(tasks_module.GlobalConfig, "OUTPUT_DIR", str(tmp_path), raising=False)
    with patch.object(tasks_module, "get_instances",
                      return_value=(None, fake_client, fake_image_storage)):
        tasks_module.download_execution_task.run("exec-dl", "/app/processed/img.png")

    row = storage.get_request(rid)
    assert row["status"] == "completed"
    assert row["result_path"]


def test_poll_comfy_video_task_failure_fails_queue_row(storage):
    from backend import tasks as tasks_module
    rid = _dispatched_row(storage, provider="comfy_video", execution_id="prompt-x")

    async def fake_check(prompt_id):
        return {"status": "failed", "error_message": "node exploded"}

    with patch("backend.third_parties.comfyui_client.ComfyUIClient") as MockClient:
        MockClient.return_value.check_video_status = fake_check
        tasks_module.poll_comfy_video_task.run("prompt-x", "/app/img.png")

    row = storage.get_request(rid)
    assert row["status"] == "failed"
    assert "node exploded" in row["error"]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_dispatch_task.py -v
```
Expected: the two new tests FAIL (queue row stays `dispatched`); earlier tests still PASS.

- [ ] **Step 3: Add a best-effort hook helper and call it from the three completion sites**

In `backend/tasks.py`, add near the top (after `get_instances`):

```python
def _review_queue_hook(execution_id: str, *, completed: bool,
                       result_path=None, error=None):
    """Best-effort: reflect a provider result onto the generation_requests
    row that dispatched it. Executions with no queue row (legacy, or logged
    outside the queue) are a no-op; hook errors never break the host task."""
    try:
        from backend.database.generation_requests_storage import GenerationRequestsStorage
        storage = GenerationRequestsStorage()
        if completed:
            storage.mark_completed_by_execution(execution_id, result_path)
        else:
            storage.mark_failed_by_execution(execution_id, error or "generation failed")
    except Exception as e:
        logger.warning(f"[review-hook] failed for {execution_id}: {e}")
```

Wire it into `download_execution_task` (three spots):
- after `storage.update_result_path(...)` (success): `_review_queue_hook(execution_id, completed=True, result_path=",".join(saved_paths))`
- after each `storage.mark_as_failed(execution_id)` (the no-paths case and the `status == "failed"` case): `_review_queue_hook(execution_id, completed=False, error=error_message if status == "failed" else "no output images")` — in the no-paths branches pass `error="no output images"`.

Wire it into `poll_comfy_video_task`:
- after the completed-branch `storage.update_result(...)`: `_review_queue_hook(prompt_id, completed=True, result_path=output_path)`
- after the failed-branch `storage.update_result(execution_id=prompt_id, status="failed")`: `_review_queue_hook(prompt_id, completed=False, error=error_message)`

Wire it into `backend/services/video.py` `get_video_status` (kling — covers both the poll task and browser polling):
- in the `kling_status == "succeed"` download branch, right after `self.storage.update_result(task_id, str(local_file), "completed")`:

```python
                    self._review_queue_hook(task_id, completed=True, result_path=str(local_file))
```

- after the `status_map` mapping, before building the response:

```python
        if status == "failed":
            self._review_queue_hook(task_id, completed=False, error=error_message)
```

- and add the method to `VideoService`:

```python
    def _review_queue_hook(self, execution_id, *, completed, result_path=None, error=None):
        try:
            from backend.database.generation_requests_storage import GenerationRequestsStorage
            storage = GenerationRequestsStorage()
            if completed:
                storage.mark_completed_by_execution(execution_id, result_path)
            else:
                storage.mark_failed_by_execution(execution_id, error or "generation failed")
        except Exception as e:
            logger.warning(f"[review-hook] failed for {execution_id}: {e}")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_dispatch_task.py -v
```
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/tasks.py backend/services/video.py tests/test_dispatch_task.py
git commit -m "feat(review): completion hooks map provider results onto queue rows"
```

---

### Task 5: `/api/review` router + Pydantic models

**Files:**
- Create: `backend/models/review.py`
- Create: `backend/api/review.py`
- Modify: `backend/main.py` (import + `include_router`)
- Test: `tests/test_api_review.py` (new)

**Interfaces:**
- Consumes: `GenerationRequestsStorage`, `InvalidStateError` (Task 2), `dispatch_generation_request_task` (Task 3).
- Produces (frontend Task 7 mirrors these exactly):
  - `GET  /api/review/requests?status=&batch_id=&page=&per_page=` → `{items, total, page, pages}`
  - `POST /api/review/requests` body `{items: [{source_image_path, prompt, provider, workflow_name?, settings?}], batch_id?}` → `{batch_id, request_ids}`
  - `PATCH /api/review/requests/{id}` body `{prompt?, settings?}` → item; 404 missing, 409 wrong state
  - `DELETE /api/review/requests/{id}` → item (discarded); 404/409
  - `POST /api/review/dispatch` body `{ids: [...]}` → `{dispatched: [...], skipped: [...]}`
  - `GET  /api/review/requests/{id}/thumbnail` → image/jpeg (serves ONLY the DB-stored `source_image_path` — never a client-supplied path)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_api_review.py`:

```python
"""
/api/review/* endpoint tests. Real throwaway Postgres (clean_tables); Celery
dispatch is mocked — no broker, no providers.
"""
from unittest.mock import patch

import pytest

from tests.conftest import make_png
from backend.database.generation_requests_storage import GenerationRequestsStorage


@pytest.fixture
def storage(clean_tables):
    return GenerationRequestsStorage()


def _payload(**overrides):
    item = {
        "source_image_path": "/app/processed/img.png",
        "prompt": "a prompt",
        "provider": "comfy_image",
        "workflow_name": "wf.json",
        "settings": {"persona": "p1"},
    }
    item.update(overrides)
    return {"items": [item]}


def test_create_and_list(client, storage):
    r = client.post("/api/review/requests", json=_payload())
    assert r.status_code == 200
    body = r.json()
    assert len(body["request_ids"]) == 1

    r = client.get("/api/review/requests?status=pending_review")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 1
    item = data["items"][0]
    assert item["status"] == "pending_review"
    assert item["original_prompt"] == "a prompt"
    assert item["settings"] == {"persona": "p1"}


def test_create_rejects_unknown_provider(client, storage):
    r = client.post("/api/review/requests", json=_payload(provider="dreamania"))
    assert r.status_code == 422


def test_list_invalid_status_422(client, storage):
    assert client.get("/api/review/requests?status=bogus").status_code == 422


def test_patch_prompt(client, storage):
    rid = client.post("/api/review/requests", json=_payload()).json()["request_ids"][0]
    r = client.patch(f"/api/review/requests/{rid}", json={"prompt": "edited"})
    assert r.status_code == 200
    assert r.json()["prompt"] == "edited"


def test_patch_missing_404(client, storage):
    assert client.patch("/api/review/requests/nope", json={"prompt": "x"}).status_code == 404


def test_patch_after_dispatch_409(client, storage):
    rid = client.post("/api/review/requests", json=_payload()).json()["request_ids"][0]
    storage.claim_for_dispatch([rid])
    r = client.patch(f"/api/review/requests/{rid}", json={"prompt": "late"})
    assert r.status_code == 409


def test_discard(client, storage):
    rid = client.post("/api/review/requests", json=_payload()).json()["request_ids"][0]
    r = client.delete(f"/api/review/requests/{rid}")
    assert r.status_code == 200
    assert r.json()["status"] == "discarded"


def test_discard_dispatched_409(client, storage):
    rid = client.post("/api/review/requests", json=_payload()).json()["request_ids"][0]
    storage.claim_for_dispatch([rid])
    storage.begin_dispatch(rid)
    assert client.delete(f"/api/review/requests/{rid}").status_code == 409


def test_dispatch_claims_and_enqueues(client, storage):
    ids = client.post(
        "/api/review/requests",
        json={"items": [
            dict(_payload()["items"][0]),
            dict(_payload(provider="kling")["items"][0]),
        ]},
    ).json()["request_ids"]

    with patch("backend.tasks.dispatch_generation_request_task.apply_async") as mock_aa:
        r = client.post("/api/review/dispatch", json={"ids": ids + ["missing"]})

    assert r.status_code == 200
    body = r.json()
    assert set(body["dispatched"]) == set(ids)
    assert body["skipped"] == ["missing"]
    assert mock_aa.call_count == 2
    queues = {c.kwargs["queue"] for c in mock_aa.call_args_list}
    assert queues == {"image", "video"}  # per-provider routing
    for rid in ids:
        assert storage.get_request(rid)["status"] == "approved"


def test_dispatch_is_idempotent(client, storage):
    rid = client.post("/api/review/requests", json=_payload()).json()["request_ids"][0]
    with patch("backend.tasks.dispatch_generation_request_task.apply_async") as mock_aa:
        client.post("/api/review/dispatch", json={"ids": [rid]})
        r2 = client.post("/api/review/dispatch", json={"ids": [rid]})
    assert r2.json()["dispatched"] == []
    assert mock_aa.call_count == 1


def test_thumbnail_serves_source_image(client, storage, tmp_path):
    png = make_png(str(tmp_path), "src.png")
    rid = client.post(
        "/api/review/requests",
        json={"items": [dict(_payload()["items"][0], source_image_path=str(png))]},
    ).json()["request_ids"][0]
    r = client.get(f"/api/review/requests/{rid}/thumbnail")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/jpeg"


def test_thumbnail_missing_file_404(client, storage):
    rid = client.post("/api/review/requests", json=_payload()).json()["request_ids"][0]
    assert client.get(f"/api/review/requests/{rid}/thumbnail").status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_api_review.py -v
```
Expected: FAIL — all requests 404 (router not mounted).

- [ ] **Step 3: Create the Pydantic models**

Create `backend/models/review.py`:

```python
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field

Provider = Literal["kling", "comfy_video", "comfy_image"]
ReviewStatus = Literal[
    "pending_review", "approved", "dispatched", "completed", "failed", "discarded"
]


class ReviewItemCreate(BaseModel):
    source_image_path: str
    prompt: str
    provider: Provider
    workflow_name: Optional[str] = None
    settings: Dict = Field(default_factory=dict)


class ReviewCreateRequest(BaseModel):
    items: List[ReviewItemCreate] = Field(min_length=1)
    batch_id: Optional[str] = None


class ReviewCreateResponse(BaseModel):
    batch_id: str
    request_ids: List[str]


class ReviewRequestItem(BaseModel):
    id: str
    batch_id: str
    source_image_path: str
    original_prompt: str
    prompt: str
    provider: str
    workflow_name: Optional[str] = None
    settings: Dict = Field(default_factory=dict)
    status: str
    execution_id: Optional[str] = None
    result_path: Optional[str] = None
    error: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class ReviewListResponse(BaseModel):
    items: List[ReviewRequestItem]
    total: int
    page: int
    pages: int


class ReviewPatchRequest(BaseModel):
    prompt: Optional[str] = None
    settings: Optional[Dict] = None


class ReviewDispatchRequest(BaseModel):
    ids: List[str] = Field(min_length=1)


class ReviewDispatchResponse(BaseModel):
    dispatched: List[str]
    skipped: List[str]
```

- [ ] **Step 4: Create the router**

Create `backend/api/review.py`:

```python
"""
Prompt review queue endpoints (phase 2). All generation flows through here:
rows are created by the image pipeline / the video page, edited while
pending_review, and dispatched to providers only via POST /dispatch.
"""
import io
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from backend.database.generation_requests_storage import (
    GenerationRequestsStorage,
    InvalidStateError,
)
from backend.models.review import (
    ReviewCreateRequest,
    ReviewCreateResponse,
    ReviewDispatchRequest,
    ReviewDispatchResponse,
    ReviewListResponse,
    ReviewPatchRequest,
    ReviewRequestItem,
    ReviewStatus,
)

logger = logging.getLogger(__name__)
router = APIRouter()

THUMBNAIL_SIZE = (256, 256)


@router.get("/requests", response_model=ReviewListResponse)
def list_requests(
    status: ReviewStatus | None = Query(default=None),
    batch_id: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=200),
    storage: GenerationRequestsStorage = Depends(GenerationRequestsStorage),
):
    return storage.list_requests(
        status=status, batch_id=batch_id, page=page, per_page=per_page
    )


@router.post("/requests", response_model=ReviewCreateResponse)
def create_requests(
    body: ReviewCreateRequest,
    storage: GenerationRequestsStorage = Depends(GenerationRequestsStorage),
):
    return storage.create_requests(
        [item.model_dump() for item in body.items], batch_id=body.batch_id
    )


@router.patch("/requests/{request_id}", response_model=ReviewRequestItem)
def patch_request(
    request_id: str,
    body: ReviewPatchRequest,
    storage: GenerationRequestsStorage = Depends(GenerationRequestsStorage),
):
    try:
        row = storage.update_request(
            request_id, prompt=body.prompt, settings=body.settings
        )
    except InvalidStateError as e:
        raise HTTPException(status_code=409, detail=str(e))
    if row is None:
        raise HTTPException(status_code=404, detail="Request not found")
    return row


@router.delete("/requests/{request_id}", response_model=ReviewRequestItem)
def discard_request(
    request_id: str,
    storage: GenerationRequestsStorage = Depends(GenerationRequestsStorage),
):
    try:
        row = storage.discard_request(request_id)
    except InvalidStateError as e:
        raise HTTPException(status_code=409, detail=str(e))
    if row is None:
        raise HTTPException(status_code=404, detail="Request not found")
    return row


@router.post("/dispatch", response_model=ReviewDispatchResponse)
def dispatch_requests(
    body: ReviewDispatchRequest,
    storage: GenerationRequestsStorage = Depends(GenerationRequestsStorage),
):
    from backend.tasks import dispatch_generation_request_task

    claimed = storage.claim_for_dispatch(body.ids)
    for rid in claimed:
        row = storage.get_request(rid)
        queue = "image" if row["provider"] == "comfy_image" else "video"
        dispatch_generation_request_task.apply_async(args=[rid], queue=queue)
    skipped = [i for i in body.ids if i not in set(claimed)]
    return ReviewDispatchResponse(dispatched=claimed, skipped=skipped)


@router.get("/requests/{request_id}/thumbnail")
def request_thumbnail(
    request_id: str,
    storage: GenerationRequestsStorage = Depends(GenerationRequestsStorage),
):
    """Thumbnail of the row's source image. Only the DB-stored path is ever
    opened — the client cannot supply a path, so no traversal surface."""
    from PIL import Image

    row = storage.get_request(request_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Request not found")
    source = Path(row["source_image_path"])
    if not source.is_file():
        raise HTTPException(status_code=404, detail="Source image not found")
    try:
        with Image.open(source) as img:
            img.thumbnail(THUMBNAIL_SIZE)
            buf = io.BytesIO()
            img.convert("RGB").save(buf, format="JPEG", quality=80)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Thumbnail failed: {e}")
    return Response(content=buf.getvalue(), media_type="image/jpeg")
```

- [ ] **Step 5: Mount the router**

In `backend/main.py`, add `review as review_module,` to the `from backend.api import (...)` block and after the other routers:

```python
app.include_router(review_module.router, prefix="/api/review", tags=["review"])
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
pytest tests/test_api_review.py -v
pytest tests/test_api_health.py -v
```
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/models/review.py backend/api/review.py backend/main.py tests/test_api_review.py
git commit -m "feat(review): /api/review router — list/create/edit/discard/dispatch/thumbnail"
```

---

### Task 6: Image pipeline stops dispatching — prompts land in the queue

**Files:**
- Modify: `backend/tasks.py` (`async_process_image`, the loop at ~lines 220-277)
- Modify: `tests/test_pipelines_api.py` (the two `async_process_image` tests that assert `generate_image` forwarding, ~lines 107-160 and ~230-260)

**Interfaces:**
- Consumes: `GenerationRequestsStorage.create_requests` (Task 2).
- Produces: `async_process_image` result dict becomes `{"success": True, "image_path", "queued_for_review": int, "total_variations": int, "batch_id": str, "request_ids": [str]}` (drops `queued_variations`/`execution_ids`; nothing in the frontend consumes those keys — verified by grep). The settings dict it writes is the `comfy_image` contract consumed by Task 3's dispatch task.

- [ ] **Step 1: Rewrite the affected tests to assert queue-row creation**

In `tests/test_pipelines_api.py`, replace the body of the deepest-hop test (`test_async_process_image_forwards_pipeline_type_to_generate_image`) with a queue-row assertion. The test currently mocks `client.generate_image` and asserts `pipeline_type` lands there; now the same forwarding is asserted **into `settings`** (dispatch-side forwarding is already covered by `tests/test_dispatch_task.py::test_dispatch_comfy_image`). Rename it accordingly:

```python
@pytest.mark.anyio
async def test_async_process_image_writes_review_request_with_pipeline_type(
    monkeypatch, clean_tables
):
    from backend import tasks as tasks_module
    from backend.database.generation_requests_storage import GenerationRequestsStorage

    class FakeWorkflow:
        async def process(self, **kwargs):
            return {"generated_prompts": ["a prompt"]}

    class FakeClient:
        async def generate_image(self, **kwargs):
            raise AssertionError("pipeline must NOT dispatch — review queue only")

    monkeypatch.setattr(
        tasks_module, "get_instances",
        lambda: (FakeWorkflow(), FakeClient(), MagicMock()),
    )

    result = await tasks_module.async_process_image(
        dest_image_path="/tmp/img.png",
        persona="p1",
        workflow_type="turbo",
        vision_model="gpt-4o",
        variation_count=1,
        strength_model=1.0,
        seed_strategy="random",
        base_seed=0,
        width=1024,
        height=1024,
        lora_name="lora",
        clip_model_type="qwen_image",
        pipeline_type="image.pose_transfer",
        workflow_overrides={"steps": 20},
        workflow_name="pose.json",
        task=MagicMock(),
    )

    assert result["success"] is True
    assert result["queued_for_review"] == 1
    row = GenerationRequestsStorage().get_request(result["request_ids"][0])
    assert row["status"] == "pending_review"
    assert row["provider"] == "comfy_image"
    assert row["prompt"] == "a prompt"
    assert row["workflow_name"] == "pose.json"
    assert row["settings"]["pipeline_type"] == "image.pose_transfer"
    assert row["settings"]["workflow_overrides"] == {"steps": 20}
    assert row["settings"]["persona"] == "p1"
```

Apply the same treatment to the second `generate_image`-asserting test near line 230 (whatever parameter it forwards — width/height/lora etc. — assert it in `row["settings"]` instead). Keep every other test in the file untouched. Add `from unittest.mock import MagicMock` and the `clean_tables` import if missing.

- [ ] **Step 2: Run to verify the rewritten tests fail**

```bash
pytest tests/test_pipelines_api.py -v
```
Expected: the rewritten tests FAIL (`generate_image` still called / no queue row); others PASS.

- [ ] **Step 3: Replace the dispatch loop in `async_process_image`**

In `backend/tasks.py`, delete the whole `for i, prompt_content in enumerate(prompts):` loop (the block that calls `client.generate_image`, `storage.log_execution`, and `download_execution_task.apply_async`) **and** the `successful_queues_for_image`/`execution_ids` initialization above it, replacing them with:

```python
    from backend.database.generation_requests_storage import GenerationRequestsStorage

    task.update_state(
        state="QUEUEING_REVIEW",
        meta={"status": f"📋 Sending {len(prompts)} prompt(s) to the review queue...", "progress": 80},
    )

    settings = {
        "persona": persona,
        "workflow_type": workflow_type,
        "strength_model": strength_model,
        "seed_strategy": seed_strategy,
        "base_seed": base_seed,
        "width": width,
        "height": height,
        "lora_name": lora_name,
        "clip_model_type": clip_model_type,
        "pipeline_type": pipeline_type,
        "workflow_overrides": workflow_overrides or {},
        "negative_prompt": DEFAULT_NEGATIVE_PROMPT,
    }
    created = GenerationRequestsStorage().create_requests([
        {
            "source_image_path": dest_image_path,
            "prompt": prompt_content,
            "provider": "comfy_image",
            "workflow_name": workflow_name,
            "settings": settings,
        }
        for prompt_content in prompts
    ])

    task.update_state(
        state="SUCCESS",
        meta={"status": f"✅ {len(prompts)} prompt(s) awaiting review for {dest_image_path}", "progress": 100},
    )

    return {
        "success": True,
        "image_path": dest_image_path,
        "queued_for_review": len(prompts),
        "total_variations": len(prompts),
        "batch_id": created["batch_id"],
        "request_ids": created["request_ids"],
    }
```

(`client` stays in scope from `get_instances()` — still used by the prompt-generation half. Batch grouping is per source image; cross-image grouping is a later refinement if the team wants it.)

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_pipelines_api.py -v
pytest tests/test_pipelines.py -v
pytest tests/test_pipeline_params.py -v
```
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/tasks.py tests/test_pipelines_api.py
git commit -m "feat(review): image pipeline writes review requests instead of dispatching"
```

---

### Task 7: Frontend review types + API client

**Files:**
- Create: `frontend/src/types/review.ts`
- Create: `frontend/src/api/review.ts`

**Interfaces:**
- Consumes: `/api/review/*` shapes (Task 5).
- Produces: `reviewApi` used by Tasks 8–9; types `ReviewRequestItem`, `ReviewProvider`, `ReviewStatus`, `ReviewListResponse`.

- [ ] **Step 1: Create the types**

Create `frontend/src/types/review.ts`:

```typescript
export type ReviewProvider = 'kling' | 'comfy_video' | 'comfy_image'

export type ReviewStatus =
  | 'pending_review'
  | 'approved'
  | 'dispatched'
  | 'completed'
  | 'failed'
  | 'discarded'

export interface ReviewRequestItem {
  id: string
  batch_id: string
  source_image_path: string
  original_prompt: string
  prompt: string
  provider: ReviewProvider
  workflow_name: string | null
  settings: Record<string, unknown>
  status: ReviewStatus
  execution_id: string | null
  result_path: string | null
  error: string | null
  created_at: string | null
  updated_at: string | null
}

export interface ReviewListResponse {
  items: ReviewRequestItem[]
  total: number
  page: number
  pages: number
}

export interface ReviewItemCreate {
  source_image_path: string
  prompt: string
  provider: ReviewProvider
  workflow_name?: string | null
  settings?: Record<string, unknown>
}

export interface ReviewCreateResponse {
  batch_id: string
  request_ids: string[]
}

export interface ReviewDispatchResponse {
  dispatched: string[]
  skipped: string[]
}
```

- [ ] **Step 2: Create the API client**

Create `frontend/src/api/review.ts`:

```typescript
import { apiClient } from '@/lib/api-client'
import type {
  ReviewCreateResponse,
  ReviewDispatchResponse,
  ReviewItemCreate,
  ReviewListResponse,
  ReviewRequestItem,
  ReviewStatus,
} from '@/types/review'

export const reviewApi = {
  listRequests: (params?: {
    status?: ReviewStatus
    batch_id?: string
    page?: number
    per_page?: number
  }) =>
    apiClient.get<ReviewListResponse>('/review/requests', { params }).then(r => r.data),

  createRequests: (body: { items: ReviewItemCreate[]; batch_id?: string }) =>
    apiClient.post<ReviewCreateResponse>('/review/requests', body).then(r => r.data),

  updateRequest: (id: string, body: { prompt?: string; settings?: Record<string, unknown> }) =>
    apiClient.patch<ReviewRequestItem>(`/review/requests/${id}`, body).then(r => r.data),

  discardRequest: (id: string) =>
    apiClient.delete<ReviewRequestItem>(`/review/requests/${id}`).then(r => r.data),

  dispatch: (ids: string[]) =>
    apiClient.post<ReviewDispatchResponse>('/review/dispatch', { ids }).then(r => r.data),

  getThumbnailUrl: (id: string) => `/api/review/requests/${id}/thumbnail`,
}
```

- [ ] **Step 3: Type-check**

```bash
cd frontend && ./node_modules/.bin/tsc -b --force
```
Expected: exit 0, no output. (Raw tsc — NOT through the RTK proxy.)

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/review.ts frontend/src/api/review.ts
git commit -m "feat(review): frontend review types + api client"
```

---

### Task 8: Review Queue page + route + nav

**Files:**
- Create: `frontend/src/pages/ReviewQueuePage.tsx`
- Modify: `frontend/src/App.tsx` (route)
- Modify: `frontend/src/components/shared/Layout.tsx:30-38` (nav item)

**Interfaces:**
- Consumes: `reviewApi` (Task 7); shadcn `Button`, `Badge`, `Textarea`, `Checkbox`, `Tabs` from `@/components/ui/*`.
- Produces: route `/review`.

- [ ] **Step 1: Create the page**

Create `frontend/src/pages/ReviewQueuePage.tsx`:

```tsx
import React, { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Checkbox } from '@/components/ui/checkbox'
import { Textarea } from '@/components/ui/textarea'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Loader2, RotateCcw, Send, Trash2 } from 'lucide-react'
import { reviewApi } from '@/api/review'
import type { ReviewRequestItem, ReviewStatus } from '@/types/review'

const STATUS_BADGE: Record<ReviewStatus, 'default' | 'secondary' | 'destructive' | 'outline'> = {
  pending_review: 'secondary',
  approved: 'default',
  dispatched: 'default',
  completed: 'outline',
  failed: 'destructive',
  discarded: 'outline',
}

const PROVIDER_LABEL: Record<string, string> = {
  kling: 'Kling API',
  comfy_video: 'ComfyUI video',
  comfy_image: 'ComfyUI image',
}

const SELECTABLE: ReviewStatus[] = ['pending_review', 'failed']

function settingsSummary(settings: Record<string, unknown>): string {
  return Object.entries(settings)
    .filter(([k, v]) => v != null && v !== '' && k !== 'workflow_overrides' && k !== 'negative_prompt')
    .map(([k, v]) => `${k}=${String(v)}`)
    .join(' · ')
}

const RequestRow: React.FC<{
  item: ReviewRequestItem
  checked: boolean
  onToggle: (id: string) => void
}> = ({ item, checked, onToggle }) => {
  const queryClient = useQueryClient()
  const [prompt, setPrompt] = useState(item.prompt)
  const editable = item.status === 'pending_review'

  const patchMutation = useMutation({
    mutationFn: () => reviewApi.updateRequest(item.id, { prompt }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['review-requests'] }),
  })
  const discardMutation = useMutation({
    mutationFn: () => reviewApi.discardRequest(item.id),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['review-requests'] }),
  })

  return (
    <div className="flex gap-3 rounded-md border p-3" data-testid="review-row">
      <div className="flex items-start pt-1">
        <Checkbox
          checked={checked}
          disabled={!SELECTABLE.includes(item.status)}
          onCheckedChange={() => onToggle(item.id)}
        />
      </div>
      <img
        src={reviewApi.getThumbnailUrl(item.id)}
        alt=""
        className="h-20 w-20 rounded object-cover bg-muted shrink-0"
        onError={e => { (e.target as HTMLImageElement).style.visibility = 'hidden' }}
      />
      <div className="flex-1 min-w-0 space-y-1.5">
        <div className="flex items-center gap-2 flex-wrap">
          <Badge variant={STATUS_BADGE[item.status]} className="text-xs capitalize">
            {item.status.replace('_', ' ')}
          </Badge>
          <Badge variant="outline" className="text-xs">
            {PROVIDER_LABEL[item.provider] ?? item.provider}
          </Badge>
          <span className="text-xs text-muted-foreground truncate">
            {item.source_image_path.split('/').pop()}
          </span>
        </div>
        <Textarea
          value={prompt}
          onChange={e => setPrompt(e.target.value)}
          onBlur={() => { if (editable && prompt !== item.prompt) patchMutation.mutate() }}
          disabled={!editable}
          rows={3}
          className="text-sm"
        />
        {prompt !== item.original_prompt && (
          <p className="text-xs text-muted-foreground">edited (original kept)</p>
        )}
        <p className="text-xs text-muted-foreground truncate">
          {settingsSummary(item.settings)}
        </p>
        {item.error && <p className="text-xs text-destructive break-words">{item.error}</p>}
      </div>
      {SELECTABLE.includes(item.status) && (
        <Button
          variant="ghost"
          size="icon"
          className="shrink-0"
          title="Discard"
          onClick={() => discardMutation.mutate()}
        >
          <Trash2 className="w-4 h-4" />
        </Button>
      )}
    </div>
  )
}

export const ReviewQueuePage: React.FC = () => {
  const queryClient = useQueryClient()
  const [statusFilter, setStatusFilter] = useState<ReviewStatus | 'all'>('pending_review')
  const [selected, setSelected] = useState<Set<string>>(new Set())

  const { data, isLoading } = useQuery({
    queryKey: ['review-requests', statusFilter],
    queryFn: () =>
      reviewApi.listRequests({
        status: statusFilter === 'all' ? undefined : statusFilter,
        per_page: 200,
      }),
    refetchInterval: 5000,
  })

  const items = useMemo(() => data?.items ?? [], [data])
  const batches = useMemo(() => {
    const map = new Map<string, ReviewRequestItem[]>()
    for (const item of items) {
      const group = map.get(item.batch_id) ?? []
      group.push(item)
      map.set(item.batch_id, group)
    }
    return Array.from(map.entries())
  }, [items])

  const toggle = (id: string) =>
    setSelected(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })

  const toggleBatch = (batchItems: ReviewRequestItem[]) => {
    const selectable = batchItems.filter(i => SELECTABLE.includes(i.status)).map(i => i.id)
    setSelected(prev => {
      const next = new Set(prev)
      const allIn = selectable.every(id => next.has(id))
      selectable.forEach(id => (allIn ? next.delete(id) : next.add(id)))
      return next
    })
  }

  const dispatchMutation = useMutation({
    mutationFn: (ids: string[]) => reviewApi.dispatch(ids),
    onSuccess: () => {
      setSelected(new Set())
      void queryClient.invalidateQueries({ queryKey: ['review-requests'] })
    },
  })

  const selectedIds = Array.from(selected)

  return (
    <div className="flex flex-col h-full">
      <div className="p-4 border-b flex items-center justify-between">
        <h1 className="text-xl font-bold">Review Queue</h1>
        <Tabs value={statusFilter} onValueChange={v => { setStatusFilter(v as ReviewStatus | 'all'); setSelected(new Set()) }}>
          <TabsList>
            <TabsTrigger value="pending_review">Pending</TabsTrigger>
            <TabsTrigger value="dispatched">Dispatched</TabsTrigger>
            <TabsTrigger value="completed">Completed</TabsTrigger>
            <TabsTrigger value="failed">Failed</TabsTrigger>
            <TabsTrigger value="all">All</TabsTrigger>
          </TabsList>
        </Tabs>
      </div>

      <div className="flex-1 overflow-auto p-4 space-y-6">
        {isLoading ? (
          <div className="flex justify-center py-12">
            <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
          </div>
        ) : items.length === 0 ? (
          <p className="text-sm text-muted-foreground text-center py-12">
            No requests{statusFilter !== 'all' ? ` with status "${statusFilter.replace('_', ' ')}"` : ''}.
          </p>
        ) : (
          batches.map(([batchId, batchItems]) => (
            <section key={batchId} className="space-y-2">
              <div className="flex items-center gap-3">
                <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
                  Batch {batchId.slice(0, 8)} ({batchItems.length})
                </h2>
                {batchItems.some(i => SELECTABLE.includes(i.status)) && (
                  <Button variant="outline" size="sm" onClick={() => toggleBatch(batchItems)}>
                    Select all in batch
                  </Button>
                )}
              </div>
              <div className="space-y-2">
                {batchItems.map(item => (
                  <RequestRow
                    key={item.id}
                    item={item}
                    checked={selected.has(item.id)}
                    onToggle={toggle}
                  />
                ))}
              </div>
            </section>
          ))
        )}
      </div>

      {selectedIds.length > 0 && (
        <div className="sticky bottom-0 border-t bg-card p-3 flex items-center justify-between">
          <p className="text-sm text-muted-foreground">{selectedIds.length} selected</p>
          <Button
            onClick={() => dispatchMutation.mutate(selectedIds)}
            disabled={dispatchMutation.isPending}
          >
            {dispatchMutation.isPending ? (
              <><Loader2 className="w-4 h-4 mr-2 animate-spin" />Dispatching...</>
            ) : statusFilter === 'failed' ? (
              <><RotateCcw className="w-4 h-4 mr-2" />Retry selected ({selectedIds.length})</>
            ) : (
              <><Send className="w-4 h-4 mr-2" />Generate selected ({selectedIds.length})</>
            )}
          </Button>
        </div>
      )}
    </div>
  )
}
```

If `@/components/ui/checkbox` or `@/components/ui/textarea` don't exist yet, check `frontend/src/components/ui/` first — the shadcn checkbox dependency (`@radix-ui/react-checkbox`) is already in package.json; add the standard shadcn `checkbox.tsx`/`textarea.tsx` files if missing.

- [ ] **Step 2: Add route and nav item**

In `frontend/src/App.tsx`: add `import { ReviewQueuePage } from '@/pages/ReviewQueuePage'` and, after the gallery route:

```tsx
              <Route path="review" element={<ReviewQueuePage />} />
```

In `frontend/src/components/shared/Layout.tsx`: add `ListChecks` to the lucide-react import and, after the Gallery entry in `navItems`:

```tsx
  { to: '/review', label: 'Review', icon: ListChecks },
```

- [ ] **Step 3: Type-check**

```bash
cd frontend && ./node_modules/.bin/tsc -b --force
```
Expected: exit 0.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/ReviewQueuePage.tsx frontend/src/App.tsx frontend/src/components/shared/Layout.tsx frontend/src/components/ui/
git commit -m "feat(review): Review Queue page with batch grouping and dispatch"
```

---

### Task 9: Close the skip-review path (video generate endpoints + buttons)

**Files:**
- Modify: `frontend/src/components/video/BatchQueuePanel.tsx` (send to queue instead of generating)
- Modify: `frontend/src/api/video.ts` (delete `generate`, `generateBatch`)
- Delete: `frontend/src/hooks/useVideoGenerate.ts`
- Modify: `frontend/src/types/video.ts` (delete `VideoBatchRequest` if now unused)
- Modify: `backend/api/video.py:78-141` (delete `/generate` and `/generate-batch` routes)
- Modify: `backend/models/video.py` (delete `VideoGenerateRequest`, `VideoGenerateResponse`, `VideoBatchItem`, `VideoBatchRequest`, `VideoBatchResponse`; keep `KlingSettings`, `ComfyKlingSettings`, and all status/list/merge/storyboard models)

**Interfaces:**
- Consumes: `reviewApi.createRequests` (Task 7). `VideoService.queue_video`/`queue_video_comfy` remain — they are now called ONLY by the dispatch task.
- Produces: no HTTP path dispatches generation directly anymore.

- [ ] **Step 1: Rewire `BatchQueuePanel` to send to the review queue**

Replace the full contents of `frontend/src/components/video/BatchQueuePanel.tsx` with:

```tsx
import React from 'react'
import { Link } from 'react-router-dom'
import { useMutation } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { ListChecks, Loader2, Send } from 'lucide-react'
import { reviewApi } from '@/api/review'
import type { ReviewItemCreate } from '@/types/review'
import type { KlingSettings, VideoBackend, ComfyKlingSettings } from '@/types/video'

interface QueueItem {
  image_path: string
  prompt?: string
  variation_count: number
}

interface BatchQueuePanelProps {
  items: QueueItem[]
  klingSettings: KlingSettings
  backend?: VideoBackend
  comfySettings?: ComfyKlingSettings
}

export const BatchQueuePanel: React.FC<BatchQueuePanelProps> = ({
  items,
  klingSettings,
  backend = 'api',
  comfySettings,
}) => {
  const [sentCount, setSentCount] = React.useState<number | null>(null)

  const mutation = useMutation({
    mutationFn: (reviewItems: ReviewItemCreate[]) =>
      reviewApi.createRequests({ items: reviewItems }),
  })

  const handleSend = async () => {
    if (items.length === 0) return
    const provider = backend === 'comfy' ? 'comfy_video' : 'kling'
    const settings = backend === 'comfy'
      ? ((comfySettings ?? {}) as Record<string, unknown>)
      : (klingSettings as unknown as Record<string, unknown>)
    const reviewItems: ReviewItemCreate[] = items.flatMap(item =>
      Array.from({ length: item.variation_count }, () => ({
        source_image_path: item.image_path,
        prompt: item.prompt ?? '',
        provider,
        workflow_name: backend === 'comfy' ? 'kling.json' : null,
        settings,
      }))
    )
    const res = await mutation.mutateAsync(reviewItems)
    setSentCount(res.request_ids.length)
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="space-y-0.5">
          <div className="flex items-center gap-2">
            <p className="text-sm font-medium">Send to Review Queue</p>
            <Badge variant="outline" className="text-xs">
              {backend === 'comfy' ? 'ComfyUI' : 'Kling API'}
            </Badge>
          </div>
          <p className="text-xs text-muted-foreground">
            {items.length} image{items.length !== 1 ? 's' : ''} — nothing generates until approved in the queue
          </p>
        </div>
        <Button
          onClick={() => void handleSend()}
          disabled={items.length === 0 || mutation.isPending}
        >
          {mutation.isPending
            ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" />Sending...</>
            : <><Send className="w-4 h-4 mr-2" />Send to Review Queue</>
          }
        </Button>
      </div>

      {mutation.isError && (
        <p className="text-sm text-destructive">Failed to send to review queue. Please try again.</p>
      )}

      {sentCount !== null && (
        <div className="flex items-center gap-2 rounded-md border p-3 text-sm">
          <ListChecks className="w-4 h-4 text-muted-foreground" />
          <span>{sentCount} request{sentCount !== 1 ? 's' : ''} awaiting review.</span>
          <Link to="/review" className="text-primary hover:underline">Open Review Queue</Link>
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Delete the dead frontend generate code**

- `frontend/src/api/video.ts`: delete the `generate:` and `generateBatch:` entries and the now-unused `VideoBatchRequest` import.
- Delete `frontend/src/hooks/useVideoGenerate.ts`.
- `frontend/src/types/video.ts`: delete `VideoBatchRequest` (and `VideoBatchItem` if defined) if nothing else references them (`/usr/bin/grep -rn "VideoBatchRequest" frontend/src`).
- Check remaining users of `useVideoStatus` — `TaskCard` is gone from BatchQueuePanel; keep the hook if `VideoGenerationHistory` or others still use it (`/usr/bin/grep -rn "useVideoStatus" frontend/src`), otherwise delete it too.

- [ ] **Step 3: Type-check the frontend**

```bash
cd frontend && ./node_modules/.bin/tsc -b --force
```
Expected: exit 0. Fix any dangling imports it reports.

- [ ] **Step 4: Delete the backend generate endpoints**

- `backend/api/video.py`: delete the `generate_video` and `generate_video_batch` route functions (lines ~78-141) and their now-unused imports (`VideoGenerateRequest`, `VideoGenerateResponse`, `VideoBatchRequest`, `VideoBatchResponse`, `uuid` if unused elsewhere in the file).
- `backend/models/video.py`: delete `VideoGenerateRequest`, `VideoGenerateResponse`, `VideoBatchItem`, `VideoBatchRequest`, `VideoBatchResponse`. Keep `KlingSettings` and `ComfyKlingSettings` (used by the dispatch task and presets) and everything else.
- Verify nothing else references the deleted names:

```bash
/usr/bin/grep -rn "VideoGenerateRequest\|VideoBatchRequest\|generate_video_batch" backend/ tests/ | /usr/bin/grep -v worktrees
```
Expected: no output.

- [ ] **Step 5: Run backend tests per file**

```bash
pytest tests/test_api_health.py -v
pytest tests/test_api_review.py -v
pytest tests/test_dispatch_task.py -v
```
Expected: all PASS (there are no existing tests for `/video/generate*` — confirmed by grep).

- [ ] **Step 6: Commit**

```bash
git add -A frontend/src backend/api/video.py backend/models/video.py
git commit -m "feat(review)!: remove direct video generate endpoints — all generation via review queue"
```

---

### Task 10: Verification sweep + contract check

**Files:** none new — verification only.

- [ ] **Step 1: Per-file backend test sweep** (throwaway postgres must be up)

```bash
docker compose -f docker-compose.test.yml up -d
for f in tests/database/test_generation_requests_storage.py \
         tests/database/test_alembic_adopt.py \
         tests/database/test_models.py \
         tests/test_dispatch_task.py \
         tests/test_api_review.py \
         tests/test_pipelines_api.py \
         tests/test_pipelines.py \
         tests/test_api_health.py \
         tests/test_api_gallery.py \
         tests/test_api_workspace.py; do
  pytest "$f" -q || echo "FAILED: $f"
done
```
Expected: no `FAILED:` lines.

- [ ] **Step 2: Frontend type-check**

```bash
cd frontend && ./node_modules/.bin/tsc -b --force
```
Expected: exit 0.

- [ ] **Step 3: API contract check**

Run the `api-contract-checker` agent over the changed surface (backend/api/review.py, backend/models/review.py, backend/api/video.py, backend/models/video.py vs frontend/src/api/review.ts, frontend/src/types/review.ts, frontend/src/api/video.ts). Fix any mismatch it reports, re-run tsc + the affected pytest file, and amend/commit.

- [ ] **Step 4: Manual smoke-check (local stack)**

```bash
docker compose build backend worker video_worker frontend
docker compose up -d
docker compose run --rm --no-deps backend alembic upgrade head
docker compose restart backend worker video_worker
```
Then in the browser:
- Workspace: process an image → banner reaches "prompt(s) awaiting review"; NO image generates.
- Review page (`/review`): row appears with thumbnail + editable prompt; edit → persists after reload.
- Select + "Generate selected" → status flips to dispatched; image appears in gallery when ComfyUI finishes and row flips to completed.
- Video page: "Send to Review Queue" → rows appear with provider badge; dispatch a kling + a comfy row.
- Discard a pending row → lands in the "All" filter as discarded.

- [ ] **Step 5: Final commit if the sweep produced fixes**

```bash
git add -A && git commit -m "test(review): phase 2 verification sweep fixes"
```

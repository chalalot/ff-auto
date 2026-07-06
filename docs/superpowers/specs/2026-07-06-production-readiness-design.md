# Production Readiness: Postgres Unification, Prompt Review Queue, Project Workspaces

**Date:** 2026-07-06
**Status:** Approved design, pending implementation plan

## Problem

The production team finds the app inconvenient for real use. Three complaints drive this design:

1. Users cannot review or edit the AI-generated prompt before generation dispatches.
2. There is no way to organize work into per-member project spaces.
3. Analysis/filtering pages are global only; teams need them scoped per project.

Storage today is split: five modules on sqlite files on disk (`evaluations_storage`, `image_logs_storage`, `video_logs_storage`, `runpod_jobs_storage`, `caption_exports_storage`) and one already on Postgres (`runs_posts_storage`). The `evaluations.db` single-file bind mount is a known operational trap (becomes a directory when the host file is missing, causing 500s).

## Decisions (from brainstorming)

- Build all three features as one sequenced roadmap: **migrate storage first**, then review queue, then workspaces.
- **No sqlite fallback.** sqlite code paths are deleted after migration.
- Industry-standard stack: **SQLAlchemy 2.0 + Alembic** on **Postgres 16 in Docker** on the same host. Everything behind `DATABASE_URL` (already supported by `backend/database/db_utils.py`).
- Prompt review is a **batch review screen with a persistent queue**: users select/deselect items; deselected items stay queued indefinitely and can be reopened anytime.
- **All generation goes through the queue.** No skip-review path.
- Identity is **lightweight**: member name picker, no passwords, stored per browser, sent as a request header. Auth can be layered on later without redesign.
- A project is a **DB-level grouping**, not a physical folder. Files stay where pipelines write them; project views are filtered queries.
- Project-scoped entities: generations (image + video), source assets (uploads, music), evaluations & analysis records, workflow/prompt presets.

## Phase 1 — Postgres unification (week 1–2, nothing user-visible)

### Infrastructure

- Add `postgres:16` service to docker-compose: named volume, healthcheck, `depends_on` from API and Celery worker containers.
- Connection via `DATABASE_URL` resolved by existing `db_utils.py`.
- Remove the `evaluations.db` bind mount entirely.

### Stack

- SQLAlchemy 2.0 declarative models in `backend/database/models.py`, typed columns.
- Alembic owns the schema. Versioned migrations replace all create-if-missing DDL. Every later schema change (phases 2–3) is an Alembic migration.
- Session management via FastAPI dependency injection with a connection pool; Celery tasks use their own session scope.

### Storage layer

- Port the five sqlite modules to SQLAlchemy sessions. **Public function signatures unchanged** — services and API layers do not change in this phase.
- Also port `runs_posts_storage.py` (currently raw psycopg2) to SQLAlchemy, so the codebase has exactly one DB access pattern.

### Data migration

- One-off idempotent script `backend/scripts/migrate_sqlite_to_pg.py`: reads each `.db` file, inserts with `ON CONFLICT DO NOTHING`, prints per-table before/after row counts.
- Old sqlite files remain on disk untouched as the rollback path (read-only artifact, not a code fallback).

### Exit criteria

- All existing pages (analysis, archive, evaluations, gallery) behave identically against Postgres.
- Migration verified by row-count comparison.
- sqlite code paths deleted.

## Phase 2 — Prompt review queue (week 2–3)

### Data model (one Alembic migration)

Table `generation_requests`:

| Column | Notes |
|---|---|
| `id` | UUID PK |
| `batch_id` | groups items generated together |
| `source_image_path` | input image |
| `original_prompt` | as produced by the storyboard workflow (immutable) |
| `prompt` | editable working copy |
| `provider` | e.g. `kling`, `comfyui` — provider-agnostic row shape for future Higgsfield/Dreamania |
| `workflow_name` | ComfyUI graph name where applicable |
| `settings` | JSONB provider settings |
| `status` | `pending_review → approved → dispatched → completed \| failed`, plus `discarded` |
| `execution_id`, `result_path` | filled after dispatch/completion |
| `error` | failure detail for `failed` rows |
| `created_at`, `updated_at` | |

Keeping both `original_prompt` and `prompt` enables measuring how often humans correct AI prompts.

### Flow change

Prompt generation (`VideoStoryboardWorkflow` output path) stops dispatching. It writes `generation_requests` rows with `status=pending_review` and returns. Nothing generates until a human approves. Deselected items stay `pending_review` indefinitely.

### API

- `GET /review/requests` — filter by status/batch, paginated.
- `PATCH /review/requests/{id}` — edit prompt/settings (only while `pending_review`).
- `POST /review/dispatch` — body: list of IDs; approves and queues Celery tasks.
- `DELETE /review/requests/{id}` — sets `discarded`.

### UI

New **Review Queue** page: items grouped by batch; each row shows thumbnail, editable prompt textarea, settings summary, checkbox. "Select all in batch", sticky **Generate selected (n)** button, status chips. Existing generate buttons across the app become "Send to review queue".

## Phase 3 — Projects & members (week 3–4)

### Data model (Alembic migrations)

- `members` — `id`, `name` (unique), `created_at`. No passwords.
- `projects` — `id`, `name`, `description`, `owner_member_id`, `created_at`, `archived_at` (nullable).
- `project_members` — many-to-many join.
- `workflow_presets` — `id`, `project_id`, `name`, `provider`, `workflow_name`, `settings` JSONB, `persona`.
- Scoping columns added to `generation_requests`, `image_logs`, `video_logs`, `evaluations`, upload/asset records: nullable `project_id`, nullable `created_by_member_id`. Nullable means pre-existing data keeps working and appears in an "Unassigned" bucket; an "assign to project" action allows gradual adoption. No backfill required.

### Identity UX

First visit: member picker (pick or type name), saved in browser, sent as a header on every API call; backend resolves or auto-creates the member. Top-nav **active project** selector. Everything created afterward is stamped with member ID and active project automatically.

### Project pages

- Projects list page → per-project workspace with tabs: Gallery, Review Queue, Analysis, Evaluations, Assets, Presets.
- Tabs reuse the existing global pages (including the current analysis page's status/date/pagination filters) parameterized by `project_id` — not new page implementations.
- Existing global pages remain as an "All projects" view with a project-name column.

## Error handling

- **Startup:** API and worker fail fast with a clear message if Postgres is unreachable or migrations are not at head (`alembic upgrade head` check at boot).
- **Dispatch:** a Celery dispatch failure affects only that item (`failed` + stored error); the rest of the selection proceeds. Failed items show a retry button (retry = back to `approved`, re-dispatch).
- **Concurrency:** dispatch is idempotent per row (`WHERE status='pending_review'` guard), so double-clicks or two members approving the same item dispatch once.

## Testing

Constraints from repo history: run tests in a disposable container (never against the live container's mounted data dirs); verify per test file, not the full suite (known pollution failures).

- **Phase 1:** each ported storage module tested against a throwaway Postgres (`docker-compose.test.yml`); migration script tested with fixture sqlite files, asserting row counts.
- **Phase 2:** state-machine tests (illegal transitions rejected), dispatch-only-selected, idempotent dispatch.
- **Phase 3:** scoping tests — project A queries never return project B rows; unassigned-data visibility.
- Every phase ends with an `api-contract-checker` run (each phase touches FastAPI models and the TS client).

## Out of scope

- Real authentication (passwords/SSO) — lightweight identity only, designed to not block adding auth later.
- Cloud hosting (GCP Cloud SQL/GCS) — `DATABASE_URL` keeps this a config change later.
- Physical project folders / file moves — DB grouping only.
- New generation providers (Higgsfield, Dreamania) — the `provider` + `settings` JSONB shape in `generation_requests` is designed to accommodate them, but integration is separate work.

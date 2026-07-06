# Phase 1: Postgres Unification — Implementation Plan

> **Format note:** This plan is a *contract document*, adapted from superpowers:writing-plans for a strong coding agent with live repo access. Tasks specify exact files, interfaces (signatures/DDL), behaviors, edge cases, and named test cases — but not full code bodies. The executor writes code against the live repo, TDD per task (test first → fail → implement → pass → commit), one commit per task.

**Goal:** Move all six storage modules onto Postgres 16 (SQLAlchemy 2.0 + Alembic), migrate existing data, delete sqlite.

**Architecture:** One SQLAlchemy engine/session layer shared by FastAPI (dependency-injected sessions) and Celery (scoped sessions). Alembic owns schema. Storage classes keep their exact public interfaces so services/API layers are untouched this phase.

**Tech stack:** Postgres 16 (Docker), SQLAlchemy 2.0, Alembic, psycopg2-binary (already present).

## Global constraints

- `DATABASE_URL` is the only connection source (resolved via existing `backend/database/db_utils.py` priority chain). No sqlite fallback anywhere.
- Public method signatures of all six storage classes (`EvaluationsStorage`, `ImageLogsStorage`, `VideoLogsStorage`, `RunpodJobsStorage`, `CaptionExportsStorage`, `RunsPostsStorage`) must not change: same names, params, return shapes (dicts/lists as today).
- **Never test against the live containers or mounted data dirs** — all tests run against the throwaway stack in `docker-compose.test.yml` (memory: fixtures polluted real data before).
- **Verify per test file**, not full `pytest tests/` (known ~24 pre-existing pollution failures).
- Frontend type checks: raw `./node_modules/.bin/tsc -b --force`, never through RTK.
- Data reality: only `image_logs.db` and `evaluations.db` are bind-mounted. `video_logs.db` (and any runpod/caption dbs) live **inside container filesystems** — the migration runbook must `docker cp` them out of the *running* containers before anything is rebuilt or restarted.

## Task 1 — Postgres service + test stack + deps

**Files:**
- Modify: `docker-compose.yml`, `requirements.txt`, `.env.example` (create if missing)
- Create: `docker-compose.test.yml`

**Contract:**
- `requirements.txt` += `sqlalchemy>=2.0`, `alembic>=1.13`.
- `docker-compose.yml`: new `postgres` service — `postgres:16`, named volume `pgdata:/var/lib/postgresql/data`, healthcheck `pg_isready -U $POSTGRES_USER`, on `ff-shared-net`, `restart: unless-stopped`, credentials from `.env`. `backend`, `worker`, `video_worker` get `depends_on: postgres: condition: service_healthy` and `DATABASE_URL=postgresql://...@postgres:5432/ffauto` via env.
- `docker-compose.test.yml`: standalone throwaway postgres on a random host port + tmpfs volume, no external network, no bind mounts to real data.
- Do **not** remove the `.db` bind mounts yet (Task 8 does, after data migration).

**Verify:** `docker compose up -d postgres` → healthy; `python -m backend.database.db_utils` (its `__main__` connection check) prints connection success with `DATABASE_URL` set.

**Commit:** `feat(infra): postgres 16 service, test stack, sqlalchemy+alembic deps`

## Task 2 — SQLAlchemy foundation + Alembic baseline

**Files:**
- Create: `backend/database/engine.py`, `backend/database/models.py`, `alembic.ini`, `backend/database/alembic/` (env.py + first migration)
- Test: `tests/database/test_models.py`

**Interfaces (produces — all later tasks consume these):**
- `engine.py`: `get_engine() -> Engine` (singleton, pooled, from `get_postgres_connection_string()`), `SessionLocal` factory, `get_db()` FastAPI dependency (yield session, close), `session_scope()` contextmanager for Celery/scripts (commit on success, rollback on exception).
- `models.py`: declarative `Base`; models `Evaluation`, `ImageLog`, `VideoLog`, `RunpodJob`, `CaptionExport`, `Run`, `Post` mirroring the existing DDL exactly (source of truth: `CREATE TABLE` strings in the six current modules — evaluations_storage.py:25, runpod_jobs_storage.py:24, video_logs_storage.py:38, image_logs_storage.py:44, caption_exports_storage.py:22, runs_posts_storage.py:67+82).
- Type mapping rules: sqlite `INTEGER PRIMARY KEY AUTOINCREMENT` → `Integer` PK with identity; `TIMESTAMP DEFAULT CURRENT_TIMESTAMP` → `DateTime(timezone=True), server_default=func.now()`; text-JSON columns (e.g. `evaluations.scores_json`) stay `Text` with same defaults — JSONB conversion is out of scope (signature compatibility). `runs`/`posts` keep their existing `JSONB`, `TEXT[]`, FK `ON DELETE CASCADE`, and the two indexes (`idx_posts_run_id`, `idx_runs_created_at`); add unique constraint on `runpod_jobs.job_id`.
- Alembic: `env.py` reads URL from `db_utils.get_postgres_connection_string()`; migration 0001 creates all seven tables.

**Edge cases:** engine creation must not connect at import time (Celery forks); `session_scope` must rollback on exception, always close.

**Tests** (against test stack): `test_migration_creates_all_tables` (alembic upgrade head → inspect table names), `test_session_scope_rolls_back_on_error`, `test_models_roundtrip` (insert+read one row per model).

**Verify:** `alembic upgrade head` clean on empty test DB; `pytest tests/database/test_models.py -v` green.

**Commit:** `feat(db): sqlalchemy engine/session layer, models, alembic baseline`

## Task 3 — Port EvaluationsStorage and ImageLogsStorage

**Files:**
- Modify: `backend/database/evaluations_storage.py`, `backend/database/image_logs_storage.py`
- Test: `tests/database/test_evaluations_storage.py`, `tests/database/test_image_logs_storage.py`

**Contract:** Reimplement every public method on SQLAlchemy sessions (`session_scope()` internally; constructors lose `db_path` param but keep accepting/ignoring it this phase so call sites don't break — remove in Task 9). Return shapes byte-identical to today (same dict keys, same status strings, timestamps serialized the same way current API responses expect). Delete `_init_db`/`_migrate_table` (Alembic owns schema). Before coding, read each module's current method list and the call sites in `backend/services/` + `backend/api/` to pin the exact return shapes.

**Tests:** per module — insert/list/filter/status-update round trips; `test_list_filters_match_legacy_semantics` (e.g. evaluations `limit`, `media_path` filters; image_logs status transitions); one test asserting dict keys of returned rows equal legacy keys.

**Verify:** `pytest tests/database/test_evaluations_storage.py -v` and `..._image_logs_...` green; then run the analysis + gallery API tests file(s) that already exist for these endpoints, per-file.

**Commit:** `refactor(db): evaluations + image_logs storage on sqlalchemy/postgres`

## Task 4 — Port VideoLogsStorage and RunpodJobsStorage

Same contract pattern as Task 3.

**Files:** modify both modules; create `tests/database/test_video_logs_storage.py`, `tests/database/test_runpod_jobs_storage.py`.

**Module-specific:** video_logs — `batch_id`/`filename_id` semantics preserved, status defaults `'pending'`; runpod_jobs — `job_id` uniqueness now DB-enforced: upsert-style `insert` must handle conflict the way current code's callers expect (read `backend/services`/`backend/tasks.py` call sites first).

**Commit:** `refactor(db): video_logs + runpod_jobs storage on sqlalchemy/postgres`

## Task 5 — Port CaptionExportsStorage and RunsPostsStorage

Same contract pattern.

**Files:** modify both modules; create `tests/database/test_caption_exports_storage.py`, `tests/database/test_runs_posts_storage.py`.

**Module-specific:** runs_posts is already Postgres (raw psycopg2) — port to SQLAlchemy sessions, no data migration needed for it; preserve JSONB/`TEXT[]` round-tripping (lists/dicts in and out, not strings).

**Commit:** `refactor(db): caption_exports + runs_posts storage on sqlalchemy`

## Task 6 — Data migration script

**Files:**
- Create: `backend/scripts/migrate_sqlite_to_pg.py`, `tests/database/test_migrate_sqlite_to_pg.py`

**Contract:** CLI: `python -m backend.scripts.migrate_sqlite_to_pg --sqlite-dir <dir> [--dry-run]`. For each of the five sqlite files found in `--sqlite-dir` (`evaluations.db`, `image_logs.db`, `video_logs.db`, + runpod/caption dbs if present): read all rows, bulk-insert via SQLAlchemy Core with `ON CONFLICT DO NOTHING` keyed on PK (and `runpod_jobs.job_id`), preserving original integer IDs.
- **Sequence fix (classic gotcha):** after copying explicit PKs, `setval` each table's identity sequence to `max(id)`.
- Timestamp parsing: sqlite `CURRENT_TIMESTAMP` strings (`YYYY-MM-DD HH:MM:SS`) → aware datetimes (assume UTC).
- Missing file → warn and skip, don't fail. Output: per-table `sqlite rows / pg rows before / pg rows after`. Idempotent: second run inserts 0.

**Tests:** fixture sqlite files built in-test → run migration twice → assert counts, ID preservation, sequence continues correctly on next insert, timestamp parse.

**Verify:** `pytest tests/database/test_migrate_sqlite_to_pg.py -v` green.

**Commit:** `feat(db): idempotent sqlite→postgres data migration script`

## Task 7 — Startup fail-fast + wiring

**Files:**
- Modify: `backend/main.py`, `backend/celery_app.py`
- Test: `tests/database/test_startup_checks.py`

**Contract:** On API startup (lifespan) and Celery worker init: check DB reachable AND `alembic current == head`; if not, exit with a one-line actionable error naming `DATABASE_URL` and `alembic upgrade head`. No auto-migrate in app process (migrations run explicitly).

**Tests:** unreachable URL → startup raises with clear message; head-mismatch simulated → raises.

**Commit:** `feat(db): fail-fast startup checks for connection and migration state`

## Task 8 — Production cutover (runbook + compose cleanup)

**Files:**
- Modify: `docker-compose.yml`
- Create: `docs/superpowers/plans/phase1-cutover-runbook.md`

**Runbook (ordered, in the doc):**
1. `docker cp` container-internal db files out of the **running** containers (`video_logs.db` from `video_worker`/`backend`, any runpod/caption dbs) into a host `./sqlite-backup/` dir together with the bind-mounted `image_logs.db`, `evaluations.db`. **Do this before any rebuild/restart.**
2. `docker compose up -d postgres` → `alembic upgrade head` → run migration script against `./sqlite-backup/` → verify row counts.
3. Remove `.db` bind mounts from `backend` + `worker` in compose; deploy new images; smoke-check analysis/archive/evaluations/gallery pages.
4. Rollback path: old sqlite files remain in `./sqlite-backup/` untouched; revert compose + image tag.

**Commit:** `chore(infra): remove sqlite bind mounts, add phase1 cutover runbook`

## Task 9 — Delete sqlite remnants + final sweep

**Files:**
- Modify: all six storage modules (drop ignored `db_path` params), their call sites, `Dockerfile.backend` if it references `.db` files
- Test: existing per-module test files re-run

**Contract:** `grep -rn "sqlite3" backend/` → zero hits; `grep -rn "db_path" backend/` → zero hits. Constructor signature change is the one allowed break — update every call site in the same commit.

**Verify:** each `tests/database/test_*.py` green per-file; API test files for analysis/evaluations/archive green per-file; disposable-stack smoke: bring up full `docker-compose.test.yml`-based stack variant and hit `/analysis`, `/evaluations`, `/archive/list` manually.

**Commit:** `refactor(db)!: remove sqlite code paths; postgres only`

## Self-review results

- Spec coverage: infra ✔ (T1), stack ✔ (T2), 6 modules ✔ (T3–5), migration ✔ (T6), fail-fast ✔ (T7), mount removal ✔ (T8), sqlite deletion ✔ (T9), exit criteria ✔ (T8 runbook + T9 verify).
- Placeholder scan: none — every task names exact files, behaviors, edge cases, test cases.
- Phases 2–3 deliberately not planned yet (just-in-time rule): their plans consume this phase's real model/session names after merge.

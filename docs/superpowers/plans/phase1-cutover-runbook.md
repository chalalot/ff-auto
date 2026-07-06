# Phase 1 Cutover Runbook — sqlite → Postgres

**Run by a human, in order. Do not skip steps.** The app code on this branch
only speaks Postgres; deploying it without completing steps 1–2 loses access
to historical data until the migration is run.

Nothing here deletes sqlite data. The old `.db` files are the rollback path
and remain untouched in `./sqlite-backup/`.

## Prerequisites

- This branch's code checked out on the production host (not yet deployed).
- `.env` contains `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` and a
  `DATABASE_URL` pointing at the compose `postgres` service
  (see `.env.example`).
- The **old** stack (backend / worker / video_worker) is still **running** —
  step 1 copies files out of the live containers.

## 1. Back up every sqlite file — BEFORE any rebuild or restart

`video_logs.db` (and any runpod/caption dbs written with a custom path) live
**inside the container filesystems**, not in bind mounts. A rebuild/restart
destroys them. Copy everything out of the *running* containers first:

```bash
mkdir -p ./sqlite-backup

# Bind-mounted files (host-side already, but snapshot them together):
cp ./image_logs.db   ./sqlite-backup/
cp ./evaluations.db  ./sqlite-backup/

# Container-internal files. VIDEO_DIR defaults to raw_video/ inside the
# container; check both workers and the backend:
docker cp ff-auto-video_worker-1:/app/raw_video/video_logs.db ./sqlite-backup/video_logs.db \
  || echo "no video_logs.db in video_worker"
docker cp ff-auto-backend-1:/app/raw_video/video_logs.db ./sqlite-backup/video_logs.db \
  || echo "no video_logs.db in backend"

# Belt-and-braces: list any other .db files hiding in the containers and copy
# anything found (runpod_jobs / caption_exports historically share
# image_logs.db, but custom db_path deployments may differ):
for c in ff-auto-backend-1 ff-auto-worker-1 ff-auto-video_worker-1; do
  echo "--- $c ---"
  docker exec "$c" sh -c 'find /app -maxdepth 3 -name "*.db" -not -path "*/node_modules/*" 2>/dev/null'
done

# Verify the backups are readable sqlite files:
for f in ./sqlite-backup/*.db; do
  sqlite3 "$f" "SELECT 'OK: ' || '$f'" || echo "CORRUPT: $f"
done
```

## 2. Bring up Postgres, migrate schema, copy data

```bash
# Start ONLY the postgres service (does not touch the running app):
docker compose up -d postgres

# Apply the schema (from the repo checkout, DATABASE_URL pointing at the
# published postgres port or run inside a one-off container on ff-shared-net):
alembic upgrade head

# Copy the data (idempotent; re-running is safe):
python -m scripts.migrate_sqlite_to_pg --sqlite-dir ./sqlite-backup

# The script prints per-table:  sqlite rows / pg before / pg after.
# VERIFY: for each table, pg_after == sqlite rows (or pg_before + new rows).
# Spot-check a couple of rows:
#   SELECT count(*) FROM image_logs;  SELECT count(*) FROM evaluations;
```

Row-count verification is the exit criterion — do not proceed until the
counts match the script's reported sqlite rows.

## 3. Deploy the new images

The `.db` bind mounts are already removed from `docker-compose.yml` on this
branch, and `backend`/`worker`/`video_worker` now receive `DATABASE_URL` and
depend on a healthy `postgres`.

```bash
docker compose build backend worker video_worker frontend
docker compose up -d
```

Startup is fail-fast: if `DATABASE_URL` is wrong or migrations are not at
head, the API and workers exit immediately with a one-line error saying so.

**Smoke-check** (all previously working pages must behave identically):

- `/health` returns `{"status": "ok"}`
- Analysis page: summary counts + evaluation badges populated
- Evaluations: history list shows migrated evaluations
- Archive: `/api/archive/...` listing works
- Gallery: images show prompt/persona metadata (comes from `image_logs`)
- Workspace: executions history, runpod jobs list, caption export history

## 4. Rollback path

The old sqlite files in `./sqlite-backup/` are untouched read-only artifacts.

```bash
git checkout <previous-release-tag-or-commit>   # compose still has the .db mounts
cp ./sqlite-backup/image_logs.db ./image_logs.db     # only if the originals were moved
cp ./sqlite-backup/evaluations.db ./evaluations.db
docker compose build backend worker video_worker
docker compose up -d
```

Postgres keeps whatever was migrated; it is simply unused by the old images.
Nothing in the rollback deletes or rewrites the sqlite files.

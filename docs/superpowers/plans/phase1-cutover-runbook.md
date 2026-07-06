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
  (see `.env.example`). **`DATABASE_URL` is mandatory** — compose no longer
  injects a default; a service started without it exits immediately with an
  actionable error.
- If the old deployment used the runs/posts Postgres (legacy `DB_HOST` /
  `DB_USER` / ... values in `.env`), note that DB's URL — step 2 copies
  runs/posts out of it. Do not delete those env vars until after cutover.
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

The postgres service publishes no host port, so schema and data migration run
in **one-off containers on the compose network** (the backend image ships
`alembic.ini` and `scripts/`). This never touches the running app services.

```bash
# Start ONLY the postgres service (does not touch the running app):
docker compose up -d postgres

# Build the new backend image once (used only for the one-off runs below;
# the live containers keep running on the old image):
docker compose build backend

# Apply the schema:
docker compose run --rm --no-deps backend alembic upgrade head

# Copy the sqlite data (idempotent; re-running is safe).
# Add --source-database-url with the LEGACY runs/posts Postgres URL (built
# from the old DB_HOST/DB_USER/DB_PASSWORD/DB_NAME values in .env) so
# historical campaign runs/posts are copied too — without it they are NOT
# migrated and the script warns loudly:
docker compose run --rm --no-deps \
  -v "$(pwd)/sqlite-backup:/app/sqlite-backup:ro" \
  backend python -m scripts.migrate_sqlite_to_pg \
    --sqlite-dir /app/sqlite-backup \
    --source-database-url "postgresql://<DB_USER>:<DB_PASSWORD>@<DB_HOST>:<DB_PORT>/<DB_NAME>"

# The script prints per-table:  source rows / pg before / pg after.
# VERIFY: for each table, pg_after == source rows (or pg_before + new rows).
# Spot-check via psql inside the postgres container:
docker compose exec postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  -c "SELECT count(*) FROM image_logs;" \
  -c "SELECT count(*) FROM evaluations;" \
  -c "SELECT count(*) FROM runs;" \
  -c "SELECT count(*) FROM posts;"
```

Row-count verification is the exit criterion — do not proceed until the
counts (including **runs** and **posts**) match the script's reported source
rows.

> Alternative: if you skip `--source-database-url` because the new stack
> should keep using the existing legacy Postgres directly, point
> `DATABASE_URL` at that DB instead — `alembic upgrade head` adopts it
> (the baseline skips tables that already exist) and then only the sqlite
> copy is needed.

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
- Runs/campaigns: historical runs list and their posts (incl. post versions)
  are present — this is the `runs`/`posts` data copied in step 2

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

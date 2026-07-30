# Deploy (GCP)

Run from the repo directory on the GCP host. The VM tracks a branch
explicitly — nothing is merged to `main` — so check out the branch you mean.

## Steady-state deploy

Two facts set the order below:

- The **frontend bundle is baked into its image** (`Dockerfile.frontend` runs
  `npm run build`), so a UI change needs `--build`, not `restart`.
- **nginx resolves `backend` once at startup and pins the IP.** Recreating the
  backend under a running frontend leaves it proxying to a dead address, and
  every `/api` call 502s — which looks exactly like an empty database. So the
  frontend is always recreated *last*.

```bash
# 1. Preflight — the tree must be clean or the pull aborts.
git status --short
docker compose ps
```

The usual reason step 1 is dirty: the UI writes `workflows/*.json` back through
the bind mount as `root:600`. `prompts/workflow_registry.json` (workflow tags and
node bindings) is written the same way whenever tags are edited on this host.
Clear both first — keep the registry's local edits if the tags here are the ones
you want, otherwise take the incoming version:

```bash
docker compose exec -T -u 0 backend chown -R 1000:1000 /app/workflows /app/prompts
git checkout -- workflows/ || git stash push workflows/
git checkout -- prompts/workflow_registry.json   # or: git stash push prompts/
```

```bash
# 2. Update the code.
git fetch origin
git checkout <branch>
git pull --ff-only origin <branch>
git log --oneline -3

# 3. Build first, while the old stack keeps serving.
docker compose build

# 4. Migrate with a throwaway container, before the new backend boots.
#    The backend has a boot guard that crash-loops when the code expects a
#    revision the DB doesn't have; `run --rm` applies it without handing the
#    live backend over to a container that might then fail to start.
docker compose run --rm backend alembic upgrade head

# 5. Roll the services — frontend LAST, and --no-deps so it doesn't drag the
#    backend into another recreate and re-break the pinned upstream.
docker compose up -d backend worker video_worker
docker compose up -d --no-deps frontend
```

## Verify

```bash
docker compose ps                     # 5 services up, none restarting
docker compose logs --tail=40 backend

# The running image is actually the one just built. Images bake in backend/, so
# a failed or skipped build silently keeps the old behaviour while the working
# tree looks correct — the timestamp should be minutes old, not days.
docker inspect --format '{{.Created}}' "$(docker compose images -q backend)"

# And the new code is really in there — grep something the deploy introduced:
docker compose exec -T backend grep -c '<a symbol from this deploy>' backend/api/<file>.py

# nginx is talking to a live backend, not a pinned dead IP.
curl -s -o /dev/null -w '%{http_code}\n' 'localhost:3000/api/review/requests?per_page=1'

# The browser will get the new bundle (hash should change across deploys).
curl -s localhost:3000/ | grep -o 'assets/index-[^"]*\.js'
```

## Rollback

```bash
git checkout <previous-sha>
docker compose build
docker compose up -d backend worker video_worker
docker compose up -d --no-deps frontend
```

A rollback does **not** undo migrations. If the deploy applied one, roll the
schema back explicitly (`alembic downgrade <rev>`) before starting the old
backend, or its boot guard will refuse the newer revision.

## Data

All application data lives in Postgres, in the `pgdata` named volume — not in
host files. `docker compose down -v` destroys it; plain `down` does not.

```bash
# Back up before any risky deploy.
docker compose exec -T postgres pg_dump -U ffauto ffauto | gzip > "backup-$(date +%F).sql.gz"
```

The SQLite files (`image_logs.db`, `evaluations.db`) are **legacy** — superseded
by Postgres and no longer bind-mounted or read by the app. See
`scripts/migrate_sqlite_to_pg.py` for the one-time import that retired them.

## Notes

- `ff-shared-net` is an external network. If it's missing:
  `docker network create ff-shared-net`, then attach redis with
  `docker network connect ff-shared-net global-redis` — the workers reach the
  broker by that hostname.
- Leave the ports at their defaults on the VM (3000/8000). `FRONTEND_PORT` /
  `BACKEND_PORT` in `.env` exist for local dev, where another app owns 3000/5000.
- Don't pass `-f docker-compose.dev.yml` here. That override is for development:
  it swaps in `uvicorn --reload` and bind-mounts the source.
- `docker compose build` runs `npm ci && npm run build` inside the frontend
  image. That's the memory-hungry step — a bare `Killed` is the VM running out
  of RAM, not a code error.
</content>
</invoke>

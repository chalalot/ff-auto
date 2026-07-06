# Deploy (GCP)

Run from the repo directory on the GCP host.

## Steady-state deploy

Once `evaluations.db` is bind-mounted (see one-time migration below), all
SQLite data (`image_logs.db`, `evaluations.db`) lives on the host and survives
rebuilds. A normal deploy is just:

```bash
git pull
docker compose up -d --build
```

## One-time migration: persist evaluations.db

Do this **once**, the first time you deploy the commit that adds the
`evaluations.db` bind mount. Before this, `evaluations.db` lived only in the
container's writable layer and was lost on every rebuild.

The rule that matters: **rescue the live DB to the host BEFORE the rebuild
recreates the container.** Recreating the container discards its writable layer
(and the data) — so the host copy must exist first.

```bash
# 0. Be on the deploy branch
git fetch && git checkout z-image-gallery-updates

# 1. RESCUE: copy the live DB out of the running container to the host.
#    Creates ./evaluations.db with your real data, before anything recreates
#    the container. (*.db is gitignored, so it won't collide with git pull.)
docker compose cp backend:/app/evaluations.db ./evaluations.db

# 2. Pull the new code + compose (which adds the bind mount)
git pull

# 3. Rebuild + restart. The bind mount now maps the rescued host file in.
docker compose up -d --build

# 4. Verify the rows survived
docker compose exec backend python3 -c "import sqlite3; print('evaluations rows:', sqlite3.connect('/app/evaluations.db').execute('select count(*) from evaluations').fetchone()[0])"
```

If step 4 shows `0` unexpectedly, **stop** — do not run more rebuilds. The host
file is now the source of truth; the old container layer may still be
recoverable only if it has not been pruned.

## Notes

- Persisted on the host via bind mounts (see `docker-compose.yml`):
  `image_logs.db`, `evaluations.db`. Back these up periodically.
- For a guaranteed-clean snapshot in step 1 you may `docker compose stop backend`
  first, but it is usually unnecessary — SQLite's on-disk file is consistent
  between transactions and evaluations are written synchronously/infrequently.

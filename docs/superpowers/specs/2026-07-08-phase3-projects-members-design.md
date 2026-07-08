# Phase 3 — Projects & Members Design

**Date:** 2026-07-08
**Parent roadmap:** `docs/superpowers/specs/2026-07-06-production-readiness-design.md` (Phase 3 section)
**Status:** Approved

## Goal

Lightweight identity and project grouping: every teammate picks a name once, every piece of
generated content is stamped with who made it and which project it belongs to, and each project
gets its own workspace view over the existing pages. No passwords, no auth — designed so real
auth can be added later without schema changes.

## Scope decisions (user-confirmed)

- **One plan**, backend-first tasks, single deploy — same execution style as Phase 2.
- **Per-project workflow presets: deferred.** The `workflow_presets` table, its API, and the
  Presets tab are out of scope for Phase 3.
- **Scoping columns go on all content tables:** `generation_requests`, `image_logs`,
  `video_logs`, `evaluations`, `runs`, `posts`, `caption_exports`. `runpod_jobs` (pure infra)
  stays global.
- **Assets tab: included.** Requires a new `uploads` table stamped at upload time.

## Grounding facts (verified in code)

- Gallery (`backend/services/gallery.py`) lists images by **scanning status directories** on
  disk — it is not DB-driven. Project filtering must join the directory listing against
  `image_logs.result_image_path` filenames.
- Uploads (`backend/api/workspace.py` `/upload`, `/ref-images/upload`) write files into
  PROCESSED_DIR with **no DB row**. The Assets tab therefore needs a new `uploads` table;
  pre-existing files have no row and simply do not appear in Assets (they remain usable
  everywhere else).
- `backend/api/deps.py` is the DI seam — identity resolution lives there as a FastAPI
  dependency.
- Phase 2's review queue means all image/video generation already flows through
  `generation_requests`; completion hooks are the single place worker-side stamping happens.

## Identity propagation approach

**Chosen: HTTP headers + FastAPI dependency (Approach A).**

- Frontend sends `X-Member-Name` and `X-Project-Id` on every API call.
- A `get_identity` dependency in `deps.py` resolves the member name to an id, **auto-creating
  the member on first sight**, and returns `Identity(member_id: Optional[str], project_id:
  Optional[str])`. Both headers optional — missing headers never break any endpoint.
- Row-creating endpoints stamp `project_id` / `created_by_member_id` at ingress.
- Celery workers never see headers: completion hooks copy `project_id` /
  `created_by_member_id` from the `generation_requests` row onto the `image_logs` /
  `video_logs` rows they write.

Rejected: cookie/session state (more moving parts, no benefit without real auth); query params
on every call (noisy, easy to miss endpoints).

## Data model (Alembic migration 0003)

New tables:

- `members` — `id` (text PK), `name` (text, unique, not null), `created_at`. No passwords.
- `projects` — `id` (text PK), `name` (not null), `description`, `owner_member_id`
  (FK → members, nullable), `created_at`, `archived_at` (nullable).
- `project_members` — `project_id` FK, `member_id` FK, composite PK.
- `uploads` — `id` (text PK), `filename`, `path`, `kind` (`input` | `ref`), `project_id`
  (nullable FK), `created_by_member_id` (nullable FK), `created_at`. Written at upload time
  only.

Scoping columns added to `generation_requests`, `image_logs`, `video_logs`, `evaluations`,
`runs`, `posts`, `caption_exports`:

- `project_id` — nullable FK → `projects.id`, indexed.
- `created_by_member_id` — nullable FK → `members.id`.

Nullable means all pre-existing rows keep working and appear in an **"Unassigned"** bucket.
No backfill. FKs use `ON DELETE SET NULL` so deleting a project/member never destroys content.

## Identity UX

- **Member picker:** first visit shows a blocking modal — pick an existing member from the
  list or type a new name. Choice saved in localStorage; never asked again in that browser.
  Changeable later from the same UI (e.g. clicking the member name).
- **Active project selector:** top-nav dropdown listing non-archived projects plus
  "No project". Selection saved in localStorage and sent as `X-Project-Id`.
- Everything created afterward is stamped automatically. Stamping happens only on
  **create paths**: upload, image process/dispatch, review-queue request creation, evaluation
  trigger, campaign run creation, caption export. Read endpoints ignore identity.

## APIs

New routers:

- `GET /api/members` — list members.
- `POST /api/members` — create (also implicit via `X-Member-Name` auto-create).
- `GET /api/projects` — list (with `include_archived` flag).
- `POST /api/projects` — create (owner = calling member).
- `PATCH /api/projects/{id}` — rename / edit description / archive (`archived_at`).
- `POST /api/projects/{id}/members` / `DELETE /api/projects/{id}/members/{member_id}` —
  membership management.
- `POST /api/projects/{id}/assign` — bulk assign existing rows: body `{table, ids}` where
  `table` ∈ the seven scoped tables; sets `project_id` on those rows. Enables gradual adoption
  of pre-existing data.
- `GET /api/uploads` — list upload rows, `project_id` filterable.

Existing list endpoints gain an optional `project_id` query param accepting a project id or
the literal `unassigned` (NULL rows only). Applies to: review-queue list, gallery list,
analysis list, evaluations list. Gallery implements this by fetching the project's
`image_logs.result_image_path` filenames and filtering its directory scan against them.

## Frontend

- `MemberPickerModal` — blocking on first visit, localStorage-backed.
- `ProjectSelector` — in `Layout.tsx` top area; feeds `X-Project-Id`.
- API client (axios/fetch layer) injects both headers globally.
- `ProjectsPage` — list, create, archive; each project links to `/projects/:id`.
- `/projects/:id` workspace — tabs **Gallery / Review / Analysis / Evaluations / Assets**.
  Tabs render the **existing page components** with a `projectId` prop threaded into their
  queries — not reimplementations. The existing pages keep working unparameterized as the
  global "All projects" view and gain a project-name column where rows are DB-backed.
- Assets tab — lists the project's `uploads` rows with thumbnails; upload button stamps the
  active project.

## Error handling

- Unknown `X-Project-Id` header: ignored (treated as no project) — never 4xx on reads or
  writes; a stale localStorage project must not brick the UI.
- `X-Member-Name` blank/absent: no member stamped; content lands in Unassigned.
- `POST /api/projects/{id}/assign` with an unknown table name: 422. Unknown ids: skipped,
  response reports `updated` count.
- Archiving a project hides it from the selector and Projects list default view; its content
  remains queryable via direct URL.

## Testing

- Scoping tests per table: project A queries never return project B rows; `unassigned`
  returns only NULL-project rows.
- Identity tests: header auto-creates member once (no duplicates on repeated calls);
  missing headers stamp nothing and break nothing.
- Assign endpoint tests: rows move buckets; unknown table 422.
- Upload test: POST /upload with headers creates an `uploads` row stamped with both ids.
- Standard constraints: disposable-container pytest per test file (never against live
  containers), `api-contract-checker` agent run at the end, frontend verified with raw
  `./node_modules/.bin/tsc -b --force`.

## Out of scope

- Per-project workflow presets (deferred with the Presets tab).
- Real authentication (passwords/SSO) — schema deliberately auth-ready (`members.id` stays
  the stable key).
- Physical project folders / file moves — DB grouping only.
- Backfilling `uploads` rows for files already on disk.
- Scoping `runpod_jobs`.

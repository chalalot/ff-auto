# Dropdown-Driven Project Scoping — Design

**Date:** 2026-07-09
**Status:** Approved (brainstorm)
**Branch:** z-image-gallery-updates

## Intent

Turn the project selector dropdown into the single control that switches
between a **global/admin view** and a **local/per-project view**:

- **"No project" selected → global view.** The nav pages aggregate data
  across all projects.
- **A specific project selected → local view.** The same nav pages show
  only that project's data.

Also declutter navigation: remove the standalone **Projects** nav item
and fold project creation + management into the dropdown itself.

## The core model

A single source of truth already exists: `projectId` in the identity
store (`localStorage: ff.projectId`, see `frontend/src/lib/identity.ts`),
auto-attached as the `X-Project-Id` header on every request by
`frontend/src/lib/api-client.ts`.

- `null` (No project) → global/admin aggregate.
- A project id → local view scoped to that project.

A new hook `useProjectId()` wraps
`useSyncExternalStore(subscribeIdentity, getProjectId)`. Every scoped page
reads it and feeds it into:

1. its react-query `queryKey` — so switching projects triggers a refetch, and
2. the `project_id` request param.

### Page behavior matrix

| Page | Behavior | Notes |
|---|---|---|
| Gallery | **scoped** | Backend already filters by `ImageLog.project_id`. |
| Review | **scoped** | Backend already accepts `project_id`. |
| Analysis | **scoped** | Backend already accepts `project_id`. |
| Video | **scoped** | `VideoLog.project_id` already stamped at generation; add a filter. |
| Archive | **scoped** | Filter filenames via existing `get_project_result_basenames()`. |
| Prompts | **global** | Shared templates — ignores the dropdown. |
| Workspace (generation) | **global surface** | New work is stamped with the active project via `X-Project-Id`; not a listing. |
| Monitor | **global** | Operational view. |
| Settings | **global** | — |

For every scoped page, `project_id = null/undefined` → aggregate all
(the backend already treats `None` as "no filter").

## Navigation & selector changes

### Remove the Projects nav item
Delete the `{ to: '/projects', label: 'Projects', icon: FolderOpen }`
entry from `navItems` in `frontend/src/components/shared/Layout.tsx`.
This is the "project symbol in the navigation menu" being removed.

### ProjectSelector becomes the sole switcher
`frontend/src/components/shared/ProjectSelector.tsx`:

- Options: `No project (global)` + the project list (unchanged).
- **Selecting a project only calls `setProjectId(id)` — remove the
  `navigate('/projects/:id')` call.** The current page re-scopes in place.
  This is the key behavior change.
- Add two footer actions below a divider:
  - **`+ New project`** — opens a small name-input modal.
  - **`⚙ Manage projects…`** — routes to the `/projects` management page.

Because the shadcn `Select` component is awkward to host arbitrary
buttons inside, the create/manage actions render as non-value rows (or a
small footer region) within `SelectContent`; clicking them closes the
select and performs the action rather than changing the selected value.

### Remove the redundant per-project workspace page
`frontend/src/pages/ProjectWorkspacePage.tsx` and its route
`projects/:projectId` are removed. Its Gallery/Review/Analysis tabs are
now just the scoped nav pages. Assets management stays reachable via the
`/projects` management page.

### `/projects` becomes management-only
`frontend/src/pages/ProjectsPage.tsx` stays as the management surface
(create / rename / archive / members / assets), reachable via
"Manage projects…". Clicking a project in the list **activates** it
(`setProjectId(id)`) instead of navigating to a separate workspace.

## `+` create flow & empty state

`+ New project` → modal with a name field → `projectsApi.create(name)` →
on success:

1. invalidate the `['projects']` query, and
2. `setProjectId(newId)` — dropping the user straight into the new,
   empty project.

Because scoping is by id and a new project has zero logged rows, every
scoped page is naturally empty / zeroed. No special empty-state plumbing
is required beyond the friendly empty states pages already render.

## Backend changes

Small — the data model already carries `project_id` on the relevant tables.

### Video
- `backend/api/video.py`: `GET /video/list` gains
  `project_id: Optional[str] = Query(None)`.
- `backend/services/video.py`: `list_videos(project_id=None)` passes it
  down.
- `backend/database/video_logs_storage.py`: `get_recent_executions`
  gains an optional `project_id` filter (`WHERE project_id == :pid`
  when provided; unfiltered when `None`).

### Archive
- `backend/api/archive.py`: `GET /archive/list` (and, where a result
  image must be resolvable, the thumbnail/metadata/image endpoints) gain
  `project_id: Optional[str] = Query(None)`.
- `backend/services/archive.py`: `list_images(project_id=None)` — when a
  project id is given, restrict returned result images to those whose
  basename is in `image_logs_storage.get_project_result_basenames(project_id)`
  (the same helper Gallery uses). `None` → all.

### Gallery / Review / Analysis
No backend change — already accept `project_id`.

## Frontend API/hooks changes

- `frontend/src/api/video.ts`: `list` gains `project_id?: string`.
- `frontend/src/api/archive.ts`: `list` gains `project_id?: string`.
- New hook `frontend/src/hooks/useProjectId.ts`.
- Gallery / Review / Analysis pages: stop receiving `projectId` as a
  prop (the workspace that supplied it is gone) and instead read
  `useProjectId()`. Keep the value in the query key + param.
- Video / Archive pages: read `useProjectId()`, add to query key + param.

## Isolation & boundaries

- `useProjectId()` is the single, well-defined interface between the
  selector and every scoped page. Pages never read `localStorage`
  directly; they depend only on the hook.
- Backend scoping stays behind each service's existing `project_id`
  parameter — routers just forward the query param. No new cross-cutting
  concern is introduced; the header remains for write-time stamping only.

## Testing

- Verify in a disposable container — never against the live mounted data
  dirs (fixtures can pollute them).
- Per-file pytest for touched services
  (`tests/...video...`, `tests/...archive...`) rather than the full
  suite (which has known pollution failures).
- Typecheck the frontend with the raw
  `./node_modules/.bin/tsc -b --force` (RTK mangles `tsc` output).
- Manual/e2e sanity: select "No project" → pages aggregate; select a
  project → pages scope; `+` a new project → all pages empty & stats 0.

## Out of scope

- Per-project Prompts (Prompts stay global by decision).
- Any auth / access control (identity remains header-trusted, no auth).
- Backfilling project_id onto historical archive files beyond what
  `ImageLog` already records.

# Dropdown-Driven Project Scoping Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the project-selector dropdown the single control that switches every listing page between a global (all-projects) view and a per-project (scoped) view, and fold project create/manage into the dropdown.

**Architecture:** Scoping is already driven by a `project_id` on backend tables and the `X-Project-Id` header. This plan (1) adds `project_id` filtering to the two listing endpoints that lack it (Video, Archive), (2) introduces a `useProjectId()` hook so every scoped React page reads the active project from the identity store, and (3) reshapes the sidebar: the dropdown gains "+ New project" and "Manage projects…", stops navigating to a per-project workspace, and the redundant `/projects/:id` tabbed page and the `Projects` nav item are removed.

**Tech Stack:** FastAPI + SQLAlchemy (backend), React + react-query + react-router + shadcn/Tailwind (frontend), pytest (backend tests). No frontend test runner exists — frontend tasks verify with `tsc` + a described manual check.

## Global Constraints

- **`project_id = None`/absent → aggregate all** (global view). A project id → scope. `"unassigned"` → only rows with NULL project_id. This is the existing contract — match it exactly.
- **Never run tests against the live container** — use a disposable container; fixtures pollute mounted data dirs.
- **Verify backend per-file**, not the whole suite: `pytest tests/<file>.py -v` (full suite has ~24 known pollution failures).
- **Typecheck the frontend with the raw binary**, never through RTK: `cd frontend && ./node_modules/.bin/tsc -b --force` (RTK garbles `tsc` output).
- **Scoped pages:** Gallery, Review, Analysis, Video, Archive. **Global pages:** Prompts, Workspace, Monitor, Settings.
- Follow existing patterns: modals are hand-rolled fixed overlays (see `MemberPickerModal.tsx`) — there is no shadcn dialog primitive.

---

### Task 1: Backend — scope Video list by project

**Files:**
- Modify: `backend/database/video_logs_storage.py` (`get_recent_executions`)
- Modify: `backend/services/video.py` (`list_videos`, ~line 211)
- Modify: `backend/api/video.py` (`list_videos` route, ~line 86)
- Test: `tests/test_video_scoping.py` (create)

**Interfaces:**
- Consumes: `VideoLog.project_id` (already stamped by `log_execution`).
- Produces:
  - `VideoLogsStorage.get_recent_executions(limit: int = 50, project_id: Optional[str] = None) -> list[dict]`
  - `VideoService.list_videos(page: int = 1, per_page: int = 20, project_id: Optional[str] = None) -> dict`
  - `GET /api/video/list?project_id=<id>` query param.

- [ ] **Step 1: Write the failing test**

Create `tests/test_video_scoping.py`:

```python
"""Video list is scoped by project_id; None aggregates all."""
import pytest

from backend.database.projects_storage import ProjectsStorage
from backend.database.video_logs_storage import VideoLogsStorage


@pytest.fixture
def two_projects(clean_tables):
    ps = ProjectsStorage()
    return ps.create_project("A")["id"], ps.create_project("B")["id"]


def _mk_video(project_id, execution_id, prompt):
    VideoLogsStorage().log_execution(
        execution_id=execution_id, prompt=prompt,
        source_image_path="/x/i.png", project_id=project_id,
    )


def test_video_list_scoped(client, two_projects):
    pa, pb = two_projects
    _mk_video(pa, "va", "in-a")
    _mk_video(pb, "vb", "in-b")
    _mk_video(None, "vc", "loose")

    items = client.get("/api/video/list", params={"project_id": pa}).json()["items"]
    assert [i["prompt"] for i in items] == ["in-a"]

    assert client.get("/api/video/list").json()["total"] == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_video_scoping.py -v`
Expected: FAIL — `/api/video/list` ignores `project_id`, so the scoped call returns all 3 (assert on `["in-a"]` fails).

- [ ] **Step 3: Add the filter to storage**

In `backend/database/video_logs_storage.py`, replace `get_recent_executions`:

```python
    def get_recent_executions(self, limit: int = 50, project_id: str = None):
        """Get recent executions ordered by creation time descending.

        When ``project_id`` is given, only that project's rows are returned;
        ``None`` returns rows from every project (global view).
        """
        try:
            with session_scope() as session:
                stmt = select(VideoLog).order_by(VideoLog.id.desc())
                if project_id is not None:
                    stmt = stmt.where(VideoLog.project_id == project_id)
                rows = session.execute(stmt.limit(limit)).scalars().all()
                return [_row_dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to fetch recent executions: {e}")
            return []
```

- [ ] **Step 4: Thread project_id through the service**

In `backend/services/video.py`, update `list_videos` (the `all_records` line ~211):

```python
    def list_videos(self, page: int = 1, per_page: int = 20,
                    project_id: Optional[str] = None) -> dict:
        """Paginate video execution records from DB."""
        all_records = self.storage.get_recent_executions(limit=1000, project_id=project_id)
```

(Leave the rest of the method unchanged. `Optional` is already imported in this file.)

- [ ] **Step 5: Add the query param to the route**

In `backend/api/video.py`, update the `list_videos` route:

```python
@router.get("/list", response_model=VideoListResponse)
def list_videos(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    project_id: Optional[str] = Query(None),
    svc: VideoService = Depends(get_video_service),
):
    """List video generation records with pagination, optionally scoped."""
    return svc.list_videos(page=page, per_page=per_page, project_id=project_id)
```

Ensure `from typing import Optional` and `Query` are imported at the top of `backend/api/video.py` (add to the existing import lines if missing).

- [ ] **Step 6: Run test to verify it passes**

Run: `pytest tests/test_video_scoping.py -v`
Expected: PASS (2 assertions in `test_video_list_scoped`).

- [ ] **Step 7: Commit**

```bash
git add backend/database/video_logs_storage.py backend/services/video.py backend/api/video.py tests/test_video_scoping.py
git commit -m "feat(video): scope /video/list by project_id

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Backend — scope Archive list by project

**Files:**
- Modify: `backend/services/archive.py` (`__init__`, `list_images`)
- Modify: `backend/api/archive.py` (`list_archive` route)
- Test: `tests/test_archive_scoping.py` (create)

**Interfaces:**
- Consumes: `ImageLogsStorage.get_project_result_basenames(project_id) -> set[str]` (existing; returns basenames of result images logged under a project).
- Produces:
  - `ArchiveService.list_images(server=None, page=1, per_page=20, project_id: Optional[str] = None) -> dict`
  - `GET /api/archive/list?project_id=<id>` query param.

- [ ] **Step 1: Write the failing test**

Create `tests/test_archive_scoping.py`:

```python
"""Archive list filters result images to the selected project's basenames."""
import pytest

from tests.conftest import make_png
from backend.database.image_logs_storage import ImageLogsStorage
from backend.database.projects_storage import ProjectsStorage
import backend.services.archive as archive_mod


@pytest.fixture
def two_projects(clean_tables):
    ps = ProjectsStorage()
    return ps.create_project("A")["id"], ps.create_project("B")["id"]


def test_archive_list_scoped(client, two_projects, tmp_path, monkeypatch):
    pa, pb = two_projects
    # Point ARCHIVE_BASE at a temp tree: <base>/srv1/results/{a,b}.png
    results = tmp_path / "srv1" / "results"
    results.mkdir(parents=True)
    make_png(str(results), "arc_a.png")
    make_png(str(results), "arc_b.png")
    monkeypatch.setattr(archive_mod, "ARCHIVE_BASE", tmp_path)

    logs = ImageLogsStorage()
    logs.log_execution(execution_id="aa", prompt="p", project_id=pa)
    logs.update_result_path(execution_id="aa", result_image_path="/whatever/arc_a.png")

    names = [i["filename"] for i in client.get(
        "/api/archive/list", params={"project_id": pa}
    ).json()["items"]]
    assert names == ["arc_a.png"]

    # Global view (no project) returns both.
    assert client.get("/api/archive/list").json()["total"] == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_archive_scoping.py -v`
Expected: FAIL — `/api/archive/list` has no `project_id` param, so the scoped call returns both files (assert on `["arc_a.png"]` fails).

- [ ] **Step 3: Give ArchiveService access to image-log basenames**

In `backend/services/archive.py`, add the import near the other imports:

```python
from backend.database.image_logs_storage import ImageLogsStorage
```

and add storage to `__init__` (after the existing `self.cache_dir` lines):

```python
        self.image_logs = ImageLogsStorage()
```

- [ ] **Step 4: Add the filter to list_images**

In `backend/services/archive.py`, update `list_images` — add the param and filter the collected files before sorting:

```python
    def list_images(
        self,
        server: Optional[str] = None,
        page: int = 1,
        per_page: int = 20,
        project_id: Optional[str] = None,
    ) -> dict:
        servers = [server] if server else self.list_servers()

        # Collect all result images across requested servers
        all_files: List[tuple] = []  # (server, filename, mtime)
        for srv in servers:
            for fname, mtime in self._scan_dir(self._results_dir(srv)):
                all_files.append((srv, fname, mtime))

        if project_id:
            allowed = self.image_logs.get_project_result_basenames(project_id)
            all_files = [t for t in all_files if t[1] in allowed]

        # Global newest-first sort
        all_files.sort(key=lambda x: x[2], reverse=True)
```

(Leave the pagination and item-building code below unchanged.)

- [ ] **Step 5: Add the query param to the route**

In `backend/api/archive.py`, update the `list_archive` route:

```python
@router.get("/list")
def list_archive(
    server: Optional[str] = Query(None, description="Filter by server name"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    project_id: Optional[str] = Query(None),
    svc: ArchiveService = Depends(get_archive_service),
):
    """Paginated list of result images from archive directories."""
    return svc.list_images(server=server, page=page, per_page=per_page, project_id=project_id)
```

(`Optional` and `Query` are already imported in this file.)

- [ ] **Step 6: Run test to verify it passes**

Run: `pytest tests/test_archive_scoping.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/services/archive.py backend/api/archive.py tests/test_archive_scoping.py
git commit -m "feat(archive): scope /archive/list by project result basenames

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Frontend — `useProjectId` hook + scope Gallery/Analysis/Review

**Files:**
- Create: `frontend/src/hooks/useProjectId.ts`
- Modify: `frontend/src/pages/GalleryPage.tsx` (line 33, 41-42)
- Modify: `frontend/src/pages/AnalysisPage.tsx` (line 102, 109-110)
- Modify: `frontend/src/pages/ReviewQueuePage.tsx` (line 199, 205-218, 305)

**Interfaces:**
- Produces: `useProjectId(): string | null` — reactive read of the active project from the identity store. Returns `null` for the global view.
- Note: after this task these three pages no longer accept a `projectId` prop; they read the hook. `ProjectWorkspacePage` (removed in Task 6) is the only prop caller — until then it still compiles because the prop becomes optional/ignored (see Step 2).

- [ ] **Step 1: Create the hook**

Create `frontend/src/hooks/useProjectId.ts`:

```typescript
import { useSyncExternalStore } from 'react'
import { getProjectId, subscribeIdentity } from '@/lib/identity'

/** Active project id from the identity store, or null for the global view. */
export function useProjectId(): string | null {
  return useSyncExternalStore(subscribeIdentity, getProjectId)
}
```

- [ ] **Step 2: Scope GalleryPage**

In `frontend/src/pages/GalleryPage.tsx`, add the import and read the hook instead of the prop. Change the component signature (line 33) and the two hook calls (lines 41-42):

```typescript
// add near the other imports
import { useProjectId } from '@/hooks/useProjectId'

// signature: drop the prop
export const GalleryPage: React.FC = () => {
  const projectId = useProjectId() ?? undefined
  // ...existing state...
  const { data: gallery, isLoading, refetch } = useGalleryImages(activeTab, page, ITEMS_PER_PAGE, projectId)
  const { data: stats } = useGalleryStats(projectId)
```

(`useGalleryImages`/`useGalleryStats` already key their queries by `projectId`, so switching projects refetches automatically.)

- [ ] **Step 3: Scope AnalysisPage**

In `frontend/src/pages/AnalysisPage.tsx`, same change — import the hook, drop the prop (line 102), read the hook. The query at 109-110 already keys on `projectId ?? 'all'`:

```typescript
import { useProjectId } from '@/hooks/useProjectId'

export const AnalysisPage: React.FC = () => {
  const projectId = useProjectId() ?? undefined
  // ...existing state...
  // query unchanged — it already uses projectId in queryKey + params
```

- [ ] **Step 4: Scope ReviewQueuePage**

In `frontend/src/pages/ReviewQueuePage.tsx`, import the hook, drop the prop (line 199), read the hook:

```typescript
import { useProjectId } from '@/hooks/useProjectId'

export const ReviewQueuePage: React.FC = () => {
  const projectId = useProjectId() ?? undefined
```

The existing lines that reference `projectId` (queryKey 205, params 210, `enabled: !projectId` 218 for the project-names lookup, and the `projectName` badge at 305 shown only in the global view) all keep working as-is — the badge that labels each row with its project now shows precisely in the global view, which is the intended behavior.

- [ ] **Step 5: Typecheck**

Run: `cd frontend && ./node_modules/.bin/tsc -b --force`
Expected: no errors. (Note: `ProjectWorkspacePage.tsx` still passes `projectId={...}` to these components; because these components no longer declare the prop, TS will error there. That file is deleted in Task 6 — to keep this task green, temporarily remove the three `projectId={projectId}` props in `ProjectWorkspacePage.tsx` Step 5a below.)

- [ ] **Step 5a: Unblock the typecheck in ProjectWorkspacePage**

In `frontend/src/pages/ProjectWorkspacePage.tsx`, drop the now-removed props (lines 40-42):

```typescript
        {tab === 'gallery' && <GalleryPage />}
        {tab === 'review' && <ReviewQueuePage />}
        {tab === 'analysis' && <AnalysisPage />}
        {tab === 'assets' && <AssetsPanel projectId={projectId} />}
```

(This makes the workspace tabs read the dropdown too — harmless, and the whole file is deleted in Task 6.) Re-run the typecheck; expected: no errors.

- [ ] **Step 6: Manual verification**

Start the app (disposable container). On `/gallery`, `/analysis`, `/review`: with "No project" selected the pages show all data; selecting a project in the dropdown re-scopes them **in place** (the page does not navigate away). Switch back to "No project" → aggregate returns.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/hooks/useProjectId.ts frontend/src/pages/GalleryPage.tsx frontend/src/pages/AnalysisPage.tsx frontend/src/pages/ReviewQueuePage.tsx frontend/src/pages/ProjectWorkspacePage.tsx
git commit -m "feat(frontend): Gallery/Analysis/Review scope to active project via useProjectId

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Frontend — scope Video & Archive to active project

**Files:**
- Modify: `frontend/src/api/video.ts` (`listVideos`, ~line 53)
- Modify: `frontend/src/hooks/useVideoLibrary.ts` (`useVideoList`)
- Modify: `frontend/src/api/archive.ts` (`list`)
- Modify: `frontend/src/pages/ArchivePage.tsx` (`useArchiveImages` hook + `ArchivePage`)

**Interfaces:**
- Consumes: `useProjectId()` from Task 3.
- Produces:
  - `videoApi.listVideos({ page?, per_page?, project_id? })`
  - `useVideoList(page?, perPage?, projectId?)`
  - `archiveApi.list({ server?, page?, per_page?, project_id? })`

- [ ] **Step 1: Add project_id to the video API client**

In `frontend/src/api/video.ts`, update `listVideos`:

```typescript
  listVideos: (params?: { page?: number; per_page?: number; project_id?: string }) =>
    apiClient.get<VideoListResponse>('/video/list', { params }).then(r => r.data),
```

- [ ] **Step 2: Thread projectId through useVideoList**

In `frontend/src/hooks/useVideoLibrary.ts`, update `useVideoList` to take and key on `projectId`:

```typescript
export function useVideoList(page = 1, perPage = 20, projectId?: string) {
  return useQuery({
    queryKey: ['videos', page, perPage, projectId ?? 'all'],
    queryFn: () => videoApi.listVideos({ page, per_page: perPage, project_id: projectId }),
    refetchInterval: (query) => {
      const items = query.state.data?.items || []
      const hasPending = items.some((item) =>
        ['pending', 'processing', 'submitted'].includes(item.status)
      )
      return hasPending ? 5000 : false
    },
  })
}
```

- [ ] **Step 3: Pass the active project from video consumers**

`useVideoList` is called in `frontend/src/components/video/VideoLibrary.tsx` and `frontend/src/components/video/VideoGenerationHistory.tsx`. In each, import the hook and pass the active project id:

```typescript
import { useProjectId } from '@/hooks/useProjectId'
// ...inside the component, where useVideoList is called:
const projectId = useProjectId() ?? undefined
// change the call site, preserving its existing page/perPage args, e.g.:
const { data, ... } = useVideoList(page, perPage, projectId)
```

(If a call site currently uses defaults like `useVideoList()`, change it to `useVideoList(1, 20, projectId)`. Keep whatever page/perPage variables already exist at that call site.)

- [ ] **Step 4: Add project_id to the archive API client**

In `frontend/src/api/archive.ts`, update `list`:

```typescript
  list: (params: { server?: string; page?: number; per_page?: number; project_id?: string }) =>
    apiClient
      .get<ArchiveListResponse>('/archive/list', { params })
      .then((r) => r.data),
```

- [ ] **Step 5: Scope the ArchivePage query**

In `frontend/src/pages/ArchivePage.tsx`, import the hook, extend `useArchiveImages`, and pass the active project:

```typescript
import { useProjectId } from '@/hooks/useProjectId'

function useArchiveImages(server: string | null, page: number, projectId?: string) {
  return useQuery({
    queryKey: ['archive', 'list', server, page, projectId ?? 'all'],
    queryFn: () =>
      archiveApi.list({
        server: server ?? undefined,
        page,
        per_page: ITEMS_PER_PAGE,
        project_id: projectId,
      }),
  })
}

// inside ArchivePage, alongside the existing useState hooks:
const projectId = useProjectId() ?? undefined
const { data, isLoading, refetch } = useArchiveImages(activeServer, page, projectId)
```

- [ ] **Step 6: Typecheck**

Run: `cd frontend && ./node_modules/.bin/tsc -b --force`
Expected: no errors.

- [ ] **Step 7: Manual verification**

On `/video` and `/archive`: "No project" shows all; selecting a project scopes the list; a freshly created project shows an empty list.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/api/video.ts frontend/src/hooks/useVideoLibrary.ts frontend/src/components/video/VideoLibrary.tsx frontend/src/components/video/VideoGenerationHistory.tsx frontend/src/api/archive.ts frontend/src/pages/ArchivePage.tsx
git commit -m "feat(frontend): scope Video and Archive lists to active project

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Frontend — redesign ProjectSelector (in-place switch + create + manage)

**Files:**
- Create: `frontend/src/components/shared/CreateProjectModal.tsx`
- Modify: `frontend/src/components/shared/ProjectSelector.tsx`

**Interfaces:**
- Consumes: `projectsApi.create(name) -> Promise<Project>`, `setProjectId`, react-query `['projects']` cache.
- Produces:
  - `<CreateProjectModal open onClose />` — hand-rolled overlay (MemberPickerModal style); on success it invalidates `['projects']` and calls `setProjectId(newId)` itself.
  - ProjectSelector no longer navigates on select; adds "+ New project" and "Manage projects…" actions.

- [ ] **Step 1: Build the create-project modal**

Create `frontend/src/components/shared/CreateProjectModal.tsx`:

```typescript
import React, { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { projectsApi } from '@/api/projects'
import { setProjectId } from '@/lib/identity'

export const CreateProjectModal: React.FC<{
  open: boolean
  onClose: () => void
}> = ({ open, onClose }) => {
  const qc = useQueryClient()
  const [name, setName] = useState('')
  const [busy, setBusy] = useState(false)

  if (!open) return null

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    const clean = name.trim()
    if (!clean || busy) return
    setBusy(true)
    try {
      const project = await projectsApi.create(clean)
      await qc.invalidateQueries({ queryKey: ['projects'] })
      setProjectId(project.id) // drop into the new, empty project
      setName('')
      onClose()
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 backdrop-blur-sm">
      <div className="w-full max-w-sm rounded-lg border bg-card p-6 space-y-4">
        <h2 className="font-semibold text-sm">New project</h2>
        <form onSubmit={submit} className="space-y-3">
          <Input
            autoFocus
            value={name}
            onChange={e => setName(e.target.value)}
            placeholder="Project name"
          />
          <div className="flex justify-end gap-2">
            <Button type="button" variant="ghost" onClick={onClose}>Cancel</Button>
            <Button type="submit" disabled={!name.trim() || busy}>Create</Button>
          </div>
        </form>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Rework ProjectSelector — no navigation, add actions**

Replace `frontend/src/components/shared/ProjectSelector.tsx` with:

```typescript
import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { Plus, Settings2 } from 'lucide-react'
import { projectsApi } from '@/api/projects'
import { useProjectId } from '@/hooks/useProjectId'
import { setProjectId } from '@/lib/identity'
import { CreateProjectModal } from '@/components/shared/CreateProjectModal'

const NONE = '__none__'
const CREATE = '__create__'
const MANAGE = '__manage__'

export const ProjectSelector: React.FC = () => {
  const navigate = useNavigate()
  const projectId = useProjectId()
  const [showCreate, setShowCreate] = useState(false)
  const { data: projects = [] } = useQuery({
    queryKey: ['projects'],
    queryFn: () => projectsApi.list(),
  })

  const handleChange = (v: string) => {
    if (v === CREATE) { setShowCreate(true); return }
    if (v === MANAGE) { navigate('/projects'); return }
    // Select the project (or clear to global). No navigation — the current
    // page re-scopes in place via useProjectId.
    setProjectId(v === NONE ? null : v)
  }

  return (
    <>
      <Select value={projectId ?? NONE} onValueChange={handleChange}>
        <SelectTrigger className="w-full text-xs">
          <SelectValue placeholder="No project" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={NONE}>No project (global)</SelectItem>
          {projects.map(p => (
            <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>
          ))}
          <div className="my-1 h-px bg-border" />
          <SelectItem value={CREATE}>
            <span className="flex items-center gap-2"><Plus className="w-3.5 h-3.5" />New project</span>
          </SelectItem>
          <SelectItem value={MANAGE}>
            <span className="flex items-center gap-2"><Settings2 className="w-3.5 h-3.5" />Manage projects…</span>
          </SelectItem>
        </SelectContent>
      </Select>
      <CreateProjectModal open={showCreate} onClose={() => setShowCreate(false)} />
    </>
  )
}
```

- [ ] **Step 3: Typecheck**

Run: `cd frontend && ./node_modules/.bin/tsc -b --force`
Expected: no errors.

- [ ] **Step 4: Manual verification**

Open the dropdown: it lists "No project (global)", the projects, then "+ New project" and "⚙ Manage projects…". Selecting a project re-scopes the current page **without navigating**. "+ New project" opens the modal; creating a project switches into it (empty everywhere). "Manage projects…" routes to `/projects`.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/shared/CreateProjectModal.tsx frontend/src/components/shared/ProjectSelector.tsx
git commit -m "feat(frontend): selector switches in place, adds create + manage actions

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: Frontend — remove Projects nav item, retire per-project workspace route

**Files:**
- Modify: `frontend/src/components/shared/Layout.tsx` (`navItems`, imports)
- Modify: `frontend/src/App.tsx` (routes)
- Modify: `frontend/src/pages/ProjectsPage.tsx` (project click activates scope)
- Delete: `frontend/src/pages/ProjectWorkspacePage.tsx`

**Interfaces:**
- Consumes: `setProjectId` (management-page activation), `ProjectSelector` (now the only switcher).
- Produces: `/projects` remains as the management page; `/projects/:projectId` route removed.

- [ ] **Step 1: Remove the Projects nav item**

In `frontend/src/components/shared/Layout.tsx`, delete the nav entry (line 36):

```typescript
  { to: '/projects', label: 'Projects', icon: FolderOpen },
```

and drop `FolderOpen` from the `lucide-react` import on line 4 (leave the other icons).

- [ ] **Step 2: Remove the workspace route**

In `frontend/src/App.tsx`, delete the route line:

```typescript
              <Route path="projects/:projectId" element={<ProjectWorkspacePage />} />
```

and remove the now-unused `import { ProjectWorkspacePage } from ...` at the top. Keep the `projects` (list) route.

- [ ] **Step 3: Delete the redundant workspace page**

```bash
git rm frontend/src/pages/ProjectWorkspacePage.tsx
```

- [ ] **Step 4: Make management-page clicks activate scope**

In `frontend/src/pages/ProjectsPage.tsx`, the project rows currently link to `/projects/:id` (the deleted route). Replace each project row's `<Link to={`/projects/${p.id}`}>` navigation with an activation handler that sets the scope and sends the user to the gallery:

```typescript
// add to imports
import { useNavigate } from 'react-router-dom'
// inside the component:
const navigate = useNavigate()
const openProject = (id: string) => { setProjectId(id); navigate('/gallery') }
```

Change the row so its primary click calls `openProject(p.id)` instead of routing to `/projects/${p.id}`. Remove any now-unused `Link` import if it is no longer referenced elsewhere in the file. (Preserve the existing archive/rename controls on each row.)

- [ ] **Step 5: Typecheck**

Run: `cd frontend && ./node_modules/.bin/tsc -b --force`
Expected: no errors (no dangling references to `ProjectWorkspacePage`, `FolderOpen`, or the removed route).

- [ ] **Step 6: Manual verification**

The sidebar no longer shows a Projects item. `/projects` is reachable only via the dropdown's "Manage projects…". Clicking a project in the management list activates it and lands on a scoped `/gallery`. Deep-linking to an old `/projects/<id>` URL no longer resolves to the tabbed workspace (expected — it's gone).

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/shared/Layout.tsx frontend/src/App.tsx frontend/src/pages/ProjectsPage.tsx
git commit -m "feat(frontend): drop Projects nav item and per-project workspace route

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Final verification (after all tasks)

- [ ] Backend per-file tests pass:
  `pytest tests/test_video_scoping.py tests/test_archive_scoping.py tests/test_phase3_scoping_filters.py -v`
- [ ] Frontend typechecks clean: `cd frontend && ./node_modules/.bin/tsc -b --force`
- [ ] End-to-end in a disposable container:
  - "No project" → Gallery/Review/Analysis/Video/Archive aggregate across all projects.
  - Select a project → all five scope to it, in place, no navigation.
  - Prompts stay global regardless of selection.
  - "+ New project" → lands in the new project with every page empty and stats at 0.
  - "Manage projects…" opens the management page; the Projects nav item is gone.

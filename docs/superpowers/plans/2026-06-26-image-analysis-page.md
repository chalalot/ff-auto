# Image Analysis Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an "Analysis" page that joins every generated image with its approval status and LLM evaluation, showing aggregate scoring stats on top and a filterable per-image table below.

**Architecture:** A new backend vertical slice (`GET /api/analysis`) scans the three image folders (pending/approved/disapproved), joins the latest evaluation per image from the evaluations SQLite DB, computes full-universe summary stats, and returns a paginated list. A new frontend page renders summary cards + a filterable table with an in-page lightbox. Follows the repo's existing per-feature pattern: models → service → router → deps → main wiring → frontend api/types/page.

**Tech Stack:** Python 3 / FastAPI / Pydantic / pytest (backend); React + TypeScript / react-query / Tailwind / Vite (frontend).

## Global Constraints

- Approval status is determined by which folder the image file lives in: `OUTPUT_DIR` = `pending`, `OUTPUT_DIR/approved` = `approved`, `OUTPUT_DIR/disapproved` = `disapproved`.
- Evaluations live in the `evaluations` SQLite table, joined to images by `media_path` (the absolute file path string, `str(directory / filename)`).
- Per-dimension scores are integers 1–5; `overall_score` is a stored float (mean of dimension scores, 2 dp).
- All backend tests must run against temp dirs / temp DBs — never touch real `results/` or a real `evaluations.db`.
- Reuse `GalleryService` helpers (`_dir_for_status`, `_scan_dir`, `extract_metadata`) rather than reimplementing folder/metadata logic.
- New API mounts under prefix `/api/analysis`. Frontend `apiClient` baseURL already includes `/api`, so frontend paths are `/analysis`.
- Rates are fractions of `total` in range 0–1 (frontend formats as %). `avg_overall_score` is `None` when nothing is evaluated.

---

## File Structure

**Backend**
- Create `backend/models/analysis.py` — Pydantic response models.
- Modify `backend/database/evaluations_storage.py` — add `get_latest_for_paths`, `get_score_summary`.
- Create `backend/services/analysis.py` — `AnalysisService` (scan + join + summary + paginate).
- Create `backend/api/analysis.py` — `GET /analysis` router.
- Modify `backend/api/deps.py` — `get_analysis_service`.
- Modify `backend/main.py` — import + `include_router`.
- Create `tests/test_services_analysis.py`, `tests/test_api_analysis.py`.

**Frontend**
- Create `frontend/src/types/analysis.ts` — response types.
- Create `frontend/src/api/analysis.ts` — `analysisApi`.
- Create `frontend/src/pages/AnalysisPage.tsx` — page (cards + filters + table + lightbox).
- Modify `frontend/src/App.tsx` — import + `<Route path="analysis">`.
- Modify `frontend/src/components/shared/Layout.tsx` — nav item.

---

## Task 1: Evaluations storage query methods

**Files:**
- Modify: `backend/database/evaluations_storage.py` (add two methods after `list_evaluations`, before `_decode_row` at line 181)
- Test: `tests/test_evaluations_storage_analysis.py` (create)

**Interfaces:**
- Consumes: existing `EvaluationsStorage(db_path)`, `_get_connection`, `_decode_row`, `create_pending`, `update_completed`.
- Produces:
  - `get_latest_for_paths(self, paths: List[str]) -> Dict[str, Dict[str, Any]]` — maps each `media_path` to its **latest** evaluation row (highest `id`), decoded (includes `scores` list). Paths with no row are absent from the dict. Empty `paths` → `{}`.
  - `get_score_summary(self) -> Dict[str, Any]` — returns `{"evaluated": int, "failed": int, "avg_overall_score": float | None, "evaluated_paths": set[str], "failed_paths": set[str]}` computed over the latest evaluation per `media_path`. `evaluated` counts distinct paths whose latest status is `completed`; `failed` counts distinct paths whose latest status is `failed`; `avg_overall_score` is the mean of `overall_score` across the `completed` latest rows (rounded 2 dp), `None` if none.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_evaluations_storage_analysis.py
import pytest

from backend.database.evaluations_storage import EvaluationsStorage


@pytest.fixture
def storage(tmp_path):
    return EvaluationsStorage(db_path=str(tmp_path / "evals.db"))


def _complete(storage, media_path, overall, dims):
    eid = storage.create_pending(
        media_type="image", media_path=media_path,
        prompt=None, model="m", rubric_version="production-v1",
    )
    storage.update_completed(
        evaluation_id=eid,
        scores=[{"dimension": d, "score": s, "rationale": "r"} for d, s in dims],
        overall_score=overall, summary="ok", raw_response={"ok": True},
    )
    return eid


def test_get_latest_for_paths_returns_latest_row(storage):
    _complete(storage, "/img/a.png", 3.0, [("artifact_free", 3)])
    _complete(storage, "/img/a.png", 5.0, [("artifact_free", 5)])  # newer
    out = storage.get_latest_for_paths(["/img/a.png", "/img/missing.png"])
    assert set(out.keys()) == {"/img/a.png"}
    assert out["/img/a.png"]["overall_score"] == 5.0
    assert out["/img/a.png"]["scores"][0]["score"] == 5


def test_get_latest_for_paths_empty(storage):
    assert storage.get_latest_for_paths([]) == {}


def test_get_score_summary_counts_and_average(storage):
    _complete(storage, "/img/a.png", 4.0, [("artifact_free", 4)])
    _complete(storage, "/img/b.png", 2.0, [("artifact_free", 2)])
    eid = storage.create_pending(
        media_type="image", media_path="/img/c.png",
        prompt=None, model="m", rubric_version="production-v1",
    )
    storage.update_failed(evaluation_id=eid, error_message="boom", raw_response=None)
    summary = storage.get_score_summary()
    assert summary["evaluated"] == 2
    assert summary["failed"] == 1
    assert summary["avg_overall_score"] == 3.0
    assert summary["evaluated_paths"] == {"/img/a.png", "/img/b.png"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_evaluations_storage_analysis.py -v`
Expected: FAIL with `AttributeError: 'EvaluationsStorage' object has no attribute 'get_latest_for_paths'`

- [ ] **Step 3: Write minimal implementation**

Insert into `backend/database/evaluations_storage.py` immediately before `def _decode_row` (line 181):

```python
    def get_latest_for_paths(self, paths: List[str]) -> Dict[str, Dict[str, Any]]:
        if not paths:
            return {}
        conn = self._get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        try:
            placeholders = ",".join("?" for _ in paths)
            cursor.execute(
                f"""
                SELECT * FROM evaluations
                WHERE media_path IN ({placeholders})
                ORDER BY id ASC
                """,
                tuple(paths),
            )
            # Higher id wins because we iterate ascending and overwrite.
            latest: Dict[str, Dict[str, Any]] = {}
            for row in cursor.fetchall():
                decoded = self._decode_row(row)
                latest[decoded["media_path"]] = decoded
            return latest
        finally:
            conn.close()

    def get_score_summary(self) -> Dict[str, Any]:
        conn = self._get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT * FROM evaluations ORDER BY id ASC")
            latest: Dict[str, Dict[str, Any]] = {}
            for row in cursor.fetchall():
                decoded = self._decode_row(row)
                latest[decoded["media_path"]] = decoded
        finally:
            conn.close()

        evaluated_paths = set()
        failed_paths = set()
        scores = []
        for path, row in latest.items():
            if row["status"] == "completed":
                evaluated_paths.add(path)
                if row.get("overall_score") is not None:
                    scores.append(row["overall_score"])
            elif row["status"] == "failed":
                failed_paths.add(path)

        avg = round(sum(scores) / len(scores), 2) if scores else None
        return {
            "evaluated": len(evaluated_paths),
            "failed": len(failed_paths),
            "avg_overall_score": avg,
            "evaluated_paths": evaluated_paths,
            "failed_paths": failed_paths,
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_evaluations_storage_analysis.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/database/evaluations_storage.py tests/test_evaluations_storage_analysis.py
git commit -m "feat: add evaluations storage query methods for analysis"
```

---

## Task 2: Analysis models + service

**Files:**
- Create: `backend/models/analysis.py`
- Create: `backend/services/analysis.py`
- Test: `tests/test_services_analysis.py`

**Interfaces:**
- Consumes: `GalleryService` (`_dir_for_status`, `_scan_dir`, `extract_metadata`); `EvaluationsStorage.get_latest_for_paths`, `get_score_summary`.
- Produces:
  - Models `AnalysisRow`, `ApprovalBreakdown`, `EvaluationBreakdown`, `AnalysisSummary`, `AnalysisResponse` (shapes below).
  - `AnalysisService(gallery_service=None, evaluations_storage=None)` with
    `get_analysis(self, status: str = "all", evaluated: str = "all", page: int = 1, per_page: int = 20) -> AnalysisResponse`.
  - `status` ∈ `{all, pending, approved, disapproved}`; `evaluated` ∈ `{all, yes, no}`.

- [ ] **Step 1: Write the models**

```python
# backend/models/analysis.py
from typing import List, Optional, Literal

from pydantic import BaseModel

from backend.models.evaluation import EvaluationScore

ApprovalStatus = Literal["pending", "approved", "disapproved"]
EvalRowStatus = Literal["completed", "pending", "failed", "not_evaluated"]


class AnalysisRow(BaseModel):
    filename: str
    path: str
    status: ApprovalStatus
    date: str
    created_at: float
    prompt: Optional[str] = None
    persona: Optional[str] = None
    eval_status: EvalRowStatus
    overall_score: Optional[float] = None
    scores: List[EvaluationScore] = []


class ApprovalBreakdown(BaseModel):
    approved: int
    disapproved: int
    pending: int
    approved_rate: float
    disapproved_rate: float
    pending_rate: float


class EvaluationBreakdown(BaseModel):
    evaluated: int
    not_evaluated: int
    failed: int
    evaluated_rate: float
    not_evaluated_rate: float


class AnalysisSummary(BaseModel):
    total: int
    approval: ApprovalBreakdown
    evaluation: EvaluationBreakdown
    avg_overall_score: Optional[float] = None


class AnalysisResponse(BaseModel):
    summary: AnalysisSummary
    items: List[AnalysisRow]
    total: int
    page: int
    pages: int
    per_page: int
```

- [ ] **Step 2: Write the failing test**

```python
# tests/test_services_analysis.py
import pytest

from tests.conftest import make_png


@pytest.fixture
def svc(_temp_dirs, tmp_path):
    from backend.services.gallery import GalleryService
    from backend.database.evaluations_storage import EvaluationsStorage
    from backend.services.analysis import AnalysisService

    gallery = GalleryService()
    storage = EvaluationsStorage(db_path=str(tmp_path / "evals.db"))
    return AnalysisService(gallery_service=gallery, evaluations_storage=storage), gallery, storage


def _complete(storage, media_path, overall):
    eid = storage.create_pending(
        media_type="image", media_path=media_path,
        prompt=None, model="m", rubric_version="production-v1",
    )
    storage.update_completed(
        evaluation_id=eid,
        scores=[{"dimension": "artifact_free", "score": int(overall), "rationale": "r"}],
        overall_score=overall, summary="ok", raw_response={"ok": True},
    )


def test_summary_counts_and_rates(svc, _temp_dirs):
    service, gallery, storage = svc
    make_png(_temp_dirs["OUTPUT_DIR"], "a_pending.png")
    make_png(str(gallery.approved_dir), "b_approved.png")
    make_png(str(gallery.disapproved_dir), "c_disapproved.png")
    # Evaluate only the approved one.
    _complete(storage, str(gallery.approved_dir / "b_approved.png"), 4.0)

    resp = service.get_analysis(status="all", evaluated="all", per_page=50)
    s = resp.summary
    assert s.total == 3
    assert s.approval.approved == 1
    assert s.approval.disapproved == 1
    assert s.approval.pending == 1
    assert s.approval.approved_rate == pytest.approx(1 / 3)
    assert s.evaluation.evaluated == 1
    assert s.evaluation.not_evaluated == 2
    assert s.avg_overall_score == 4.0


def test_status_filter_restricts_universe(svc, _temp_dirs):
    service, gallery, storage = svc
    make_png(_temp_dirs["OUTPUT_DIR"], "p1.png")
    make_png(str(gallery.approved_dir), "ap1.png")

    resp = service.get_analysis(status="approved", per_page=50)
    assert resp.summary.total == 1
    assert all(r.status == "approved" for r in resp.items)


def test_evaluated_filter_no(svc, _temp_dirs):
    service, gallery, storage = svc
    make_png(_temp_dirs["OUTPUT_DIR"], "ev.png")
    make_png(_temp_dirs["OUTPUT_DIR"], "noev.png")
    _complete(storage, str(gallery.output_dir / "ev.png"), 5.0)

    resp = service.get_analysis(evaluated="no", per_page=50)
    names = {r.filename for r in resp.items}
    assert "noev.png" in names
    assert "ev.png" not in names
    assert all(r.eval_status == "not_evaluated" for r in resp.items)


def test_row_carries_scores_and_metadata(svc, _temp_dirs):
    service, gallery, storage = svc
    make_png(str(gallery.approved_dir), "scored.png")
    _complete(storage, str(gallery.approved_dir / "scored.png"), 4.0)

    resp = service.get_analysis(status="approved", evaluated="yes", per_page=50)
    row = next(r for r in resp.items if r.filename == "scored.png")
    assert row.eval_status == "completed"
    assert row.overall_score == 4.0
    assert row.scores[0].dimension == "artifact_free"


def test_empty_universe(svc):
    service, _, _ = svc
    resp = service.get_analysis()
    assert resp.summary.total == 0
    assert resp.summary.avg_overall_score is None
    assert resp.items == []
    assert resp.pages == 1
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/test_services_analysis.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.services.analysis'`

- [ ] **Step 4: Write the service**

```python
# backend/services/analysis.py
import math
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from backend.database.evaluations_storage import EvaluationsStorage
from backend.models.analysis import (
    AnalysisResponse,
    AnalysisRow,
    AnalysisSummary,
    ApprovalBreakdown,
    EvaluationBreakdown,
)
from backend.models.evaluation import EvaluationScore
from backend.services.gallery import GalleryService

_STATUSES = ("pending", "approved", "disapproved")


class AnalysisService:
    def __init__(
        self,
        gallery_service: Optional[GalleryService] = None,
        evaluations_storage: Optional[EvaluationsStorage] = None,
    ):
        self.gallery = gallery_service or GalleryService()
        self.storage = evaluations_storage or EvaluationsStorage()

    def _scan_all(self) -> List[Tuple[str, str, float]]:
        """Return [(filename, status, mtime)] across all three folders."""
        rows: List[Tuple[str, str, float]] = []
        for status in _STATUSES:
            directory = self.gallery._dir_for_status(status)
            for filename, mtime in self.gallery._scan_dir(directory):
                rows.append((filename, status, mtime))
        rows.sort(key=lambda r: r[2], reverse=True)
        return rows

    def get_analysis(
        self,
        status: str = "all",
        evaluated: str = "all",
        page: int = 1,
        per_page: int = 20,
    ) -> AnalysisResponse:
        all_rows = self._scan_all()
        if status in _STATUSES:
            all_rows = [r for r in all_rows if r[1] == status]

        score_summary = self.storage.get_score_summary()
        evaluated_paths = score_summary["evaluated_paths"]
        failed_paths = score_summary["failed_paths"]

        def _path(filename: str, st: str) -> str:
            return str(self.gallery._dir_for_status(st) / filename)

        if evaluated == "yes":
            all_rows = [r for r in all_rows if _path(r[0], r[1]) in evaluated_paths]
        elif evaluated == "no":
            all_rows = [r for r in all_rows if _path(r[0], r[1]) not in evaluated_paths]

        summary = self._build_summary(all_rows, score_summary, status, evaluated)

        total = len(all_rows)
        pages = math.ceil(total / per_page) if total else 1
        page = max(1, min(page, pages))
        start = (page - 1) * per_page
        page_rows = all_rows[start : start + per_page]

        page_paths = [_path(f, st) for f, st, _ in page_rows]
        latest = self.storage.get_latest_for_paths(page_paths)

        items: List[AnalysisRow] = []
        for filename, st, mtime in page_rows:
            path = _path(filename, st)
            meta = self.gallery.extract_metadata(filename, status=st)
            ev = latest.get(path)
            if ev is None:
                eval_status = "not_evaluated"
                overall = None
                scores: List[EvaluationScore] = []
            else:
                eval_status = ev["status"]
                overall = ev.get("overall_score")
                scores = [EvaluationScore(**s) for s in ev.get("scores", [])]
            items.append(
                AnalysisRow(
                    filename=filename,
                    path=path,
                    status=st,
                    date=datetime.fromtimestamp(mtime).strftime("%Y-%m-%d"),
                    created_at=mtime,
                    prompt=meta.get("prompt"),
                    persona=meta.get("persona"),
                    eval_status=eval_status,
                    overall_score=overall,
                    scores=scores,
                )
            )

        return AnalysisResponse(
            summary=summary,
            items=items,
            total=total,
            page=page,
            pages=pages,
            per_page=per_page,
        )

    def _build_summary(
        self,
        rows: List[Tuple[str, str, float]],
        score_summary: Dict,
        status: str,
        evaluated: str,
    ) -> AnalysisSummary:
        total = len(rows)

        def rate(n: int) -> float:
            return round(n / total, 4) if total else 0.0

        approved = sum(1 for r in rows if r[1] == "approved")
        disapproved = sum(1 for r in rows if r[1] == "disapproved")
        pending = sum(1 for r in rows if r[1] == "pending")

        evaluated_paths = score_summary["evaluated_paths"]
        failed_paths = score_summary["failed_paths"]

        def _path(filename: str, st: str) -> str:
            return str(self.gallery._dir_for_status(st) / filename)

        row_paths = [_path(f, st) for f, st, _ in rows]
        evaluated_count = sum(1 for p in row_paths if p in evaluated_paths)
        failed_count = sum(1 for p in row_paths if p in failed_paths)
        not_evaluated = total - evaluated_count

        # Average over the evaluated images present in the filtered universe.
        if evaluated_count and (status != "all" or evaluated != "all"):
            latest = self.storage.get_latest_for_paths(
                [p for p in row_paths if p in evaluated_paths]
            )
            vals = [
                latest[p]["overall_score"]
                for p in row_paths
                if p in latest and latest[p].get("overall_score") is not None
            ]
            avg = round(sum(vals) / len(vals), 2) if vals else None
        else:
            avg = score_summary["avg_overall_score"]

        return AnalysisSummary(
            total=total,
            approval=ApprovalBreakdown(
                approved=approved,
                disapproved=disapproved,
                pending=pending,
                approved_rate=rate(approved),
                disapproved_rate=rate(disapproved),
                pending_rate=rate(pending),
            ),
            evaluation=EvaluationBreakdown(
                evaluated=evaluated_count,
                not_evaluated=not_evaluated,
                failed=failed_count,
                evaluated_rate=rate(evaluated_count),
                not_evaluated_rate=rate(not_evaluated),
            ),
            avg_overall_score=avg,
        )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_services_analysis.py -v`
Expected: PASS (5 tests)

- [ ] **Step 6: Commit**

```bash
git add backend/models/analysis.py backend/services/analysis.py tests/test_services_analysis.py
git commit -m "feat: add analysis models and service"
```

---

## Task 3: Analysis API router + wiring

**Files:**
- Create: `backend/api/analysis.py`
- Modify: `backend/api/deps.py` (append after `get_evaluation_service`, line 51)
- Modify: `backend/main.py:9-17` (import) and `backend/main.py:53` (include_router)
- Test: `tests/test_api_analysis.py`

**Interfaces:**
- Consumes: `AnalysisService.get_analysis`, `get_analysis_service` dependency.
- Produces: `GET /api/analysis?status=&evaluated=&page=&per_page=` → `AnalysisResponse` JSON.

- [ ] **Step 1: Add the dependency provider**

Append to `backend/api/deps.py`:

```python
from backend.services.analysis import AnalysisService


@lru_cache
def get_analysis_service() -> AnalysisService:
    return AnalysisService()
```

- [ ] **Step 2: Write the router**

```python
# backend/api/analysis.py
from fastapi import APIRouter, Depends, Query

from backend.api.deps import get_analysis_service
from backend.models.analysis import AnalysisResponse
from backend.services.analysis import AnalysisService

router = APIRouter()


@router.get("", response_model=AnalysisResponse)
def list_analysis(
    status: str = Query("all", pattern="^(all|pending|approved|disapproved)$"),
    evaluated: str = Query("all", pattern="^(all|yes|no)$"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    svc: AnalysisService = Depends(get_analysis_service),
):
    return svc.get_analysis(
        status=status, evaluated=evaluated, page=page, per_page=per_page
    )
```

- [ ] **Step 3: Wire into main.py**

In `backend/main.py`, add `analysis as analysis_module,` to the `from backend.api import (...)` block (after `evaluations as evaluations_module,` on line 16):

```python
from backend.api import (
    workspace,
    gallery,
    config_routes,
    monitor,
    video as video_module,
    archive as archive_module,
    evaluations as evaluations_module,
    analysis as analysis_module,
)
```

And after line 53 (`app.include_router(evaluations_module.router, ...)`):

```python
app.include_router(analysis_module.router, prefix="/api/analysis", tags=["analysis"])
```

- [ ] **Step 4: Write the failing API test**

```python
# tests/test_api_analysis.py
from tests.conftest import make_png


def test_analysis_endpoint_returns_summary_and_items(client, _temp_dirs):
    make_png(_temp_dirs["OUTPUT_DIR"], "api_analysis_pending.png")

    resp = client.get("/api/analysis", params={"status": "all", "evaluated": "all"})
    assert resp.status_code == 200
    body = resp.json()
    assert "summary" in body
    assert "items" in body
    assert body["summary"]["total"] >= 1
    assert {"approval", "evaluation", "avg_overall_score"} <= set(body["summary"].keys())


def test_analysis_rejects_bad_status(client):
    resp = client.get("/api/analysis", params={"status": "bogus"})
    assert resp.status_code == 422


def test_analysis_pagination_params(client, _temp_dirs):
    for i in range(3):
        make_png(_temp_dirs["OUTPUT_DIR"], f"api_an_page_{i}.png")
    resp = client.get("/api/analysis", params={"page": 1, "per_page": 2})
    assert resp.status_code == 200
    body = resp.json()
    assert body["per_page"] == 2
    assert len(body["items"]) <= 2
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_api_analysis.py -v`
Expected: PASS (3 tests)

Note: the API uses the `lru_cache`d default `AnalysisService()`, which constructs its own `EvaluationsStorage()` (real `evaluations.db`). The tests assert on counts/structure that don't depend on eval contents, so they pass regardless. Do not assert on `evaluated`/`avg_overall_score` values in the API test.

- [ ] **Step 6: Run the full backend suite**

Run: `python -m pytest tests/ -q`
Expected: PASS (no regressions)

- [ ] **Step 7: Commit**

```bash
git add backend/api/analysis.py backend/api/deps.py backend/main.py tests/test_api_analysis.py
git commit -m "feat: add analysis API endpoint"
```

---

## Task 4: Frontend types + API client

**Files:**
- Create: `frontend/src/types/analysis.ts`
- Create: `frontend/src/api/analysis.ts`

**Interfaces:**
- Consumes: `apiClient` from `@/lib/api-client` (baseURL includes `/api`); `EvaluationScore` from `@/types/evaluation`.
- Produces: `analysisApi.list(params)` returning `Promise<AnalysisResponse>`; types matching the backend `AnalysisResponse`.

- [ ] **Step 1: Write the types**

```typescript
// frontend/src/types/analysis.ts
import type { EvaluationScore } from '@/types/evaluation'

export type ApprovalStatus = 'pending' | 'approved' | 'disapproved'
export type EvalRowStatus = 'completed' | 'pending' | 'failed' | 'not_evaluated'
export type AnalysisStatusFilter = 'all' | ApprovalStatus
export type EvaluatedFilter = 'all' | 'yes' | 'no'

export interface AnalysisRow {
  filename: string
  path: string
  status: ApprovalStatus
  date: string
  created_at: number
  prompt?: string | null
  persona?: string | null
  eval_status: EvalRowStatus
  overall_score?: number | null
  scores: EvaluationScore[]
}

export interface ApprovalBreakdown {
  approved: number
  disapproved: number
  pending: number
  approved_rate: number
  disapproved_rate: number
  pending_rate: number
}

export interface EvaluationBreakdown {
  evaluated: number
  not_evaluated: number
  failed: number
  evaluated_rate: number
  not_evaluated_rate: number
}

export interface AnalysisSummary {
  total: number
  approval: ApprovalBreakdown
  evaluation: EvaluationBreakdown
  avg_overall_score?: number | null
}

export interface AnalysisResponse {
  summary: AnalysisSummary
  items: AnalysisRow[]
  total: number
  page: number
  pages: number
  per_page: number
}
```

- [ ] **Step 2: Write the API client**

```typescript
// frontend/src/api/analysis.ts
import { apiClient } from '@/lib/api-client'
import type { AnalysisResponse, AnalysisStatusFilter, EvaluatedFilter } from '@/types/analysis'

export const analysisApi = {
  list: (params: {
    status?: AnalysisStatusFilter
    evaluated?: EvaluatedFilter
    page?: number
    per_page?: number
  }) =>
    apiClient.get<AnalysisResponse>('/analysis', { params }).then(r => r.data),
}
```

- [ ] **Step 3: Verify it type-checks**

Run: `cd frontend && npx tsc -b --noEmit`
Expected: no errors (files compile; they're not yet imported anywhere, which is fine).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/analysis.ts frontend/src/api/analysis.ts
git commit -m "feat: add analysis frontend types and api client"
```

---

## Task 5: AnalysisPage (cards + filters + table + lightbox) and navigation

**Files:**
- Create: `frontend/src/pages/AnalysisPage.tsx`
- Modify: `frontend/src/App.tsx` (import line ~10; route after line 64 `archive`)
- Modify: `frontend/src/components/shared/Layout.tsx` (import icon; add nav item)

**Interfaces:**
- Consumes: `analysisApi.list`; types from `@/types/analysis`; `Card`/`Badge`/`Button`/`Select` UI components; `galleryApi.getDownloadUrl` and `galleryApi.getThumbnailUrl` from `@/api/gallery` for images.
- Produces: `AnalysisPage` React component (named export); `/analysis` route; sidebar nav entry.

- [ ] **Step 1: Write the page component**

```tsx
// frontend/src/pages/AnalysisPage.tsx
import React, { useState } from 'react'
import { useQuery, keepPreviousData } from '@tanstack/react-query'
import { Loader2, X, ChevronLeft, ChevronRight } from 'lucide-react'
import { analysisApi } from '@/api/analysis'
import { galleryApi } from '@/api/gallery'
import type {
  AnalysisRow,
  AnalysisStatusFilter,
  EvaluatedFilter,
} from '@/types/analysis'
import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'

const pct = (rate: number) => `${(rate * 100).toFixed(0)}%`
const STATUS_VARIANT: Record<string, string> = {
  approved: 'bg-green-500/15 text-green-700 dark:text-green-400',
  disapproved: 'bg-red-500/15 text-red-700 dark:text-red-400',
  pending: 'bg-amber-500/15 text-amber-700 dark:text-amber-400',
}

function StatCard({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <Card className="p-4">
      <div className="text-xs uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className="text-2xl font-semibold mt-1">{value}</div>
      {sub && <div className="text-xs text-muted-foreground mt-1">{sub}</div>}
    </Card>
  )
}

function ScoreCell({ row }: { row: AnalysisRow }) {
  if (row.eval_status !== 'completed') {
    return <span className="text-xs text-muted-foreground">{row.eval_status.replace('_', ' ')}</span>
  }
  return (
    <div className="space-y-1.5 max-w-md">
      {row.scores.map(s => (
        <div key={s.dimension} className="text-xs">
          <span className="font-medium">{s.dimension.replace(/_/g, ' ')}: </span>
          <span className="tabular-nums">{s.score}/5</span>
          <span className="text-muted-foreground"> — {s.rationale}</span>
        </div>
      ))}
      <div className="text-sm font-semibold pt-1">
        Avg: {row.overall_score?.toFixed(2) ?? '—'}
      </div>
    </div>
  )
}

function Lightbox({ row, onClose }: { row: AnalysisRow; onClose: () => void }) {
  React.useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div
      className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        className="bg-card rounded-lg max-w-5xl w-full max-h-[90vh] overflow-auto p-4 grid grid-cols-1 md:grid-cols-2 gap-4"
        onClick={e => e.stopPropagation()}
      >
        <div className="relative">
          <img
            src={galleryApi.getThumbnailUrl(row.filename, row.status)}
            alt={row.filename}
            className="w-full rounded-md object-contain"
          />
        </div>
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <span className="font-mono text-xs break-all">{row.filename}</span>
            <button onClick={onClose} className="p-1 hover:bg-accent rounded">
              <X className="w-4 h-4" />
            </button>
          </div>
          <Badge className={STATUS_VARIANT[row.status]}>{row.status}</Badge>
          <ScoreCell row={row} />
          {row.prompt && (
            <div className="text-xs">
              <div className="font-medium">Prompt</div>
              <p className="text-muted-foreground whitespace-pre-wrap">{row.prompt}</p>
            </div>
          )}
          {row.persona && (
            <div className="text-xs">
              <span className="font-medium">Persona: </span>
              <span className="text-muted-foreground">{row.persona}</span>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export const AnalysisPage: React.FC = () => {
  const [status, setStatus] = useState<AnalysisStatusFilter>('all')
  const [evaluated, setEvaluated] = useState<EvaluatedFilter>('all')
  const [page, setPage] = useState(1)
  const [selected, setSelected] = useState<AnalysisRow | null>(null)

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['analysis', status, evaluated, page],
    queryFn: () => analysisApi.list({ status, evaluated, page, per_page: 25 }),
    placeholderData: keepPreviousData,
  })

  const onFilter = (fn: () => void) => {
    fn()
    setPage(1)
  }

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-xl font-semibold">Analysis</h1>
        <p className="text-sm text-muted-foreground">Scoring and approval overview across all generated images.</p>
      </div>

      {data && (
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
          <StatCard label="Avg Score" value={data.summary.avg_overall_score?.toFixed(2) ?? '—'} sub={`${data.summary.total} images`} />
          <StatCard label="Approved" value={`${data.summary.approval.approved}`} sub={pct(data.summary.approval.approved_rate)} />
          <StatCard label="Disapproved" value={`${data.summary.approval.disapproved}`} sub={pct(data.summary.approval.disapproved_rate)} />
          <StatCard label="Pending" value={`${data.summary.approval.pending}`} sub={pct(data.summary.approval.pending_rate)} />
          <StatCard label="Evaluated" value={`${data.summary.evaluation.evaluated}`} sub={pct(data.summary.evaluation.evaluated_rate)} />
          <StatCard label="Not Evaluated" value={`${data.summary.evaluation.not_evaluated}`} sub={pct(data.summary.evaluation.not_evaluated_rate)} />
        </div>
      )}

      <div className="flex flex-wrap gap-3 items-center">
        <select
          className="border rounded-md px-2 py-1 text-sm bg-background"
          value={status}
          onChange={e => onFilter(() => setStatus(e.target.value as AnalysisStatusFilter))}
        >
          <option value="all">All statuses</option>
          <option value="approved">Approved</option>
          <option value="disapproved">Disapproved</option>
          <option value="pending">Pending</option>
        </select>
        <select
          className="border rounded-md px-2 py-1 text-sm bg-background"
          value={evaluated}
          onChange={e => onFilter(() => setEvaluated(e.target.value as EvaluatedFilter))}
        >
          <option value="all">All</option>
          <option value="yes">Evaluated</option>
          <option value="no">Not evaluated</option>
        </select>
      </div>

      {isLoading && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="w-4 h-4 animate-spin" /> Loading analysis…
        </div>
      )}
      {isError && (
        <div className="text-sm text-red-600 flex items-center gap-3">
          Failed to load analysis.
          <Button variant="outline" size="sm" onClick={() => refetch()}>Retry</Button>
        </div>
      )}

      {data && (
        <>
          <div className="overflow-x-auto border rounded-lg">
            <table className="w-full text-sm">
              <thead className="bg-muted/50 text-left">
                <tr>
                  <th className="p-3 font-medium">Image</th>
                  <th className="p-3 font-medium">Status</th>
                  <th className="p-3 font-medium">Rubric Scores</th>
                  <th className="p-3 font-medium">Prompt / Persona</th>
                  <th className="p-3 font-medium">Date</th>
                </tr>
              </thead>
              <tbody>
                {data.items.length === 0 && (
                  <tr><td colSpan={5} className="p-6 text-center text-muted-foreground">No images match these filters.</td></tr>
                )}
                {data.items.map(row => (
                  <tr key={row.path} className="border-t hover:bg-accent/30">
                    <td className="p-3">
                      <button onClick={() => setSelected(row)} className="block">
                        <img
                          src={galleryApi.getThumbnailUrl(row.filename, row.status)}
                          alt={row.filename}
                          className="w-20 h-20 object-cover rounded-md hover:ring-2 ring-primary"
                          loading="lazy"
                        />
                      </button>
                    </td>
                    <td className="p-3 align-top">
                      <Badge className={STATUS_VARIANT[row.status]}>{row.status}</Badge>
                    </td>
                    <td className="p-3 align-top"><ScoreCell row={row} /></td>
                    <td className="p-3 align-top max-w-xs">
                      <div className="text-xs text-muted-foreground line-clamp-3 whitespace-pre-wrap">{row.prompt || '—'}</div>
                      {row.persona && <div className="text-xs mt-1"><span className="font-medium">Persona:</span> {row.persona}</div>}
                    </td>
                    <td className="p-3 align-top whitespace-nowrap text-xs text-muted-foreground">{row.date}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">{data.total} images · page {data.page} / {data.pages}</span>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage(p => p - 1)}>
                <ChevronLeft className="w-4 h-4" /> Prev
              </Button>
              <Button variant="outline" size="sm" disabled={page >= data.pages} onClick={() => setPage(p => p + 1)}>
                Next <ChevronRight className="w-4 h-4" />
              </Button>
            </div>
          </div>
        </>
      )}

      {selected && <Lightbox row={selected} onClose={() => setSelected(null)} />}
    </div>
  )
}
```

- [ ] **Step 2: Register the route in App.tsx**

Add the import alongside the other page imports (after line 10, the `ArchivePage` import):

```tsx
import { AnalysisPage } from '@/pages/AnalysisPage'
```

Add the route after the `archive` route (line 64):

```tsx
              <Route path="analysis" element={<AnalysisPage />} />
```

- [ ] **Step 3: Add the nav item in Layout.tsx**

Add `BarChart3` to the lucide import on line 4:

```tsx
import { Image, Grid, Video, Activity, FileText, Settings, Archive, Loader2, BarChart3 } from 'lucide-react'
```

Add to the `navItems` array (after the `gallery` entry, line 32):

```tsx
  { to: '/analysis', label: 'Analysis', icon: BarChart3 },
```

- [ ] **Step 4: Type-check and build**

Run: `cd frontend && npx tsc -b --noEmit && npm run build`
Expected: build succeeds with no type errors.

- [ ] **Step 5: Manual smoke test**

Start the backend (`uvicorn backend.main:app --reload`) and frontend (`npm run dev`), open the Analysis tab. Verify: summary cards render; table lists images with status badges and scores; changing filters refetches and resets to page 1; clicking a thumbnail opens the lightbox; Esc / overlay click closes it; pagination buttons work.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/AnalysisPage.tsx frontend/src/App.tsx frontend/src/components/shared/Layout.tsx
git commit -m "feat: add Analysis page with summary cards, table, and lightbox"
```

---

## Task 6: Contract verification

**Files:** none (verification only).

- [ ] **Step 1: Run the api-contract-checker**

Dispatch the `api-contract-checker` agent (or manually diff `backend/models/analysis.py` against `frontend/src/types/analysis.ts`). Confirm field names and types match: `AnalysisResponse`, `AnalysisSummary`, `ApprovalBreakdown`, `EvaluationBreakdown`, `AnalysisRow`. Fix any drift.

- [ ] **Step 2: Final full backend suite**

Run: `python -m pytest tests/ -q`
Expected: PASS.

---

## Self-Review notes

- **Spec coverage:** summary stats (avg score, approval/disapproval/pending counts+rates, evaluated/not-evaluated counts+rates) → Task 2 `_build_summary` + Task 5 cards. Table col1 image (clickable→lightbox) → Task 5. Col2 approval status → Task 5. Col3 per-dimension scores + rationale + avg → Task 5 `ScoreCell`. Prompt/persona + date columns → Task 5. Status + evaluated filters → Tasks 2/3/5. Pagination → Tasks 2/3/5. Lightbox → Task 5. Error/empty states → Task 5.
- **Average-score subtlety:** when no filter is applied, the page summary uses the DB-wide `get_score_summary` average; when filtered, it recomputes the average over only the evaluated images in the filtered universe (Task 2 `_build_summary`).
- **Perf:** metadata extraction (PNG open) runs only for the current page's ≤25 rows; the summary uses folder counts + a single eval-DB pass.

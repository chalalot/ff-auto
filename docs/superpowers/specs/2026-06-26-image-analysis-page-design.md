# Image Analysis Page — Design

Date: 2026-06-26
Branch: z-image-gallery-updates

## Goal

A new "Analysis" page that joins every generated image with its approval status
and its LLM evaluation, showing aggregate scoring stats on top and a detailed
per-image table below.

## Scope

- **Image universe**: all images on disk (pending + approved + disapproved), with
  a status filter and an evaluated/not-evaluated filter. Default = all.
- **Click-through**: clicking a row's image opens an in-page lightbox (full image +
  full evaluation). No changes to the Gallery page.
- **Extra columns**: Prompt & persona, Date created (in addition to image,
  approval status, and rubric scores + rationale + avg).

## Architecture

New backend vertical slice + new frontend page, following the repo's existing
per-feature pattern (models → service → router → deps → api client → types → page).

### Backend

**`backend/models/analysis.py`**
- `AnalysisRow`: `filename`, `path`, `status` (`pending|approved|disapproved`),
  `date` ("YYYY-MM-DD"), `created_at` (float mtime), `prompt` (str|None),
  `persona` (str|None), `eval_status`
  (`completed|pending|failed|not_evaluated`), `overall_score` (float|None),
  `scores` (list of `{dimension, score, rationale}`, `[]` if not evaluated).
- `AnalysisSummary`:
  - `total: int`
  - `approval: {approved, disapproved, pending, approved_rate, disapproved_rate, pending_rate}`
  - `evaluation: {evaluated, not_evaluated, evaluated_rate, not_evaluated_rate, failed}`
  - `avg_overall_score: float|None`
- `AnalysisResponse`: `{summary, items: AnalysisRow[], total, page, pages, per_page}`

Rates are fractions of `total` (0–1); frontend formats as %. `avg_overall_score`
rounds to 2 dp, `None` when nothing evaluated.

**`backend/database/evaluations_storage.py`** (additions)
- `get_latest_for_paths(paths: list[str]) -> dict[str, row]`: one query returning
  the latest evaluation per `media_path` for the current page's images.
- `get_score_summary(paths: list[str] | None) -> {evaluated, failed, avg_overall_score}`:
  aggregate for the summary block without loading every row.

**`backend/services/analysis.py`** — `AnalysisService`
- Reuses `GalleryService` helpers (`_scan_dir`, `_dir_for_status`, `extract_metadata`).
- Scans the 3 folders → full image list with status + mtime/date.
- Applies `status` and `evaluated` filters.
- Computes `AnalysisSummary` over the full filtered universe (folder counts +
  eval-DB aggregate).
- Sorts newest-first (`created_at` desc), paginates.
- Extracts per-image metadata (prompt/persona) and joins evaluations **only for
  the current page's rows**.

**`backend/api/analysis.py`** — `GET /analysis`
- Query params: `status` (`all|pending|approved|disapproved`, default `all`),
  `evaluated` (`all|yes|no`, default `all`), `page` (>=1), `per_page` (1–100).
- Wire into `backend/api/deps.py` (`get_analysis_service`) and the app router.

### Frontend

- `frontend/src/types/analysis.ts` — mirror the response shapes.
- `frontend/src/api/analysis.ts` — `analysisApi.list({status, evaluated, page, per_page})`.
- `frontend/src/pages/AnalysisPage.tsx`:
  - Top: summary stat cards — avg score; approved/disapproved/pending counts+rates;
    evaluated/not-evaluated counts+rates.
  - Filter controls (status, evaluated).
  - Table: col1 image thumbnail (click → lightbox), col2 approval status badge,
    col3 per-dimension rubric scores + rationale + bold final avg, then
    Prompt & persona, Date created.
  - Lightbox modal: full image (`/gallery/download/{filename}?status=`), status
    badge, all scores+rationales, overall avg, prompt/persona. Close on overlay/Esc.
  - react-query for fetching; paginated.
- Nav entry + `<Route path="analysis">` in `frontend/src/App.tsx`.

## Behavior details

- **Two independent dimensions**: approval (folder) vs evaluation (completed eval
  exists). An image can be approved and not-evaluated.
- `not_evaluated` = latest eval missing or non-`completed`. `failed` surfaced
  separately in the eval block.
- Per-image `overall_score` is the avg already stored on the evaluation.
- `avg_overall_score` = mean of `overall_score` across evaluated images in the
  filtered universe.

## Error / empty states

- Empty universe → cards show 0 / "—", table shows empty message.
- Eval-DB read failure → rows render with `eval_status: not_evaluated`; page still
  loads (non-fatal).
- Frontend react-query error → inline error banner with retry; loading → spinner.

## Testing

- Backend pytest: summary math (rates, avg, division-by-zero → `None`),
  `status`/`evaluated` filter combinations, pagination, not-evaluated/failed
  classification. Temp OUTPUT_DIR with fixture images + temp evals DB.
- Contract: `AnalysisResponse` matches `types/analysis.ts` (api-contract-checker).

## Out of scope

- No changes to Gallery deep-linking.
- No new evaluation triggering from this page (read-only view of existing evals).
- No CSV/export (can be added later).

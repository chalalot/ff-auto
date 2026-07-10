# Pipeline selector + JSON-introspected parameter panel

**Date:** 2026-06-28
**Status:** Approved (design)
**Area:** Image generation UX (`WorkspacePage`) + pipeline subsystem + workspace API

## Problem

The generation UI lets users tune a fixed, hardcoded set of knobs (variations,
strength, width/height, seed). Two gaps:

1. **No pipeline selection.** The `GenerationPipeline` registry already exists
   (`image.subject_environment`, `image.unified`, plus video stubs), and
   `pipeline_type` already threads end-to-end, but the user can't choose a
   pipeline before clicking Process — it's always the default.
2. **Config is detached from the actual workflow.** The real tunable values
   live in `workflow.json` node inputs (LoRA `strength_model`, the latent
   *input* resolution on `EmptySD3LatentImage`, the *output* resolution on
   `ImageScale`, sampler `steps`/`cfg`/`sampler_name`, etc.). The UI exposes
   only a conflated width/height (which actually maps to output res, with the
   latent auto-halved) and a strength field whose default (`0.8`) doesn't even
   match the JSON (`1.15`). Users can't temporarily adjust the genuine workflow
   parameters per run.

This app exists to raise the user's automation rate, so the UI should *detect*
the tunable inputs from the loaded workflow JSON and let users temporarily
override them per run, without editing the JSON file.

## Goals

- Select the image (and, visibly-but-disabled, video) pipeline before Process.
- Auto-populate a "Workflow Parameters" menu from the selected pipeline's
  workflow JSON (full introspection of editable inputs).
- Let users temporarily override those values per run; nothing is persisted to
  the JSON file on disk.
- Preserve current behavior exactly when no overrides are sent (direct API
  callers and existing tests unaffected).

## Non-goals

- Implementing video generation (`build_workflow` for the video stubs). Video
  pipelines appear in the selector as disabled / "coming soon".
- Persisting overrides to `workflow.json` or to server-side presets.
- Enum-aware controls (e.g. a dropdown of valid `sampler_name` values). String
  inputs render as text fields. Can be a later enhancement via ComfyUI
  `object_info`.

## Decisions (from brainstorming)

| # | Decision |
|---|----------|
| Param detection | **Full introspection** — expose every editable (non-wiring) node input, no curation. |
| UI structure | **Split app-level vs workflow-node params** — single source of truth, no duplicated controls. |
| Seed authority | **App Seed strategy owns seed** — seed inputs shown but locked in the panel. |
| Video scope | **Image now, video disabled** in the selector ("coming soon"). |
| Default values | **JSON is the source of truth** — panel pre-fills from the raw JSON; effective UI defaults shift to the JSON's real values (e.g. strength `0.8 → 1.15`, output `1024×1600 → 1024×1536`, input res becomes the JSON's explicit `512×768`). What-you-see = what-runs. |
| Scope | One spec / one plan. |

## Architecture

### Component 1 — Pipeline metadata

Add two class attributes to `GenerationPipeline` (`backend/pipelines/base.py`):

- `label: str` — human-friendly name (e.g. "Subject + Environment").
- `available: bool = True` — whether the pipeline can actually run. Video stubs
  set `available = False`.

New helper `pipelines_metadata()` in `base.py` returns, for every registered
pipeline, `{pipeline_type, media_type, label, available}`.

New endpoint (`backend/api/workspace.py`):

```
GET /workspace/pipelines  →  List[{pipeline_type, media_type, label, available}]
```

The existing `GET /workspace/image-pipelines` stays for back-compat.

### Component 2 — Parameter introspection

Add to `GenerationPipeline`:

- `load_template(self) -> dict` — returns the raw workflow graph. Base raises
  `NotImplementedError`; `ComfyImagePipeline` returns `_load_workflow_json()`.
- `describe_parameters(self) -> list[NodeParams]` — concrete on the base: calls
  `load_template()` and introspects.

Introspection rules:

- **Editable input** = a node input whose value is **not a list**. List values
  are node connections (wiring, e.g. `["129", 0]`) and are excluded.
- **Type** inferred from the Python value: `bool → "boolean"`, `int →
  "integer"`, `float → "number"`, otherwise `"string"`.
- **Locked** inputs are returned (so the UI can show them greyed) but flagged
  `locked: true` with a `locked_reason`. Locked keys and reasons:
  - `seed`, `noise_seed` → "Controlled by the Seed strategy"
  - `text` → "Set from the generated prompt"
  - `lora_name` → "Controlled by the LoRA selector"
  - `device` → "Controlled by deployment (COMFYUI_CLIP_DEVICE)"
- **Node title** = `node["_meta"]["title"]` if present, else `class_type`.
- Node order = JSON insertion order (stable, ComfyUI export order).

New endpoint:

```
GET /workspace/pipelines/{pipeline_type}/parameters
  → { pipeline_type,
      nodes: [ { node_id, class_type, title,
                 inputs: [ {key, value, type, locked, locked_reason?} ] } ] }
```

Validation: `pipeline_type` must resolve in the registry (else 400) and be
`available` (else 400). Reuses the existing pipeline-validation pattern.

### Component 3 — Override application

New per-run channel: `workflow_overrides: { node_id: { input_key: value } }`.

Threading (all default to `{}`, fully back-compatible):

```
ProcessImageConfig (frontend type)
  → ProcessImageRequest / ProcessBatchRequest (Pydantic, workflow_overrides: dict = {})
  → api route (process / process_batch)
  → dispatch_processing / dispatch_batch (kwarg)
  → process_image_task (Celery kwarg)
  → async_process_image
  → client.generate_image(workflow_overrides=...)
  → GenerationInputs.workflow_overrides
  → ComfyImagePipeline.build_workflow → apply_overrides(workflow_data, overrides)  [LAST step]
```

`apply_overrides(workflow_data, overrides)` (shared, on the base):

- For each `node_id → {key: value}`: skip if node absent, skip locked keys, skip
  keys not already present as a non-list input on that node.
- **Type-coerce** the incoming value to the type of the existing JSON value
  (`int`/`float`/`bool`/`str`) so `"8"` becomes `8`, etc.
- Applied **last** in `build_workflow`, after the legacy semantic patching
  (`_patch_clip_loader`, prompt injection, LoRA, `_patch_workflow_dimensions`,
  `_patch_sampler_seeds`). Because it runs last and the frontend sends the full
  panel state, the panel is authoritative; when `overrides` is empty, behavior
  is byte-for-byte identical to today. The legacy patch functions are **not**
  removed (low risk, existing tests stay green).

### Component 4 — Frontend UI (`WorkspacePage`)

- **App settings** (existing controls, mostly unchanged): pipeline selector
  (new), persona, vision model, variations, seed strategy, LoRA selector.
  Remove the `clip_model_type` control — it becomes `CLIPLoader.type` in the
  panel. Remove the width/height/strength controls — they become workflow
  params.
- **Pipeline selector**: a grouped `Select` (Image group selectable; Video group
  disabled with "coming soon"). On change → fetch parameters, reset the panel.
- **Workflow Parameters** (new section): grouped by node (collapsible), one
  control per editable input (number input for integer/number, text for string,
  switch for boolean). Locked inputs are disabled with a tooltip showing
  `locked_reason`. A **Reset to JSON defaults** button restores fetched values.
- On Process, the panel's current values are sent as `workflow_overrides`
  (keyed by `node_id` → `{key: value}`), excluding locked inputs.

New API client methods (`frontend/src/api/workspace.ts`):
`getPipelines()`, `getPipelineParameters(pipelineType)`.

New types (`frontend/src/types/index.ts`): `PipelineInfo`,
`WorkflowParamInput`, `WorkflowParamNode`, `WorkflowParameters`; extend
`ProcessImageConfig` with `workflow_overrides?: Record<string, Record<string, unknown>>`.

## Data flow (happy path)

1. UI loads → `GET /workspace/pipelines` → renders selector.
2. User picks `image.subject_environment` → `GET
   /workspace/pipelines/image.subject_environment/parameters` → panel renders
   from JSON values.
3. User bumps `LoraLoaderModelOnly.strength_model` to `1.3`, leaves the rest.
4. Process → POST with `pipeline_type` + `workflow_overrides`
   `{"125": {"strength_model": 1.3}, "120": {...}, "131": {...}, "128": {...}}`
   (full editable panel state).
5. Task → `generate_image` → `build_workflow` does legacy patching then
   `apply_overrides` overwrites with the panel state → ComfyUI runs with the
   panel's values; seed still per-variation from the app strategy.

## Error handling

- Unknown / unavailable `pipeline_type` on either GET endpoint → HTTP 400.
- `apply_overrides` silently ignores unknown nodes / missing keys / locked keys
  (defensive: a stale panel must never 500 a generation). Type-coercion failures
  fall back to leaving the original value and log a warning.
- Frontend: if `getPipelineParameters` fails, show an inline error in the panel
  and keep Process enabled with no overrides sent — generation then falls back
  to the pipeline's legacy built-in defaults (today's behavior), not the JSON
  values, since the panel never loaded.

## Testing (TDD)

**Backend unit (`tests/`):**
- `describe_parameters`: excludes list (wiring) inputs; includes scalars; marks
  locked keys with reasons; infers integer/number/boolean/string; uses
  `_meta.title`.
- `apply_overrides`: applies editable keys; skips locked keys; skips
  unknown nodes / absent keys; coerces `"8"`→`8`, `"1.3"`→`1.3`.
- `build_workflow` with `workflow_overrides`: override wins over
  `_patch_workflow_dimensions` / strength; locked `seed`/`text`/`lora_name`
  untouched; empty overrides ⇒ unchanged vs today.
- `pipelines_metadata` / `available`: video pipelines `available=False`.
- API: `GET /workspace/pipelines` shape; `GET
  /workspace/pipelines/{type}/parameters` 200 for image, 400 for unknown, 400
  for video; `process` / `process_batch` thread `workflow_overrides` into
  dispatch.
- Threading: `dispatch_processing` and `async_process_image` forward
  `workflow_overrides` to `generate_image`.

**Frontend:** `tsc -b` clean (project's existing FE check; no component test
runner configured).

**Isolation:** run backend tests in the disposable container with read-only
source/test mounts and no data-dir mounts (per project memory).

## Risks

- **Default value shift** (strength/output/input res now from JSON) — approved;
  it's the intended consequence of JSON-as-source-of-truth and keeps
  what-you-see = what-runs.
- Model-filename inputs are editable (full introspection); a bad value would
  fail the ComfyUI run, not the API. Acceptable per the "raw power" choice.
- `WorkspacePage.tsx` is already large (~88K); the panel should be extracted
  into a focused child component (`WorkflowParametersPanel`) to avoid growing it
  further.

# Image-to-Prompt Run Trace Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a read-only, live-updating run trace for the image-to-prompt pipeline, showing Vision observation, Analyst, and Turbo Engineer inputs, exact rendered LLM messages, outputs, timing, and failures.

**Architecture:** Persist one `PipelineRun` and ordered `PipelineStep` rows in PostgreSQL. A recorder context owns lifecycle updates and a context-local LiteLLM callback captures rendered provider messages without parsing logs. FastAPI exposes one trace endpoint, and a dedicated React route polls it until the run reaches a terminal state.

**Tech Stack:** Python, SQLAlchemy 2, Alembic, FastAPI, Celery, PostgreSQL JSONB, React, TypeScript, React Query, Vitest, jsdom, Testing Library.

## Global Constraints

- Keep the first version read-only; do not add editing, replay, retry, workflow authoring, storyboard tracing, or ComfyUI tracing.
- Store trace payloads directly in PostgreSQL JSONB/Text columns; do not add object storage or an external observability service.
- Capture exact rendered LLM messages when under the configured payload limit; mark oversized values with truncation metadata.
- Never persist provider credentials, authorization headers, or unrelated secret values.
- Poll every 1-2 seconds while a run is queued or running and stop polling after success or failure.
- Preserve existing task and image-generation behavior when trace persistence is unavailable.

---

## File Map

Create:

- `backend/database/pipeline_runs_storage.py` - transactional CRUD and lifecycle operations for runs and steps.
- `backend/services/pipeline_trace.py` - recorder context, payload normalization, truncation, and LiteLLM callback capture.
- `backend/api/pipeline_runs.py` - trace retrieval route and response serialization.
- `frontend/src/pages/PipelineRunPage.tsx` - dedicated read-only trace page.
- `frontend/src/components/pipeline/PipelineRunTimeline.tsx` - ordered step status display.
- `frontend/src/components/pipeline/PipelineStepInspector.tsx` - selected-step payload inspector.
- `frontend/src/hooks/usePipelineRun.ts` - React Query polling hook.
- `frontend/src/types/pipeline.ts` - frontend trace contracts.
- `frontend/vitest.config.ts` - frontend test environment configuration.
- `frontend/src/test/setup.ts` - Testing Library and jsdom setup.
- `tests/database/test_pipeline_runs_storage.py` - persistence and lifecycle tests.
- `tests/test_pipeline_trace.py` - recorder and callback tests.
- `tests/test_api_pipeline_runs.py` - endpoint tests.
- `frontend/src/pages/PipelineRunPage.test.tsx` - page and polling-state tests.
- `frontend/src/components/pipeline/PipelineStepInspector.test.tsx` - payload rendering tests.

Modify:

- `backend/database/models.py` - add `PipelineRun` and `PipelineStep` SQLAlchemy models.
- `backend/database/alembic/versions/0005_pipeline_run_traces.py` - create the two tables and indexes.
- `backend/tasks.py` - pass the run ID into `process_image_task`, set trace context around each workflow stage, and finalize the run.
- `backend/services/image_processing.py` - create a run before dispatch, return its ID, and expose it in active-task metadata.
- `backend/models/workspace.py` - add `run_id` to dispatch and active-task response models where applicable.
- `backend/api/workspace.py` - return `run_id` from single and batch dispatch and register the trace router.
- `backend/main.py` - import and include `pipeline_runs.router` with prefix `/api/pipeline-runs`.
- `frontend/src/api/workspace.ts` - return dispatch run IDs and add trace retrieval.
- `frontend/src/api/pipeline.ts` - add the typed trace GET client.
- `frontend/package.json` and `frontend/package-lock.json` - add the frontend test script and minimal test dependencies.
- `frontend/src/App.tsx` - add `/pipeline-runs/:runId` under the existing layout.
- `frontend/src/pages/WorkspacePage.tsx` - link active tasks and newly dispatched jobs to the trace page.
- `frontend/src/types/index.ts` - add `run_id` to dispatch/task types if local types remain centralized there.
- `tests/test_pipelines_api.py` and `tests/test_workflow_files.py` - assert run IDs are threaded through dispatch and worker calls.

---

### Task 1: Add Trace Database Models and Storage

**Files:**
- Create: `backend/database/pipeline_runs_storage.py`
- Modify: `backend/database/models.py`
- Create: `backend/database/alembic/versions/0005_pipeline_run_traces.py`
- Test: `tests/database/test_pipeline_runs_storage.py`

**Interfaces:**
- `PipelineRunsStorage.create_run(pipeline_name: str, input_payload: dict, project_id: str | None, created_by_member_id: str | None) -> str`
- `PipelineRunsStorage.create_step(run_id: str, step_key: str, sequence: int) -> str`
- `PipelineRunsStorage.start_step(step_id: str, input_payload: dict | None, system_prompt: str | None, rendered_context: list | dict | None, model_name: str | None) -> None`
- `PipelineRunsStorage.append_llm_call(step_id: str, call_payload: dict) -> None`
- `PipelineRunsStorage.complete_step(step_id: str, output_payload: dict | list | str | None, usage: dict | None) -> None`
- `PipelineRunsStorage.fail_step(step_id: str, error: dict, partial_output: object | None) -> None`
- `PipelineRunsStorage.complete_run(run_id: str, final_output: dict | None) -> None`
- `PipelineRunsStorage.fail_run(run_id: str, error: dict) -> None`
- `PipelineRunsStorage.get_run_with_steps(run_id: str) -> dict | None`

- [ ] **Step 1: Write failing storage tests**

Create tests that use the existing `migrated_engine` and `clean_tables` fixtures. Assert that a created run returns a stable string ID, steps are ordered by `sequence`, lifecycle timestamps are set, JSON payloads round-trip, and a missing run returns `None`.

```python
def test_run_and_steps_round_trip(clean_tables):
    storage = PipelineRunsStorage()
    run_id = storage.create_run("image_to_prompt", {"image_path": "ref.png"}, None, None)
    analyst_id = storage.create_step(run_id, "analyst", 2)
    vision_id = storage.create_step(run_id, "vision_observation", 1)
    storage.start_step(vision_id, {"prompt": "observe"}, None, None, "gpt-4o")
    storage.complete_step(vision_id, {"observation": "subject"}, {"input_tokens": 3})
    trace = storage.get_run_with_steps(run_id)
    assert [step["step_key"] for step in trace["steps"]] == ["vision_observation", "analyst"]
    assert trace["steps"][0]["output_payload"] == {"observation": "subject"}
```

- [ ] **Step 2: Run the focused tests and verify failure**

Run: `pytest tests/database/test_pipeline_runs_storage.py -q`

Expected: FAIL because the storage module, models, and migration do not exist.

- [ ] **Step 3: Add SQLAlchemy models**

Add `PipelineRun` and `PipelineStep` to `backend/database/models.py` using the existing `Base`, `Text`, `JSONB`, and `TIMESTAMP` conventions. Use string UUIDs as primary keys, a foreign key from `pipeline_steps.run_id` to `pipeline_runs.id`, a unique constraint on `(run_id, step_key)`, and indexes on `(run_id, sequence)` and `(status, updated_at)`.

- [ ] **Step 4: Add the Alembic migration**

Create revision `0005` with `pipeline_runs` and `pipeline_steps` tables, JSONB payload columns, nullable error/usage fields, status text columns, timestamps, foreign key, unique constraint, and the two indexes. Implement a matching `downgrade()` that drops indexes and tables in dependency order.

- [ ] **Step 5: Implement storage lifecycle methods**

Use `session_scope()` for each operation. Serialize exception data as JSON-compatible dictionaries. Set `started_at` only when a step transitions to `running`; set `finished_at` on success or failure. `get_run_with_steps()` must return a plain dictionary with JSON values and steps sorted by `sequence`.

- [ ] **Step 6: Run the focused tests and verify success**

Run: `pytest tests/database/test_pipeline_runs_storage.py -q`

Expected: PASS with all run, ordering, lifecycle, failure, and missing-record assertions passing.

- [ ] **Step 7: Commit the database slice**

```bash
git add backend/database/models.py backend/database/pipeline_runs_storage.py backend/database/alembic/versions/0005_pipeline_run_traces.py tests/database/test_pipeline_runs_storage.py
git commit -m "feat: persist pipeline run traces"
```

### Task 2: Build the Trace Recorder and LLM Capture Boundary

**Files:**
- Create: `backend/services/pipeline_trace.py`
- Modify: `backend/workflows/image_to_prompt_workflow.py`
- Test: `tests/test_pipeline_trace.py`

**Interfaces:**
- `PipelineTraceRecorder.start_run(...) -> PipelineTraceRecorder`
- `PipelineTraceRecorder.step(step_key: str, sequence: int, input_payload: dict | None = None) -> PipelineStepRecorder`
- `PipelineStepRecorder.capture_prompt(system_prompt: str | None, rendered_context: object | None, model_name: str | None) -> None`
- `PipelineStepRecorder.capture_output(output_payload: object, usage: dict | None = None) -> None`
- `PipelineStepRecorder.__enter__()` and `__exit__(...)`
- `current_trace_step: ContextVar[PipelineStepRecorder | None]`
- `TraceLiteLLMCallback` - reads `current_trace_step`, normalizes callback request/response data, and records rendered messages without credentials.

- [ ] **Step 1: Write failing recorder tests**

Test successful and failed context-manager exits, payload truncation markers, callback capture of `kwargs["messages"]`, response capture, and removal of credential-like keys such as `api_key` and `authorization`.

```python
def test_failed_step_is_persisted_with_error(fake_storage):
    recorder = PipelineTraceRecorder(fake_storage, "run-1")
    with pytest.raises(ValueError):
        with recorder.step("analyst", 2, {"observation": "x"}):
            raise ValueError("model failed")
    fake_storage.fail_step.assert_called_once()
```

- [ ] **Step 2: Run the focused tests and verify failure**

Run: `pytest tests/test_pipeline_trace.py -q`

Expected: FAIL because the recorder and callback do not exist.

- [ ] **Step 3: Implement payload normalization and truncation**

Add a configurable byte/character limit in `pipeline_trace.py`. Normalize strings, dictionaries, lists, and provider callback objects to JSON-safe values. When a value exceeds the limit, return an object containing the truncated value, `truncated: true`, and `original_length`.

- [ ] **Step 4: Implement the recorder context manager**

Create the run and step lifecycle calls through `PipelineRunsStorage`. Set the context variable on entry, capture output on normal exit, capture exception type/message and partial output on error, reset the context variable in `finally`, and treat storage errors as warnings that do not replace the workflow exception. Use `append_llm_call()` for each provider request/response so multiple Turbo LLM calls remain inspectable within one step.

- [ ] **Step 5: Implement the LiteLLM callback**

Register one process-level callback compatible with the existing LiteLLM `success_callback` and `failure_callback` settings. Read the active step from the context variable, extract `messages`, model, usage, and response content, remove secret fields, and append the normalized call record to the step's rendered context/output metadata. Do not print the full request to logs.

- [ ] **Step 6: Install the callback without changing non-traced behavior**

Update `ImageToPromptWorkflow._get_llm()` so the callback is installed once per worker process while existing telemetry suppression remains unchanged. Keep the workflow's cached LLM behavior. Add a small helper around `_observe`, `_analyze`, and `_enhance` so the active recorder step is set while each operation runs.

- [ ] **Step 7: Run the focused tests and verify success**

Run: `pytest tests/test_pipeline_trace.py tests/test_image_to_prompt_agent.py -q`

Expected: PASS, including the existing deterministic workflow tests.

- [ ] **Step 8: Commit the recorder slice**

```bash
git add backend/services/pipeline_trace.py backend/workflows/image_to_prompt_workflow.py tests/test_pipeline_trace.py
git commit -m "feat: capture pipeline step prompts and outputs"
```

### Task 3: Create Runs at Dispatch and Finalize Them in Celery

**Files:**
- Modify: `backend/services/image_processing.py`
- Modify: `backend/tasks.py`
- Modify: `backend/models/workspace.py`
- Modify: `backend/api/workspace.py`
- Test: `tests/test_pipelines_api.py`
- Test: `tests/test_workflow_files.py`

**Interfaces:**
- `ImageProcessingService.dispatch_processing(...) -> dict[str, str | None]` returns `{task_id, run_id}`.
- `async_process_image(..., run_id: str | None, ...) -> dict`.
- `PipelineRun` lifecycle receives the existing task parameters as the root input payload.

- [ ] **Step 1: Extend dispatch tests with run IDs**

Update dispatch mocks so `dispatch_processing()` creates a trace before `send_task`, passes `run_id` in Celery kwargs, and returns both IDs. Assert Redis task metadata contains `run_id`.

- [ ] **Step 2: Run the dispatch tests and verify failure**

Run: `pytest tests/test_pipelines_api.py tests/test_workflow_files.py -q`

Expected: FAIL because dispatch currently returns only `task_id` and does not pass `run_id`.

- [ ] **Step 3: Create the run before Celery dispatch**

In `ImageProcessingService.dispatch_processing()`, build a JSON-safe root input from the actual image path, brief, persona, workflow settings, model, variation count, and project/member IDs. Call `create_run()` before `send_task()`, pass the returned ID as `run_id`, and include it in Redis metadata. If trace creation raises, log a warning, continue dispatch with `run_id=None`, and preserve the existing task behavior.

- [ ] **Step 4: Add run ID response contracts**

Change `DispatchResponse` to include optional `run_id`. Change `BatchDispatchResponse` to include parallel optional `run_ids`. Keep existing `task_id` and `task_ids` fields unchanged.

- [ ] **Step 5: Add step lifecycle around `async_process_image()`**

When `run_id` is present, create ordered steps for Vision observation, Analyst, and Turbo Engineer. Mark the parent run running, invoke the workflow with the trace recorder, persist the final generated prompt response, and mark the run succeeded. On both handled refusal/empty-response failures and unexpected exceptions, mark the relevant step and parent run failed before preserving the existing return/raise behavior. When `run_id` is absent, skip trace writes and execute the existing workflow path unchanged.

- [ ] **Step 6: Run the dispatch and workflow tests**

Run: `pytest tests/test_pipelines_api.py tests/test_workflow_files.py tests/test_image_to_prompt_agent.py -q`

Expected: PASS with existing behavior preserved and run IDs asserted.

- [ ] **Step 7: Commit the Celery integration slice**

```bash
git add backend/services/image_processing.py backend/tasks.py backend/models/workspace.py backend/api/workspace.py tests/test_pipelines_api.py tests/test_workflow_files.py
git commit -m "feat: trace image-to-prompt task execution"
```

### Task 4: Add the Trace Retrieval API

**Files:**
- Create: `backend/api/pipeline_runs.py`
- Modify: `backend/main.py`
- Create: `tests/test_api_pipeline_runs.py`

**Interfaces:**
- `GET /api/pipeline-runs/{run_id}` returns `{run, steps}` with ordered steps.
- Missing IDs return HTTP 404 with detail `Pipeline run not found`.
- In-progress and failed runs return HTTP 200 with their current persisted state.

- [ ] **Step 1: Write failing API tests**

Seed a run with queued/running/succeeded and failed steps through the storage fixture. Assert status 200, sequence ordering, payload fields, and status 404 for an unknown ID.

- [ ] **Step 2: Run the endpoint tests and verify failure**

Run: `pytest tests/test_api_pipeline_runs.py -q`

Expected: FAIL because the route and router registration do not exist.

- [ ] **Step 3: Implement the route**

Add a router that obtains `PipelineRunsStorage`, calls `get_run_with_steps()`, raises `HTTPException(404, detail="Pipeline run not found")` when absent, and returns the normalized dictionary. Register it under `/api/pipeline-runs` using the same router inclusion pattern as the existing API modules.

- [ ] **Step 4: Run API tests**

Run: `pytest tests/test_api_pipeline_runs.py -q`

Expected: PASS for in-progress, successful, failed, and missing traces.

- [ ] **Step 5: Commit the API slice**

```bash
git add backend/api/pipeline_runs.py backend/main.py tests/test_api_pipeline_runs.py
git commit -m "feat: expose pipeline run traces"
```

### Task 5: Build the Dedicated Run-Detail Page

**Files:**
- Create: `frontend/src/types/pipeline.ts`
- Create: `frontend/src/api/pipeline.ts`
- Create: `frontend/src/hooks/usePipelineRun.ts`
- Create: `frontend/src/components/pipeline/PipelineRunTimeline.tsx`
- Create: `frontend/src/components/pipeline/PipelineStepInspector.tsx`
- Create: `frontend/src/pages/PipelineRunPage.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/package.json`
- Modify: `frontend/package-lock.json`
- Create: `frontend/vitest.config.ts`
- Create: `frontend/src/test/setup.ts`
- Test: `frontend/src/pages/PipelineRunPage.test.tsx`
- Test: `frontend/src/components/pipeline/PipelineStepInspector.test.tsx`

**Interfaces:**
- `PipelineRunTrace`, `PipelineStepTrace`, and `PipelineRunStatus` mirror the API response.
- `usePipelineRun(runId: string)` returns the latest trace, loading state, and refresh error; its `refetchInterval` returns `1500` for `queued`/`running` and `false` otherwise.
- `PipelineRunTimeline` accepts ordered steps and `selectedStepId`/ `onSelect`.
- `PipelineStepInspector` accepts one step and renders read-only payload sections.

- [ ] **Step 1: Add the minimal frontend test harness**

Run: `cd frontend && npm install --save-dev vitest jsdom @testing-library/react @testing-library/jest-dom`

Add a `test` script with value `vitest`, configure `vitest.config.ts` with the `jsdom` environment and `src/test/setup.ts`, and import `@testing-library/jest-dom/vitest` from the setup file. Do not add a second test framework.

- [ ] **Step 2: Write failing component tests**

Mock the trace API and assert the page renders the run header, all three ordered steps, the selected step's Input/System Prompt/Context/Output/Metadata sections, and a failed-step error. Assert the query configuration stops polling for `succeeded` and `failed` traces.

- [ ] **Step 3: Run frontend tests and verify failure**

Run: `cd frontend && npm test -- --run PipelineRunPage.test.tsx PipelineStepInspector.test.tsx`

Expected: FAIL because the types, hook, page, and components do not exist.

- [ ] **Step 4: Add typed trace API and polling hook**

Create `frontend/src/api/pipeline.ts` with `getRun(runId)` and use it from `usePipelineRun`. Preserve the last successful query data when a refresh fails, exposing the error separately for the page status line.

- [ ] **Step 5: Implement the timeline**

Render the step sequence with stable status icons/colors and accessible buttons. Select the first `running` step automatically; otherwise select the first step on initial load. Keep fixed dimensions for status controls so polling updates do not shift layout.

- [ ] **Step 6: Implement the inspector**

Render Input, System Prompt, Context, Output, and Metadata as read-only sections. Use a scrollable `<pre>` viewer for structured values, JSON stringify objects with two-space indentation, and show an explicit `Truncated payload` marker when metadata indicates truncation.

- [ ] **Step 7: Implement the page and route**

Create the dedicated page with run status, duration, timeline, selected-step inspector, refresh error, and a terminal-state indicator. Add `/pipeline-runs/:runId` inside the existing `Layout` route tree.

- [ ] **Step 8: Run frontend tests and lint**

Run: `cd frontend && npm test -- --run PipelineRunPage.test.tsx PipelineStepInspector.test.tsx && npm run lint`

Expected: PASS with no new lint errors.

- [ ] **Step 9: Commit the run page slice**

```bash
git add frontend/package.json frontend/package-lock.json frontend/vitest.config.ts frontend/src/test/setup.ts frontend/src/types/pipeline.ts frontend/src/api/pipeline.ts frontend/src/hooks/usePipelineRun.ts frontend/src/components/pipeline frontend/src/pages/PipelineRunPage.tsx frontend/src/App.tsx frontend/src/pages/PipelineRunPage.test.tsx frontend/src/components/pipeline/PipelineStepInspector.test.tsx
git commit -m "feat: add pipeline run trace page"
```

### Task 6: Link Workspace Jobs to Their Trace

**Files:**
- Modify: `frontend/src/api/workspace.ts`
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/pages/WorkspacePage.tsx`
- Modify: `backend/services/image_processing.py`
- Modify: `backend/api/workspace.py`
- Test: `tests/test_pipelines_api.py`

- [ ] **Step 1: Write failing link tests**

Assert single dispatch returns `task_id` and `run_id`, batch dispatch returns parallel ID arrays, and active-task metadata exposes `run_id` when present.

- [ ] **Step 2: Run the link tests and verify failure**

Run: `pytest tests/test_pipelines_api.py -q`

Expected: FAIL until response models, API clients, and task cards are updated.

- [ ] **Step 3: Update frontend dispatch contracts**

Add `run_id`/`run_ids` to the API response types and retain the IDs in the workspace mutation result. For single-image dispatch, navigate to `/pipeline-runs/{run_id}` after the task is accepted; for batch dispatch, keep the existing workspace behavior and expose a trace link per active task.

- [ ] **Step 4: Add trace links to active task cards**

Read `run_id` from the active task object and add an icon+text link to the dedicated page. Do not make the entire card a link because existing Cancel/Retry controls must remain independent.

- [ ] **Step 5: Run backend and frontend checks**

Run: `pytest tests/test_pipelines_api.py -q` and `cd frontend && npm run lint`.

Expected: PASS with the existing dispatch and task controls unchanged.

- [ ] **Step 6: Commit the workspace integration slice**

```bash
git add backend/services/image_processing.py backend/api/workspace.py frontend/src/api/workspace.ts frontend/src/types/index.ts frontend/src/pages/WorkspacePage.tsx tests/test_pipelines_api.py
git commit -m "feat: link workspace jobs to run traces"
```

### Task 7: End-to-End Verification and Handoff

**Files:**
- Modify only if verification finds a concrete defect in the files above.

- [ ] **Step 1: Validate migration and database tests**

Run: `docker compose -f docker-compose.test.yml up -d` then `pytest tests/database/test_pipeline_runs_storage.py tests/test_api_pipeline_runs.py -q`.

Expected: PASS against the throwaway PostgreSQL database and Alembic head `0005`.

- [ ] **Step 2: Validate backend regression coverage**

Run: `pytest tests/test_image_to_prompt_agent.py tests/test_pipelines_api.py tests/test_workflow_files.py tests/test_pipeline_trace.py -q`.

Expected: PASS with no changes to existing image-to-prompt output behavior.

- [ ] **Step 3: Validate frontend checks**

Run: `cd frontend && npm test -- --run PipelineRunPage.test.tsx PipelineStepInspector.test.tsx && npm run lint && npm run build`.

Expected: PASS for focused tests, lint, and production build.

- [ ] **Step 4: Manually verify live behavior**

Start the existing backend worker/API and frontend. Dispatch one image with one variation and confirm the browser navigates to the run page, Vision becomes succeeded before Analyst starts, Analyst context/output appears, Turbo output is an array, polling stops after terminal status, and a forced model failure leaves the failed step readable.

- [ ] **Step 5: Inspect the final diff**

Run: `git diff main...HEAD --check` and `git status --short`.

Expected: no whitespace errors, no unexpected modified files, and all trace changes limited to the approved scope.

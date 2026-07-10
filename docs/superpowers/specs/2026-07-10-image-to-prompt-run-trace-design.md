# Image-to-Prompt Run Trace Design

## Status

Approved design. Implementation is intentionally limited to a read-only first
version.

## Intent

Make the image-to-prompt pipeline debuggable while it is running and after it
finishes. Operators should be able to see the ordered execution, the exact
data passed between stages, the rendered LLM messages, and each stage's
result or failure without searching worker logs.

## Goals

- Create one trace for each image-to-prompt execution.
- Show live progress and completed runs in the application.
- Preserve the execution order and parent/child relationship.
- Capture exact rendered LLM messages for Analyst and Turbo Engineer calls.
- Capture inputs, outputs, model metadata, timing, and errors.
- Provide a dedicated read-only run-detail page.
- Use polling for live updates.
- Store trace payloads in the existing database for the first version.

## Non-goals

- Editing prompts or agent configuration from the trace page.
- Replaying or retrying an individual step.
- A visual workflow editor.
- Storyboard workflow tracing.
- ComfyUI tracing in the first version. ComfyUI is currently a separate
  downstream generation path and is not part of this workflow's execution.
- External observability services or object storage.

## Current Workflow Boundary

The first trace covers the current `ImageToPromptWorkflow.process` flow:

```text
Reference image or brief
  -> Vision observation
  -> Analyst agent
  -> Turbo Engineer agent
  -> Generated prompt variations
```

Vision observation is a model/tool stage, not a CrewAI agent. Analyst and Turbo
Engineer are CrewAI stages. Turbo variations remain one trace step with an
output array; they are not separate child steps in this version.

## Architecture

### Trace records

Add normalized records owned by the application database:

`PipelineRun`

- `id`
- `pipeline_name` (`image_to_prompt`)
- `status` (`queued`, `running`, `succeeded`, `failed`)
- `input_payload`
- `final_output`
- `started_at`
- `finished_at`
- `error`
- creation/update timestamps

`PipelineStep`

- `id`
- `run_id`
- `step_key` (`vision_observation`, `analyst`, `turbo_engineer`)
- `sequence`
- `status` (`queued`, `running`, `succeeded`, `failed`)
- `input_payload`
- `system_prompt`
- `rendered_context`
- `output_payload`
- `model_name`
- usage metadata when available
- `started_at`
- `finished_at`
- `error`
- creation/update timestamps

JSON payloads are stored directly in the database for the first version. The
API must return structured JSON and the UI must render large values in
scrollable viewers. Payload size limits must be explicit in the implementation;
truncation must be represented in metadata rather than silently losing data.
Exact capture is the default, but if a configured limit is exceeded the stored
value must include an explicit truncation marker and the original length.

### Recording lifecycle

The image-to-prompt orchestration creates the parent run before starting work.
Each stage is recorded with this lifecycle:

1. Insert a queued step.
2. Mark the step running immediately before execution.
3. Capture input and prompt snapshots before the model call.
4. Capture output, usage, and timing on success.
5. Capture exception type, message, and any partial output on failure.
6. Always finalize the step in a `finally` path.
7. Mark the parent run failed when a required step fails; otherwise mark it
   succeeded after all steps complete.

The recorder should be a small service or context manager so workflow code does
not duplicate status and timestamp handling. It must not depend on log parsing.

### Exact LLM context capture

The vision stage records the actual vision prompt and returned observation.

Analyst and Turbo Engineer records must capture the exact rendered messages sent
to the LLM, including system/backstory content, task instructions, prior
messages, expected output instructions, and tool definitions when present.
The exactness guarantee applies to values under the configured payload limit;
oversized values follow the explicit truncation rule above.

Instrumentation belongs at the CrewAI/LLM call boundary. The recorder should
also retain the workflow-level inputs used to construct the call, allowing a
trace to explain both the application intent and the final provider request.
Provider credentials, authorization headers, and unrelated secret values must
never be persisted.

## Backend API

Add an endpoint to retrieve a run and its ordered steps, for example:

```text
GET /api/pipeline-runs/{run_id}
```

The response includes the parent run, steps ordered by `sequence`, and the
selected payload fields. It must return an in-progress run without requiring
the worker to finish.

The endpoint must distinguish a missing run from a run that exists but has no
completed steps. Failed steps remain available for inspection.

The existing image-to-prompt dispatch path must return or associate the new
`run_id` with the worker task so the frontend can navigate to the trace page.

## Frontend

Add a dedicated run-detail route. The page contains:

- Pipeline name, run status, start time, duration, and refresh state.
- An ordered timeline for Vision observation, Analyst, and Turbo Engineer.
- Status indicators for queued, running, succeeded, and failed.
- Automatic selection of the currently running step.
- A read-only inspector with Input, System Prompt, Context, Output, and
  Metadata sections.
- Scrollable text/JSON viewers for large payloads.
- Error details for failed steps and access to all completed predecessors.

The page polls the trace endpoint every 1-2 seconds while the run is queued or
running. Polling stops after success or failure. Refresh errors should be shown
without erasing the last successfully loaded trace state.

## Error Handling

- A failure in one step stops the dependent pipeline stages.
- The failed step stores a useful error message and timestamps.
- The parent run records the terminal failure state.
- The API remains readable after failure.
- If trace persistence itself fails, the workflow error must still be logged;
  trace persistence must not convert a successful generation into a failed
  generation unless the application explicitly requires durable tracing.

## Security and Retention

This is an operator/debugging feature. Trace payloads can contain reference
image paths, user-provided briefs, prompts, tool input, and generated content.
The first version must:

- Avoid storing credentials and authorization headers.
- Avoid logging full provider requests outside the trace record.
- Apply explicit payload limits.
- Keep access behind the application's existing authentication boundary.
- Document that retention and deletion follow the existing application data
  policy.

## Testing

Backend tests should cover:

- Run and step creation with correct sequence.
- Running, success, and failure transitions.
- Persistence of exact prompt/context/output payloads.
- Parent failure when a required step fails.
- Retrieval of in-progress and failed traces.
- No credential fields persisted by the recorder.

Frontend tests should cover:

- Rendering ordered steps and statuses.
- Selecting a step and displaying its payload sections.
- Polling while active and stopping at a terminal status.
- Preserving the last trace when a refresh request fails.
- Rendering failed-step details.

## Rollout Boundary

Implement the trace model and recorder for the image-to-prompt pipeline first.
Verify the live run page with one image and one Turbo variation, then verify
multiple variations and failure cases. The data model should keep
`pipeline_name` and `step_key` generic so storyboard tracing can be added
without changing the read-only page contract.

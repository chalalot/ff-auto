# Plan — Skill-driven agentic prompt generation

> The *how*. Derived from
> [the spec](../specs/2026-07-09-skill-driven-prompt-agent-spec.md). Vertical slices —
> each an end-to-end thread verifiable against the spec. Every step cites its clause(s)
> and an explicit verification. Status: **DRAFT — awaiting confirmation (Phase 3 gate).**

## Global verification constraints (from project memory)

- **Never test against the live container.** Run in a disposable container; fixtures
  can pollute mounted data dirs.
- **Verify per-file**, not `pytest tests/` (full suite has ~24 pre-existing pollution
  failures).
- Frontend (if touched) verified with raw `./node_modules/.bin/tsc -b --force` (RTK
  mangles `tsc`).

## Slices

### P1 — Skill vendoring + `SkillReaderTool` (foundation)
*Satisfies:* S4 (consume-via-tool), enables S2/S3.
- Vendor `writing-image-prompts/` → `prompts/skills/writing-image-prompts/` (A2).
- Implement `SkillReaderTool(BaseTool)` in `backend/tools/`: `_run(ref_path)` rooted at
  the skill dir; traversal guard returns an error string (never raises, never escapes
  root); per-instance read-log (list of `(order, path)`).
- **Verify:** unit test — tool reads `SKILL.md` and `references/lighting/lighting.md`;
  `_run("../../../etc/passwd")` returns an error string and reads nothing; read-log
  records the two successful reads in order. *(No LLM — pure unit.)*

### P2 — Skill-driven Analyst, corrective (image path, through `process()`)
*Satisfies:* S1, S2, S3, S10, S12; parents I1, I4, C4, C6.
- Add the Analyst agent with `tools=[SkillReaderTool]`; keep programmatic vision
  (A11) producing the raw observation, fed to the Analyst.
- Analyst backstory instructs: walk 9 sections in order, open a map before any detail
  file, name skill-pattern violations + corrections, preserve subject/wardrobe/
  setting/pose intent (A1). `descriptive_prompt` = the improved analysis.
- Compute analysis once; reuse across `variation_count` (A7, S12).
- **Verify:** in a disposable container, `process(image=<off-center, flat-lit
  fixture>)` → assert `descriptive_prompt` names a composition/lighting rule and a
  correction differing from the raw reference (I1); assert the `SkillReaderTool`
  read-log shows ≥1 map and strictly fewer than all detail files (I4); refusal on a
  moderated image still raises the same error (S10).

### P3 — Enhancer: persona locks + persona-type format
*Satisfies:* S5, S6, S9; parents I2, I5, C2, C3.
- Thin Enhancer (no skill tool) assembles improved analysis → prompt using the persona
  type's `turbo_*` templates (locks + format only, A4); empty-template fallback keeps
  section format for `image.subject_environment` (A10, E5).
- Lock precedence: skill suggestion vs lock → lock wins (S6). MODE_FULL emits body
  string verbatim; MODE_PORTRAIT omits it (Matrix C).
- **Verify:** `process(image=<full-body fixture>)` → output contains `#Subject` and
  `#Environment`, parseable by `_split_subject_environment`, and the verbatim body
  string (I2); return keys/types unchanged and `caption_export_task` runs against it
  unmodified (I5).

### P4 — Brief-only + input validation (through `process()`)
*Satisfies:* S7, S8; parent I3.
- Add `brief` param; make `image_path` optional. Neither → `ValueError` **before** any
  vision/LLM call. Brief-only skips vision (S7); image+brief steers.
- **Verify:** `process(image_path=None, brief="a woman in a cafe")` → valid 2-section
  prompt, `reference_image is None`, no vision call made (I3); `process(None, None)`
  raises `ValueError` with no LLM call; `process(image, brief)` reflects both.

### P5 — Brief reachable through the product (Celery + API)
*Satisfies:* S8 end-to-end; A12.
- Thread `brief` through `async_process_image` / `process_image_task` and add the
  optional `brief` field to the generation entry endpoint + its request model.
  *(Use the `/new-endpoint` project skill for the model/router/client/test surface.)*
- **Verify:** submit a brief-only request via the API in a disposable container → a
  `generation_requests` row lands in `pending_review` with a valid prompt; API-contract
  check passes (backend model ↔ frontend type).

### P6 — Regenerate action
*Satisfies:* S11; parent C5; Matrix B.
- `GenerationRequestsStorage.regenerate_prompt(request_id, new_prompt)` (in-place
  `prompt` update, preserve `original_prompt`, guard `status == pending_review`);
  `regenerate_request_task`; `POST /generation-requests/{id}/regenerate`.
- **Verify:** regenerate a `pending_review` row → `prompt` changes, `original_prompt`
  unchanged (Matrix B happy cell); regenerate an `approved`/`dispatched`/`completed`/
  `failed`/`discarded` row → rejected, **row unmutated** (Matrix B reject cells).

### P7 — Brief-only headless (migration + no-image dispatch)  *(added after checkpoint; user-approved N2 amendment)*
*Satisfies:* S13; A15.
- Alembic `0004` makes `generation_requests.source_image_path` nullable; model updated.
- `ProcessImageRequest.image_path` optional + at-least-one validator; `dispatch_processing`
  skips `prepare_image` when no image (queues `dest_image_path=None`); thumbnail 404s a
  null-source row.
- **Verify:** null-source row persists; brief-only accepted, neither→422; thumbnail
  null-source→404; dispatch skips prepare. (5 tests, DB) ☑

### P8 — Brief textarea in the generate form  *(added after checkpoint)*
*Satisfies:* A12 (UI reachability).
- `brief?: string` on `ProcessImageConfig`; brief textarea in `WorkspacePage` (flows as
  image+brief). Brief-only *without an image* from this UI is not wired (dispatch is
  image-selection-gated) — reachable via API.
- **Verify:** `tsc -b --force` clean. ☑

## Traceability matrix

| Intent/Constraint | Spec clause(s) | Plan step(s) | Verification | Status |
|-------------------|----------------|--------------|--------------|--------|
| I1 (corrective analysis) | S1, S2, S10 | P2 | unit ☑; **live run ☑** — analysis prescribed "Correction: 50mm lens, f/5.6–f/8" while preserving subject/wardrobe/pose | ☑ |
| I2 (format + body preserved) | S5, S6 | P3 | base-instruction carries `#Subject`/`#Environment` + hourglass + hair lock ☑ (unit) | ☑ |
| I3 (brief-only works) | S7, S8, S13 | P4, P5, P7, P8 | process() brief-only + neither→ValueError ☑; threaded API→task→workflow+settings ☑; headless (nullable col + no-image dispatch + 422 + 404) ☑; brief textarea + tsc ☑ | ☑ |
| I4 (progressive disclosure provable) | S2, S3, S4 | P1, P2 | unit ☑; **live run ☑** — read-log: SKILL.md → camera-lens map → lighting map (3 of 64, maps-first) | ☑ |
| I5 (return shape unchanged) | S9, S12 | P3 | keys/types ☑ (stubbed-seam test); callers import unchanged ☑ | ☑ |
| C1 (CrewAI + tool) | S4 | P1 | skill only via tool, not concatenated ☑ | ☑ |
| C2 (locks + format) | S5, S6 | P3 | lock-wins + verbatim body string ☑ (unit) | ☑ |
| C3 (downstream unchanged) | S9 | P3 | `tasks`/`caption_export_task` import + kwargs unchanged ☑ | ☑ |
| C4 (multi-provider vision) | S10 | P2 | code ☑; **live ☑** — Gemini vision succeeded end-to-end; OpenAI 429 exercised the S10 error path | ☑ |
| C5 (regenerate) | S11 | P6 | Matrix B via HTTP (pending→202+dispatch; approved→409 no-mutate; missing→404) + task mutate/preserve ☑ | ☑ |
| C6 (skill fidelity) | S2 | P2 | task text ☑; **live ☑** — SKILL.md first, section maps before any detail file | ☑ |

- **Top-down:** every I1–I5 and C1–C6 has a row.
- **Bottom-up:** every clause S1–S12 appears; every plan step P1–P6 cites clauses.

---
*Phase 3 gate: every spec clause maps to ≥1 plan step; each step has an explicit
verification. On confirmation → Phase 4 (Build), one slice at a time.*

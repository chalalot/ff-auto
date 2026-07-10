# Spec — Skill-driven agentic prompt generation

> The *what*. Source of truth, derived from
> [the intent](2026-07-09-skill-driven-prompt-agent-intent.md). Each clause names its
> parent intent (I1–I5) or constraint (C1–C6). Status: **DRAFT — awaiting confirmation
> (Phase 2 gate).**

## Interfaces / modules (deep modules)

- **M1 — `SkillReaderTool`** (CrewAI `BaseTool`). One capability: *read one skill
  reference by its skill-relative path.*
  `_run(ref_path: str) -> str`. Roots every read at the vendored skill dir
  (`prompts/skills/writing-image-prompts/`, A2); refuses any path escaping that root
  (traversal guard) and returns an error string instead of raising; **appends each
  successful read's path to a per-call read-log** used to verify progressive
  disclosure (I4). Hides rooting, guarding, and logging behind a single "read a skill
  file" verb.

- **M2 — `ImageToPromptWorkflow.process(...)`** — extended signature, unchanged return
  shape:
  `process(image_path: Optional[str] = None, brief: Optional[str] = None, persona_name="Jennie", workflow_type="turbo", vision_model="gpt-4o", variation_count=1, clip_model_type="qwen_image") -> dict`.
  Returns `{reference_image, generated_prompt, generated_prompts, descriptive_prompt}`.

- **M3 — Skill-driven Analyst** (internal). Constructed with `tools=[SkillReaderTool]`.
  Consumes raw observation (from vision) and/or brief; walks the skill's 9 sections,
  discloses references progressively, and emits an **improved** structured analysis
  (named patterns + corrections). Exposed inside `process()` only as
  `analyze(observation?, brief?) -> improved_analysis`.

- **M4 — Enhancer/assembler** (internal, thin, **no skill tool**). Consumes the
  improved analysis + persona locks + persona-type `turbo_*` templates → final prompt
  in that persona type's format.

- **M5 — Regenerate** — `POST /generation-requests/{id}/regenerate` → Celery
  `regenerate_request_task(request_id)` → re-runs `process()` from the stored
  `source_image_path` + `settings` (+ stored `brief` if any) and updates the row's
  `prompt` in place.

## Behavioral clauses

| Clause | Parent | Behavior (input → output, incl. errors/edges) |
|--------|--------|-----------------------------------------------|
| **S1** | I1 | With an image, Analyst emits, for each photographic dimension (composition, lighting, lens/camera) where the reference violates a skill rule, both **the named violation** and **the corrected skill-endorsed choice**. Subject/wardrobe/setting/pose **intent is preserved** (A1) — only technique dimensions are corrected. |
| **S2** | I1, C6 | Analyst walks the skill's 9 sections in order and, per the skill's own rule, opens a section **map** (`references/<s>/<s>.md`) *before* any detail file; opens a detail file **only** for dimensions it judges relevant. |
| **S3** | I4 | Every `SkillReaderTool` read is recorded (path + order). A representative run's log shows **≥1 map read** and **strictly fewer than all** detail files. (Verified from the log; not a runtime hard-fail — A9.) |
| **S4** | C1, I4 | The skill is consumed **only** through `SkillReaderTool` progressive reads; the full skill text is **not** concatenated into the agent prompt up front. |
| **S5** | I2, C2 | Enhancer assembles using the selected persona type's `turbo_*` templates, so output preserves that type's format. For `#Subject`/`#Environment` persona types both headers are present and parseable by `_split_subject_environment`. When analysis = **MODE_FULL**, the hard-coded body string is emitted **verbatim**. |
| **S6** | I2, C2 | Persona locks live in the selected persona-**type** template *text* (e.g. `instagirl`'s verbatim hourglass body string; `dancer`'s "Ignore Analyst hair observations" + mandatory hair paragraph), **not** in per-persona-*name* config. The Enhancer applies them by using that type's `turbo_*` templates as its base instruction; on conflict between a skill suggestion and a template lock, **the lock wins**. The pre-existing `hair_color`/`hairstyle_options` `format_map` is a **no-op** (no `{placeholder}` exists in any template) and is kept as-is (A13). |
| **S7** | I3 | `process(image_path=None, brief="…")` runs the **brief-only** path: no vision call; Analyst *chooses* skill patterns for the brief (nothing to correct — A3); returns a valid prompt (both sections for section-type personas); `reference_image` is `None`. |
| **S8** | I3 | Input rule: **at least one** of `image_path`/`brief` required. Neither → `ValueError` raised **before any LLM/vision call**. `image+brief` → image grounds observation, brief steers intent. `image-only` → current behavior. |
| **S9** | I5 | `process()` returns unchanged keys/types: `reference_image` (`str\|None`), `generated_prompt` (`str`), `generated_prompts` (`list[str]`, length == `variation_count`), `descriptive_prompt` (`str`, now = improved analysis). Existing callers (`async_process_image`, `caption_export_task`) run **without signature changes**. |
| **S10** | I1, C4 | Vision read keeps OpenAI/Grok/Gemini support and the existing refusal/empty/error detection, raising the **same** error types/messages. The brief-only path skips vision entirely (so it can never raise a refusal). |
| **S11** | C5 | `regenerate(request_id)`: if status == `pending_review`, re-run `process()` from stored source+settings, **replace `prompt`**, **preserve `original_prompt`**, return the updated row. If status ∈ {`approved`,`dispatched`,`completed`,`failed`,`discarded`} → **reject without mutating** (A5/A6). |
| **S12** | I5 | For `variation_count = N`, the improved analysis is computed **once** and the Enhancer runs N independent passes over it (A7); `generated_prompts` has length N. |
| **S13** | I3 | **Brief-only headless:** `generation_requests.source_image_path` is nullable (migration). `POST /process` accepts a request with no `image_path` but a `brief` (neither → 422); dispatch skips `prepare_image`, sends `dest_image_path=None`, and the resulting queue row has `source_image_path = NULL`. The thumbnail endpoint returns 404 (not 500) for a null-source row. (A15) |

## State × operation matrix

### Matrix A — input combination × pipeline stage

|                    | image-only | brief-only | image+brief | **neither** |
|--------------------|------------|------------|-------------|-------------|
| validate inputs    | ok | ok | ok | **ValueError (pre-LLM)** |
| vision read        | run on image | **skipped** | run on image | n/a |
| skill exploration  | correct observed dims | choose dims for brief | correct + steer by brief | n/a |
| enhance / assemble | prompt | prompt | prompt | n/a |

### Matrix B — `regenerate` × request status

|            | pending_review | approved | dispatched | completed | failed | discarded |
|------------|----------------|----------|------------|-----------|--------|-----------|
| regenerate | re-run, replace `prompt`, keep `original_prompt` | reject, no mutate | reject, no mutate | reject, no mutate | reject, no mutate (A5) | reject, no mutate |

### Matrix C — Enhancer body slot × body-mode

|           | MODE_FULL | MODE_PORTRAIT |
|-----------|-----------|---------------|
| body slot | emit hard-coded body string **verbatim** | **omit** body slot entirely |

## Edge & error cases

- **E1:** Vision refusal / empty / tool-error on an image path → same exceptions as
  today; `async_process_image` logs a failed execution. Brief-only cannot reach E1.
- **E2:** `SkillReaderTool` given a missing file or an out-of-root path → returns an
  **error string** (agent continues); never raises, never reads outside the skill root.
- **E3:** Agent ignores progressive disclosure (opens no map / reads everything) →
  still produces output; **I4 fails at verification** for that run, not at runtime (A9).
- **E4:** Persona config empty (e.g. `Jennie` has blank `hair_color`/`hairstyles`) →
  existing fallbacks kept (`hairstyles → ["long loose hair"]`, empty hair color
  tolerated); locks degrade gracefully.
- **E5:** Persona-type templates empty (e.g. `dream`/`Jennie`) → base instruction is
  empty (the **pre-existing** behavior; no synthetic fallback is added — A10). Such
  personas carry no `#Subject`/`#Environment` guidance, and the downstream
  `SubjectEnvironmentPipeline` already single-node-falls-back when the prompt has no
  section headers. No crash.
- **E6:** `brief` is treated as **untrusted data**, wrapped so it cannot reprogram the
  agent's instructions (A8); a hostile brief cannot make the Analyst skip locks.
- **E7:** FACE_VISIBLE → micro-expression inventory required in analysis;
  FACE_NOT_VISIBLE → expression section omitted (existing analyst rule preserved).

## Assumptions & open decisions

| ID | Decision (value/rule) | Why this default | Alternative rejected | Confirmed? |
|----|-----------------------|------------------|----------------------|------------|
| A1 | Analyst corrects **only** technique (composition/lighting/lens); preserves subject/wardrobe/setting/pose intent | Matches "improved, not raw" without re-inventing the shoot | Full scene re-imagination | **yes** |
| A2 | Skill vendored at `prompts/skills/writing-image-prompts/` | Co-located with other `prompts/` assets | Outside-repo path (not deployable) | **yes** |
| A3 | Brief-only → Analyst *chooses* patterns (no correction step) | No reference to correct against | Fabricate a pseudo-reference | **yes** |
| A4 | `turbo_*` templates retained for **locks + format only**; craft superseded by skill | Preserves C2 guardrails | Delete templates (loses format/locks) | **yes** |
| A5 | `regenerate` allowed **only** in `pending_review` | Other states already sent to a provider; re-gen would desync | Also allow `failed` | no |
| A6 | `regenerate` mutates `prompt` in place, keeps `original_prompt` | Row already has both columns; simplest | Create a new request row | no |
| A7 | Improved analysis computed **once**, reused across N variations | Cost; variations should share the corrected read | Re-analyze per variation | no |
| A8 | `brief` wrapped as untrusted data in agent prompt | Prevent prompt-injection past the locks | Inline brief as instructions | no |
| A9 | I4 (progressive disclosure) verified from tool-log on representative runs, not a runtime assertion | Agent behavior can't be hard-enforced without breaking runs | Hard-fail if all files read | no |
| A10 | **Reconciled in verify:** empty persona-type templates → **empty** base instruction (pre-existing behavior, kept as-is); NO synthetic fallback added; format for those personas relies on the downstream single-node fallback | matches original behavior + "keep as-is"; adding a fallback would be new behavior | Synthesize a default assembler (new behavior); raise on empty template | **yes (reconciled)** |
| A11 | Design: **programmatic vision** (unchanged, multi-provider) produces the raw observation → fed to the skill-driven Analyst agent; the Analyst does **not** call vision itself | Keeps C4 + refusal detection robust; adds the agentic loop only where correction/selection happens | Give Analyst a VisionTool and let it loop (messier multi-provider, weaker refusal handling) | no |
| A12 | `brief` exposed as an optional field on the existing generation entry point + threaded through Celery, so brief-only is user-reachable (not just unit-testable) | I-intent says the workflow accepts a brief | process()-only (feature unreachable in product) | no |
| A13 | **Discovered in build:** `hair_color`/`hairstyle_options` `format_map` is a **no-op** (no `{placeholder}` in any template); per-persona-*name* hair config does not reach the prompt today. Locks are per-persona-*type* template text. Kept **as-is** — not wired in | C2 says "keep as-is"; wiring per-name hair into prompts is a behavior change beyond this effort's intent | Wire hair_color/hairstyles into the prompt (scope creep) | **yes (keep as-is)** |
| A14 | Regenerate is only eligible for `comfy_image` (image-prompt) rows; other providers → 409 | video prompts don't come from `ImageToPromptWorkflow`; re-running it would produce a wrong (image-style) prompt | Allow regenerate for any provider | no |
| A16 | **Found in live run:** the blocking crew seams (`_observe`/`_analyze`/`_enhance`) run via `asyncio.to_thread` because `process()` is awaited inside a running event loop and CrewAI forbids sync `kickoff()` there | fixes a real runtime bug (prod path too); keeps seams sync + stub-testable | `await crew.kickoff_async()` (would force async stubs / bigger churn) | **yes (fixed)** |
| A15 | **User-approved N2 amendment:** `generation_requests.source_image_path` made nullable via Alembic migration + no-image dispatch path, so brief-only is reachable through the queue | user chose full reachability over the sentinel hack | Sentinel placeholder (data pollution); defer (feature unreachable) | **yes** |

---
*Phase 2 gate: every intent covered by ≥1 clause; every clause names a parent; no
untraced magic values; matrices have no empty cells; register/matrix/clause agree;
user confirms.*

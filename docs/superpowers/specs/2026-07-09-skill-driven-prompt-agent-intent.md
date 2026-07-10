# Intent — Skill-driven agentic prompt generation

> The *why*. Durable. Captured BEFORE any spec or code.
> Status: **DRAFT — awaiting user confirmation (Phase 1 gate).**

## Outcome

Replace the current static LLM prompt pipeline (`ImageToPromptWorkflow`) with an
**agentic** one in which a skill-driven **Analyst** agent uses the
`writing-image-prompts` skill via *progressive disclosure* to not only describe a
reference image but **judge it against photographic standards and emit an *improved*
analysis** (better composition / lighting / camera than the raw reference), which a
thin **Enhancer** then assembles into the final prompt under the existing persona
locks and `#Subject`/`#Environment` format. The workflow also accepts a **text brief**
(with or without an image).

## For whom / why now

- **Actor:** operators generating KOL/persona images through the review queue. They
  today get prompts that faithfully mirror the reference — including its flaws — and
  cannot start from a text brief.
- **Trigger:** the reference images are often not well-shot. Faithful description
  propagates bad composition/lighting into every generated image. A skill encoding
  photographic best-practice already exists; wiring an agent to *apply* it (correct
  the reference, choose patterns deliberately) is the leverage.

## Constraints (non-negotiable)

- **C1 — Stack:** implemented on the existing **CrewAI** stack; the skill is consumed
  through a custom file-reading tool (`SkillReaderTool`) so the agent discloses
  references progressively rather than being handed all text up front.
- **C2 — Output contract preserved:** final prompt keeps the **`#Subject` /
  `#Environment` two-section format** and the **hard persona locks** (hair color,
  hairstyle list, MODE_FULL/PORTRAIT body rule, KOL demographic). The skill enriches
  *inside* these guardrails; it does not override them.
- **C3 — Downstream unchanged:** `process()` return shape and the Celery →
  `generation_requests` review-queue flow keep working; `caption_export_task` keeps
  working.
- **C4 — Multi-provider vision kept:** OpenAI / Grok / Gemini vision remain supported.
- **C5 — Autonomous:** the agent runs to completion (no interactive chat / streaming).
  A **regenerate** action re-runs it for a request.
- **C6 — Skill fidelity:** the agent follows the skill's own rules — walk sections in
  order, open a section *map* before any detail file, respect the skill's
  conflict/hierarchy rules.

## Non-goals (explicitly out of scope)

- **N1:** No interactive/chat UI, no streaming endpoint, no per-turn user steering.
- **N2 (amended 2026-07-09):** No change to ComfyUI generation or the
  LoRA/seed/dimension settings. ~~No review-queue schema change~~ — *amended:* a
  single schema change is now **in scope** — `generation_requests.source_image_path`
  becomes nullable — to make **brief-only headless** generation reachable through the
  queue (user-approved; see spec S13 / A15). No other schema changes.
- **N3:** No new vision *provider* (only reuse existing ones).
- **N4:** Not rewriting the `writing-image-prompts` skill content — it is consumed
  as-is (vendored into the repo).

## Success criteria (observable / testable)

- **I1:** Given a reference image whose composition/lighting violates a skill rule, the
  analyst's emitted analysis names the violation and states an improved
  composition/lighting/camera choice that differs from the raw reference. *(Check: run
  on a deliberately off-center / flat-lit fixture image; assert the analysis text
  names the correction, e.g. cites rule-of-thirds / a named lighting setup, and the
  documented improvement.)*
- **I2:** The final prompt still contains both `#Subject` and `#Environment` sections
  and, when MODE_FULL, the hard-coded body string. *(Check: assert on `process()`
  output for a full-body fixture.)*
- **I3:** A **brief with no image** produces a valid two-section prompt without raising.
  *(Check: `process(image_path=None, brief="…")` returns a non-empty prompt with both
  sections.)*
- **I4:** The agent demonstrably used progressive disclosure — it opened ≥1 section
  *map* and did **not** read every detail file. *(Check: `SkillReaderTool` call log for
  a run shows map reads and a subset — not all — of detail files.)*
- **I5:** `process()` return keys (`reference_image`, `generated_prompt`,
  `generated_prompts`, `descriptive_prompt`) are unchanged in name/type; the existing
  Celery task and `caption_export_task` run unmodified against it. *(Check: existing
  task call sites work without signature changes; per-file tests pass.)*

---

## Existing-system contract inventory (keep / cut / change)

Since this intent rebuilds `ImageToPromptWorkflow`, every element of its current
contract is marked. A cut you can name is a decision; a cut you didn't notice is a
regression.

| Element (current) | Verdict | Note |
|---|---|---|
| Programmatic vision step (single static `analyst_task.txt`, 5-cat A–E report) | **CHANGE** | Becomes a skill-driven Analyst agent that observes **and corrects**, disclosing references progressively. Raw vision call may remain as the Analyst's "what's literally there" input. |
| Analyst = strictly objective, "no fluff, objective reality" | **CHANGE** | Analyst is now **normative/corrective**: judges the ref against skill photography rules and proposes the improved version. |
| Single `turbo_engineer` injecting full framework+constraints+example up front | **CHANGE** | Becomes a **thin Enhancer/assembler**: takes the analyst's improved analysis, applies persona locks + `#Subject`/`#Environment`. Craft knowledge moves to the skill/analyst. |
| Persona locks (hair_color, hairstyles, MODE_FULL/PORTRAIT body string, KOL demographic) | **KEEP** | C2. |
| `#Subject` / `#Environment` two-section output format | **KEEP** | C2. |
| Multi-provider vision (OpenAI / Grok / Gemini) | **KEEP** | C4. |
| Refusal / moderation phrase detection | **KEEP** | Still needed on the vision read. |
| `variation_count` (N variations) | **KEEP** | |
| **Image required** (`FileNotFoundError` if missing) | **CHANGE** | Image now **optional**; brief-only allowed; at least one of {image, brief} required. |
| `process()` return shape | **KEEP** | `reference_image` may be `None` for brief-only; `descriptive_prompt` now = analyst's *improved* analysis. |
| Celery `process_image_task` → `generation_requests` review queue | **KEEP** | Add a **regenerate** action (C5). |
| `caption_export_task` | **KEEP** | Runs unmodified against the new `process()`. |
| `writing-image-prompts` skill (currently outside repo) | **ADD** | Vendored into the repo so `SkillReaderTool` can read it. |
| Text **brief** input | **ADD** | New optional input threaded to Analyst + Enhancer. |

## Assumptions & open decisions (conservative defaults, not yet confirmed)

- **A1 — Correction scope:** the Analyst preserves the reference's *subject, wardrobe,
  setting intent, and pose intent*; it corrects/upgrades only the **photographic
  technique** dimensions (composition, lighting, lens/camera) toward skill-endorsed
  patterns. It does not re-invent the scene. *(Default; confirm.)*
- **A2 — Skill vendoring location:** `prompts/skills/writing-image-prompts/`. *(Default;
  confirm.)*
- **A3 — Brief-only vision:** with no image the Analyst has nothing to observe, so it
  *chooses* good patterns for the brief from the skill rather than correcting.
  *(Default.)*
- **A4 — Enhancer still needs the persona `turbo_*` templates** for the locks + format;
  only the *craft* portion of those templates is superseded by the skill. *(Default;
  confirm which template parts stay.)*

# Pipeline Selector + JSON-Introspected Parameter Panel — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users pick the generation pipeline and temporarily override workflow parameters (read live from the workflow JSON) before clicking Process.

**Architecture:** Backend gains pipeline metadata (`label`/`available`), a JSON-introspection layer that lists every editable node input, and a per-run `workflow_overrides` channel applied last in `build_workflow` (non-destructive: empty overrides ⇒ today's behavior byte-for-byte). Frontend adds a grouped pipeline selector and a `WorkflowParametersPanel` populated from a new parameters endpoint; the panel state is sent as `workflow_overrides`.

**Tech Stack:** FastAPI + Pydantic, Celery, pytest (`asyncio_mode=auto`); React 18 + TypeScript, TanStack Query, Tailwind, shadcn-style UI primitives. Frontend verification is `tsc -b` (no JS test runner configured).

## Global Constraints

- **Test isolation (project memory — non-negotiable):** run backend tests in a disposable container with read-only source/test mounts and **no data-dir mounts**. Never run `docker compose exec` against the live container. Canonical command:
  ```bash
  docker run --rm \
    -v "$PWD/backend:/app/backend:ro" -v "$PWD/tests:/app/tests:ro" \
    -v "$PWD/pytest.ini:/app/pytest.ini:ro" -v "$PWD/workflow.json:/app/workflow.json:ro" \
    -e PYTHONDONTWRITEBYTECODE=1 -e COMFYUI_CLIP_DEVICE=cpu ff-auto-backend:latest \
    pytest -p no:cacheprovider -q tests/<file>.py
  ```
- **`tests/` and `docs/` are gitignored.** New test files need `git add -f`. New plan/spec docs stay untracked on disk (matches existing convention); do **not** force-add docs.
- **Back-compat:** every new param defaults to empty (`workflow_overrides = {}`); when omitted, generation behavior is identical to today. Do **not** remove `_patch_workflow_dimensions`, `_patch_clip_loader`, the strength patch, or the existing `width`/`height`/`strength`/`clip_model_type` backend params.
- **Locked inputs** (shown but never overridable): `seed`, `noise_seed` ("Controlled by the Seed strategy"), `text` ("Set from the generated prompt"), `lora_name` ("Controlled by the LoRA selector"), `device` ("Controlled by deployment (COMFYUI_CLIP_DEVICE)").
- **Commit message footer (every commit):**
  ```
  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
  ```
- Current branch is `z-image-gallery-updates`; commit there (no new branch unless asked).

## File Structure

**Backend**
- `backend/pipelines/base.py` (modify) — `label`/`available` attrs; `pipelines_metadata()`; `LOCKED_INPUT_KEYS`/reasons; `_infer_param_type()`; `describe_workflow_parameters()`; `apply_workflow_overrides()`; `GenerationInputs.workflow_overrides`; `GenerationPipeline.load_template()`/`describe_parameters()`.
- `backend/pipelines/image.py` (modify) — labels on the two image pipelines; `ComfyImagePipeline.load_template()`; call `apply_workflow_overrides` last in `build_workflow`.
- `backend/pipelines/video.py` (modify) — `available = False` + labels on the three stubs.
- `backend/pipelines/__init__.py` (modify) — re-export `pipelines_metadata`, `describe_workflow_parameters`, `apply_workflow_overrides`.
- `backend/models/workspace.py` (modify) — `PipelineInfo`, `WorkflowParamInput`, `WorkflowParamNode`, `WorkflowParametersResponse`; `workflow_overrides` on both request models.
- `backend/api/workspace.py` (modify) — `_get_available_pipeline()`; `GET /workspace/pipelines`; `GET /workspace/pipelines/{pipeline_type}/parameters`; thread `workflow_overrides` in `process`/`process_batch`.
- `backend/services/image_processing.py` (modify) — `workflow_overrides` param + task kwarg.
- `backend/tasks.py` (modify) — `workflow_overrides` through `process_image_task` → `async_process_image` → `generate_image`.
- `backend/third_parties/comfyui_client.py` (modify) — `generate_image(workflow_overrides=...)` → `GenerationInputs.workflow_overrides`.

**Backend tests** (gitignored — `git add -f`)
- `tests/test_pipeline_params.py` (create) — metadata, introspection, override application, image `build_workflow` override behavior.
- `tests/test_pipelines_api.py` (modify) — new endpoints + `workflow_overrides` threading.

**Frontend**
- `frontend/src/types/index.ts` (modify) — pipeline/param types; extend `ProcessImageConfig`.
- `frontend/src/api/workspace.ts` (modify) — `getPipelines()`, `getPipelineParameters()`.
- `frontend/src/components/workspace/WorkflowParametersPanel.tsx` (create) — the panel + pure helpers `buildInitialOverrides()` / `overridesEqual()`.
- `frontend/src/pages/WorkspacePage.tsx` (modify) — pipeline selector; remove `clip_model_type`/width/height/strength app controls; overrides state; wire into process.

---

### Task 1: Pipeline metadata (`label` / `available` / `pipelines_metadata`)

**Files:**
- Modify: `backend/pipelines/base.py` (class attrs on `GenerationPipeline` ~line 65-66; new `pipelines_metadata()` after `available_pipelines()` ~line 119)
- Modify: `backend/pipelines/image.py` (add `label` to the two registered classes ~line 191-209)
- Modify: `backend/pipelines/video.py` (add `available`/`label` ~line 27-64)
- Modify: `backend/pipelines/__init__.py` (export `pipelines_metadata`)
- Test: `tests/test_pipeline_params.py`

**Interfaces:**
- Produces: `GenerationPipeline.label: str`, `GenerationPipeline.available: bool = True`; `pipelines_metadata() -> list[dict]` where each dict is `{"pipeline_type": str, "media_type": str, "label": str, "available": bool}`, sorted by `pipeline_type`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_pipeline_params.py`:

```python
"""Tests for pipeline metadata, JSON introspection, and override application."""
from backend.pipelines import pipelines_metadata


def test_pipelines_metadata_includes_image_and_video():
    meta = pipelines_metadata()
    by_type = {m["pipeline_type"]: m for m in meta}

    assert by_type["image.subject_environment"]["media_type"] == "image"
    assert by_type["image.subject_environment"]["available"] is True
    assert by_type["image.subject_environment"]["label"] == "Subject + Environment"
    assert by_type["image.unified"]["label"] == "Unified prompt"

    # Video pipelines are typed stubs — present but not runnable yet.
    assert by_type["video.first_frame"]["available"] is False
    assert by_type["video.first_last_frame"]["media_type"] == "video"
    assert by_type["video.first_middle_last_frame"]["available"] is False


def test_pipelines_metadata_sorted_by_type():
    types = [m["pipeline_type"] for m in pipelines_metadata()]
    assert types == sorted(types)
```

- [ ] **Step 2: Run test to verify it fails**

Run (in the isolated container per Global Constraints): `pytest -p no:cacheprovider -q tests/test_pipeline_params.py`
Expected: FAIL — `ImportError: cannot import name 'pipelines_metadata'`.

- [ ] **Step 3: Write minimal implementation**

In `backend/pipelines/base.py`, add the two class attrs to `GenerationPipeline` (just below `media_type` at line 66):

```python
    pipeline_type: str = ""
    media_type: str = ""  # "image" | "video"
    label: str = ""       # human-friendly name for the selector
    available: bool = True  # False for typed stubs that cannot run yet
```

Add `pipelines_metadata()` after `available_pipelines()` (after line 119):

```python
def pipelines_metadata() -> List[Dict[str, Any]]:
    """Selector-facing metadata for every registered pipeline."""
    return [
        {
            "pipeline_type": p.pipeline_type,
            "media_type": p.media_type,
            "label": p.label or p.pipeline_type,
            "available": p.available,
        }
        for p in sorted(_REGISTRY.values(), key=lambda x: x.pipeline_type)
    ]
```

In `backend/pipelines/image.py`, add `label` to each registered class:

```python
class UnifiedPromptPipeline(ComfyImagePipeline):
    ...
    pipeline_type = "image.unified"
    label = "Unified prompt"
```
```python
class SubjectEnvironmentPipeline(ComfyImagePipeline):
    ...
    pipeline_type = "image.subject_environment"
    label = "Subject + Environment"
```

In `backend/pipelines/video.py`, set `available = False` on the base `ComfyVideoPipeline` (below `media_type = "video"`):

```python
    media_type = "video"
    available = False  # typed stubs — build_workflow not implemented yet
    required_images: int = 0
```

And add `label` to each stub:

```python
class FirstFramePipeline(ComfyVideoPipeline):
    ...
    pipeline_type = "video.first_frame"
    label = "First frame"
    required_images = 1
```
```python
class FirstLastFramePipeline(ComfyVideoPipeline):
    ...
    pipeline_type = "video.first_last_frame"
    label = "First + Last frame"
    required_images = 2
```
```python
class FirstMiddleLastFramePipeline(ComfyVideoPipeline):
    ...
    pipeline_type = "video.first_middle_last_frame"
    label = "First + Middle + Last frame"
    required_images = 3
```

In `backend/pipelines/__init__.py`, add `pipelines_metadata` to the names imported/re-exported from `.base`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest -p no:cacheprovider -q tests/test_pipeline_params.py`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add -f tests/test_pipeline_params.py
git add backend/pipelines/base.py backend/pipelines/image.py backend/pipelines/video.py backend/pipelines/__init__.py
git commit -m "feat(pipelines): add label/available metadata + pipelines_metadata()"
```

---

### Task 2: JSON introspection (`describe_workflow_parameters`)

**Files:**
- Modify: `backend/pipelines/base.py` (add constants + `_infer_param_type` + `describe_workflow_parameters` + `GenerationPipeline.load_template`/`describe_parameters`)
- Modify: `backend/pipelines/image.py` (`ComfyImagePipeline.load_template`)
- Modify: `backend/pipelines/__init__.py` (export `describe_workflow_parameters`)
- Test: `tests/test_pipeline_params.py`

**Interfaces:**
- Produces: `describe_workflow_parameters(workflow_data: dict) -> list[dict]`. Each node dict: `{"node_id": str, "class_type": str, "title": str, "inputs": [ {"key": str, "value": Any, "type": str, "locked": bool, "locked_reason": str | None} ]}`. `type` ∈ `{"integer","number","boolean","string"}`. List-valued inputs (wiring) are excluded. Node order = dict insertion order.
- Produces: `GenerationPipeline.load_template(self) -> dict` (base raises `NotImplementedError`); `ComfyImagePipeline.load_template` returns `_load_workflow_json()`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_pipeline_params.py`:

```python
from backend.pipelines import describe_workflow_parameters

SAMPLE_WF = {
    "1": {"class_type": "LoraLoaderModelOnly",
          "inputs": {"lora_name": "x.safetensors", "strength_model": 1.15, "model": ["2", 0]}},
    "2": {"class_type": "EmptySD3LatentImage",
          "inputs": {"width": 512, "height": 768, "batch_size": 1}},
    "3": {"class_type": "KSampler", "_meta": {"title": "Main Sampler"},
          "inputs": {"seed": 42, "steps": 8, "cfg": 0.9, "model": ["1", 0]}},
    "4": {"class_type": "CLIPTextEncode",
          "inputs": {"text": "hello", "clip": ["5", 0]}},
    "5": {"class_type": "CLIPLoader",
          "inputs": {"type": "qwen_image", "device": "default"}},
}


def _inputs(nodes, node_id):
    node = next(n for n in nodes if n["node_id"] == node_id)
    return {i["key"]: i for i in node["inputs"]}


def test_describe_excludes_wiring_inputs():
    nodes = describe_workflow_parameters(SAMPLE_WF)
    assert "model" not in _inputs(nodes, "1")   # list value = node connection
    assert "clip" not in _inputs(nodes, "4")


def test_describe_infers_types():
    ins = _inputs(describe_workflow_parameters(SAMPLE_WF), "3")
    assert ins["steps"]["type"] == "integer"
    assert ins["cfg"]["type"] == "number"
    assert _inputs(describe_workflow_parameters(SAMPLE_WF), "5")["type"]["type"] == "string"


def test_describe_marks_locked_inputs():
    nodes = describe_workflow_parameters(SAMPLE_WF)
    assert _inputs(nodes, "3")["seed"]["locked"] is True
    assert "Seed strategy" in _inputs(nodes, "3")["seed"]["locked_reason"]
    assert _inputs(nodes, "4")["text"]["locked"] is True
    assert _inputs(nodes, "1")["lora_name"]["locked"] is True
    assert _inputs(nodes, "5")["device"]["locked"] is True
    # editable ones are not locked
    assert _inputs(nodes, "1")["strength_model"]["locked"] is False
    assert _inputs(nodes, "2")["width"]["locked"] is False


def test_describe_uses_meta_title_else_class_type():
    nodes = describe_workflow_parameters(SAMPLE_WF)
    titles = {n["node_id"]: n["title"] for n in nodes}
    assert titles["3"] == "Main Sampler"
    assert titles["2"] == "EmptySD3LatentImage"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest -p no:cacheprovider -q tests/test_pipeline_params.py`
Expected: FAIL — `ImportError: cannot import name 'describe_workflow_parameters'`.

- [ ] **Step 3: Write minimal implementation**

In `backend/pipelines/base.py`, after the imports add module constants:

```python
LOCKED_INPUT_KEYS: Dict[str, str] = {
    "seed": "Controlled by the Seed strategy",
    "noise_seed": "Controlled by the Seed strategy",
    "text": "Set from the generated prompt",
    "lora_name": "Controlled by the LoRA selector",
    "device": "Controlled by deployment (COMFYUI_CLIP_DEVICE)",
}


def _infer_param_type(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    return "string"


def describe_workflow_parameters(workflow_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """List every editable (non-wiring) node input from a workflow graph.

    List-valued inputs are node connections and are excluded. Inputs whose key
    is in ``LOCKED_INPUT_KEYS`` are returned but flagged ``locked`` so the UI can
    show them greyed-out (they are owned by the app / prompt / deployment).
    """
    nodes: List[Dict[str, Any]] = []
    for node_id, node in workflow_data.items():
        if not isinstance(node, dict) or "inputs" not in node:
            continue
        title = node.get("_meta", {}).get("title") or node.get("class_type", node_id)
        inputs: List[Dict[str, Any]] = []
        for key, value in node.get("inputs", {}).items():
            if isinstance(value, list):  # node connection (wiring), not a value
                continue
            locked_reason = LOCKED_INPUT_KEYS.get(key)
            inputs.append({
                "key": key,
                "value": value,
                "type": _infer_param_type(value),
                "locked": locked_reason is not None,
                "locked_reason": locked_reason,
            })
        if inputs:
            nodes.append({
                "node_id": node_id,
                "class_type": node.get("class_type", ""),
                "title": title,
                "inputs": inputs,
            })
    return nodes
```

Add to `GenerationPipeline` (after `build_workflow`):

```python
    def load_template(self) -> Dict[str, Any]:
        """Return the raw workflow graph this pipeline builds from."""
        raise NotImplementedError(
            f"{self.pipeline_type} does not expose a workflow template"
        )

    def describe_parameters(self) -> List[Dict[str, Any]]:
        """Introspect this pipeline's workflow JSON into editable parameters."""
        return describe_workflow_parameters(self.load_template())
```

In `backend/pipelines/image.py`, add to `ComfyImagePipeline` (e.g. above `build_workflow`):

```python
    def load_template(self) -> Dict[str, Any]:
        return _load_workflow_json()
```

In `backend/pipelines/__init__.py`, add `describe_workflow_parameters` to the `.base` re-exports.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest -p no:cacheprovider -q tests/test_pipeline_params.py`
Expected: PASS (6 passed).

- [ ] **Step 5: Commit**

```bash
git add -f tests/test_pipeline_params.py
git add backend/pipelines/base.py backend/pipelines/image.py backend/pipelines/__init__.py
git commit -m "feat(pipelines): introspect workflow JSON into editable parameters"
```

---

### Task 3: Override application + thread into `build_workflow`

**Files:**
- Modify: `backend/pipelines/base.py` (`GenerationInputs.workflow_overrides`; `apply_workflow_overrides`)
- Modify: `backend/pipelines/image.py` (call `apply_workflow_overrides` last; switch `build_workflow` to `self.load_template()`)
- Modify: `backend/pipelines/__init__.py` (export `apply_workflow_overrides`)
- Test: `tests/test_pipeline_params.py`

**Interfaces:**
- Consumes: `describe_workflow_parameters`, `LOCKED_INPUT_KEYS` (Task 2).
- Produces: `GenerationInputs.workflow_overrides: Dict[str, Dict[str, Any]]` (default `{}`); `apply_workflow_overrides(workflow_data: dict, overrides: dict) -> None` (mutates in place; skips locked keys, unknown nodes, absent keys; coerces value to the existing JSON value's type).

- [ ] **Step 1: Write the failing test**

Append to `tests/test_pipeline_params.py`:

```python
import copy
from backend.pipelines import apply_workflow_overrides


def test_apply_overrides_sets_editable_and_coerces_type():
    wf = copy.deepcopy(SAMPLE_WF)
    apply_workflow_overrides(wf, {"2": {"width": "640", "height": 1024},
                                  "1": {"strength_model": "1.3"}})
    assert wf["2"]["inputs"]["width"] == 640          # "640" coerced to int
    assert wf["2"]["inputs"]["height"] == 1024
    assert wf["1"]["inputs"]["strength_model"] == 1.3  # coerced to float


def test_apply_overrides_skips_locked_keys():
    wf = copy.deepcopy(SAMPLE_WF)
    apply_workflow_overrides(wf, {"3": {"seed": 999, "steps": 12},
                                  "4": {"text": "HACK"},
                                  "1": {"lora_name": "evil.safetensors"}})
    assert wf["3"]["inputs"]["seed"] == 42             # locked, untouched
    assert wf["3"]["inputs"]["steps"] == 12            # editable, applied
    assert wf["4"]["inputs"]["text"] == "hello"        # locked, untouched
    assert wf["1"]["inputs"]["lora_name"] == "x.safetensors"  # locked


def test_apply_overrides_ignores_unknown_nodes_and_keys():
    wf = copy.deepcopy(SAMPLE_WF)
    apply_workflow_overrides(wf, {"99": {"width": 1}, "2": {"nope": 5}})
    assert "99" not in wf
    assert "nope" not in wf["2"]["inputs"]


def test_apply_overrides_empty_is_noop():
    wf = copy.deepcopy(SAMPLE_WF)
    apply_workflow_overrides(wf, {})
    assert wf == SAMPLE_WF
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest -p no:cacheprovider -q tests/test_pipeline_params.py`
Expected: FAIL — `ImportError: cannot import name 'apply_workflow_overrides'`.

- [ ] **Step 3: Write minimal implementation**

In `backend/pipelines/base.py`, add the field to `GenerationInputs` (after `options`):

```python
    options: Dict[str, Any] = field(default_factory=dict)
    workflow_overrides: Dict[str, Dict[str, Any]] = field(default_factory=dict)
```

Add the function (near `describe_workflow_parameters`):

```python
def _coerce_to(existing: Any, value: Any) -> Any:
    """Coerce ``value`` to the type of ``existing`` (best-effort)."""
    try:
        if isinstance(existing, bool):
            return bool(value)
        if isinstance(existing, int):
            return int(value)
        if isinstance(existing, float):
            return float(value)
        return type(existing)(value)
    except (TypeError, ValueError):
        return existing  # leave the original value untouched on bad input


def apply_workflow_overrides(
    workflow_data: Dict[str, Any], overrides: Dict[str, Dict[str, Any]]
) -> None:
    """Apply per-run node-input overrides in place.

    Skips locked keys, unknown nodes, and keys not already present as a
    non-list input. Coerces each value to the existing value's type. Defensive
    by design: a stale panel must never raise here.
    """
    if not overrides:
        return
    for node_id, patch in overrides.items():
        node = workflow_data.get(node_id)
        if not isinstance(node, dict):
            continue
        node_inputs = node.get("inputs")
        if not isinstance(node_inputs, dict):
            continue
        for key, value in (patch or {}).items():
            if key in LOCKED_INPUT_KEYS:
                continue
            if key not in node_inputs or isinstance(node_inputs[key], list):
                continue
            node_inputs[key] = _coerce_to(node_inputs[key], value)
```

In `backend/pipelines/image.py`, import `apply_workflow_overrides` from `.base` (add to the existing `from .base import (...)`), switch the template load to the method, and apply overrides last in `build_workflow`:

```python
    def build_workflow(self, inputs: GenerationInputs) -> Dict[str, Any]:
        cleaned_prompt = _clean_prompt(inputs.prompt)
        workflow_data = self.load_template()
        final_lora = _resolve_lora(inputs.lora_name, inputs.kol_persona)

        _patch_clip_loader(workflow_data, inputs.clip_model_type)
        self.inject_prompt(workflow_data, cleaned_prompt)

        lora_node = _find_lora_workflow_node(workflow_data)
        if lora_node:
            lora_inputs = _workflow_node_inputs(lora_node)
            if final_lora:
                lora_inputs["lora_name"] = final_lora
            if inputs.strength_model is not None:
                lora_inputs["strength_model"] = float(inputs.strength_model)

        _patch_workflow_dimensions(workflow_data, inputs.width, inputs.height)
        _patch_sampler_seeds(workflow_data, inputs.seed_strategy, inputs.base_seed)
        apply_workflow_overrides(workflow_data, inputs.workflow_overrides)
        return workflow_data
```

In `backend/pipelines/__init__.py`, add `apply_workflow_overrides` to the `.base` re-exports.

- [ ] **Step 4: Add the image-pipeline integration test, then run**

Append to `tests/test_pipeline_params.py`:

```python
import pytest
from backend.pipelines import GenerationInputs, get_pipeline
from backend.pipelines import image as image_mod

# Minimal image workflow exercising lora/dims/seed/clip/prompt + an upscale node.
IMAGE_WF = {
    "lora": {"class_type": "LoraLoaderModelOnly",
             "inputs": {"lora_name": "base.safetensors", "strength_model": 1.15, "model": ["unet", 0]}},
    "latent": {"class_type": "EmptySD3LatentImage",
               "inputs": {"width": 512, "height": 768, "batch_size": 1}},
    "scale": {"class_type": "ImageScale",
              "inputs": {"width": 1024, "height": 1536, "upscale_method": "lanczos",
                         "crop": "disabled", "image": ["dec", 0]}},
    "ks": {"class_type": "KSampler",
           "inputs": {"seed": 1, "steps": 8, "cfg": 0.9, "model": ["lora", 0]}},
    "clip": {"class_type": "CLIPLoader", "inputs": {"type": "qwen_image", "device": "default"}},
    "txt": {"class_type": "CLIPTextEncode", "inputs": {"text": "", "clip": ["clip", 0]}},
}


@pytest.fixture
def patched_template(monkeypatch):
    monkeypatch.setattr(image_mod, "_load_workflow_json", lambda: copy.deepcopy(IMAGE_WF))


def test_build_workflow_override_beats_dimension_patch(patched_template):
    pipe = get_pipeline("image.unified")
    inputs = GenerationInputs(prompt="hi",
                              workflow_overrides={"latent": {"width": 700, "height": 900}})
    wf = pipe.build_workflow(inputs)
    assert wf["latent"]["inputs"]["width"] == 700   # override beats the auto-half (256)
    assert wf["latent"]["inputs"]["height"] == 900


def test_build_workflow_override_sets_strength(patched_template):
    pipe = get_pipeline("image.unified")
    wf = pipe.build_workflow(GenerationInputs(
        prompt="hi", workflow_overrides={"lora": {"strength_model": 1.4}}))
    assert wf["lora"]["inputs"]["strength_model"] == 1.4


def test_build_workflow_does_not_override_locked_seed(patched_template):
    pipe = get_pipeline("image.unified")
    wf = pipe.build_workflow(GenerationInputs(
        prompt="hi", seed_strategy="fixed", base_seed=100,
        workflow_overrides={"ks": {"seed": 5}}))
    assert wf["ks"]["inputs"]["seed"] == 100  # app strategy owns seed; override ignored


def test_build_workflow_empty_overrides_matches_legacy(patched_template):
    pipe = get_pipeline("image.unified")
    wf = pipe.build_workflow(GenerationInputs(prompt="hi", seed_strategy="fixed", base_seed=7))
    # No overrides: dims come from the legacy patch (output=1024x1600, latent halved).
    assert wf["scale"]["inputs"]["width"] == 1024
    assert wf["latent"]["inputs"]["width"] == 512
    assert wf["ks"]["inputs"]["seed"] == 7
```

Run: `pytest -p no:cacheprovider -q tests/test_pipeline_params.py`
Expected: PASS (all tests, ~14 passed).

- [ ] **Step 5: Regression-check the existing pipeline suite**

Run: `pytest -p no:cacheprovider -q tests/test_pipelines.py tests/test_comfyui_client.py`
Expected: PASS (no regressions — `build_workflow` with no overrides is unchanged, and `load_template` delegates to the same monkeypatched `_load_workflow_json`).

- [ ] **Step 6: Commit**

```bash
git add -f tests/test_pipeline_params.py
git add backend/pipelines/base.py backend/pipelines/image.py backend/pipelines/__init__.py
git commit -m "feat(pipelines): apply per-run workflow_overrides last in build_workflow"
```

---

### Task 4: API endpoints — `GET /pipelines` and `GET /pipelines/{type}/parameters`

**Files:**
- Modify: `backend/models/workspace.py` (response models, after the existing `BatchDispatchResponse` ~line 72)
- Modify: `backend/api/workspace.py` (`_get_available_pipeline`; two routes after `list_image_pipelines` ~line 57)
- Test: `tests/test_pipelines_api.py`

**Interfaces:**
- Consumes: `pipelines_metadata`, `get_pipeline`, `UnknownPipelineError` (Tasks 1-2).
- Produces: `GET /workspace/pipelines -> List[PipelineInfo]`; `GET /workspace/pipelines/{pipeline_type}/parameters -> WorkflowParametersResponse`. Pydantic models: `PipelineInfo{pipeline_type,media_type,label,available}`; `WorkflowParamInput{key,value:Any,type,locked,locked_reason:Optional[str]}`; `WorkflowParamNode{node_id,class_type,title,inputs:List[WorkflowParamInput]}`; `WorkflowParametersResponse{pipeline_type,nodes:List[WorkflowParamNode]}`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_pipelines_api.py`. Use the session-scoped `client` fixture already defined in `tests/conftest.py` (`TestClient(app)` with autouse temp-dir isolation) — just declare `client` as a test arg; no imports or new fixtures needed. The workspace router is mounted at prefix `/api/workspace` (verified in `backend/main.py:48`; see `tests/test_api_workspace.py` for the same usage).

```python
def test_get_pipelines_lists_image_and_video(client):
    resp = client.get("/api/workspace/pipelines")
    assert resp.status_code == 200
    by_type = {p["pipeline_type"]: p for p in resp.json()}
    assert by_type["image.unified"]["available"] is True
    assert by_type["image.unified"]["label"] == "Unified prompt"
    assert by_type["video.first_frame"]["available"] is False


def test_get_parameters_for_image_pipeline(client):
    resp = client.get("/api/workspace/pipelines/image.unified/parameters")
    assert resp.status_code == 200
    body = resp.json()
    assert body["pipeline_type"] == "image.unified"
    assert len(body["nodes"]) > 0
    # seed is present but locked
    seeds = [i for n in body["nodes"] for i in n["inputs"] if i["key"] == "seed"]
    assert seeds and all(i["locked"] for i in seeds)


def test_get_parameters_unknown_pipeline_400(client):
    assert client.get("/api/workspace/pipelines/image.nope/parameters").status_code == 400


def test_get_parameters_video_pipeline_400(client):
    # video pipelines are unavailable (no template)
    assert client.get("/api/workspace/pipelines/video.first_frame/parameters").status_code == 400
```


- [ ] **Step 2: Run test to verify it fails**

Run: `pytest -p no:cacheprovider -q tests/test_pipelines_api.py -k "pipelines or parameters"`
Expected: FAIL — 404 (routes not registered).

- [ ] **Step 3: Write minimal implementation**

In `backend/models/workspace.py`, add (use `from typing import Any, List, Optional` — extend the existing typing import):

```python
class PipelineInfo(BaseModel):
    pipeline_type: str
    media_type: str
    label: str
    available: bool


class WorkflowParamInput(BaseModel):
    key: str
    value: Any = None
    type: str
    locked: bool = False
    locked_reason: Optional[str] = None


class WorkflowParamNode(BaseModel):
    node_id: str
    class_type: str
    title: str
    inputs: List[WorkflowParamInput]


class WorkflowParametersResponse(BaseModel):
    pipeline_type: str
    nodes: List[WorkflowParamNode]
```

In `backend/api/workspace.py`, extend the model import block (add `PipelineInfo, WorkflowParametersResponse`) and add the helper + routes after `list_image_pipelines`:

```python
def _get_available_pipeline(pipeline_type: str):
    """Resolve a runnable pipeline or raise 400 (unknown or unavailable)."""
    from backend.pipelines import UnknownPipelineError, get_pipeline

    try:
        pipeline = get_pipeline(pipeline_type)
    except UnknownPipelineError:
        raise HTTPException(status_code=400, detail=f"Unknown pipeline_type '{pipeline_type}'")
    if not pipeline.available:
        raise HTTPException(
            status_code=400,
            detail=f"pipeline_type '{pipeline_type}' is not available yet",
        )
    return pipeline


@router.get("/pipelines", response_model=List[PipelineInfo])
def list_pipelines():
    """All registered pipelines (image + video) with selector metadata."""
    from backend.pipelines import pipelines_metadata

    return pipelines_metadata()


@router.get("/pipelines/{pipeline_type}/parameters", response_model=WorkflowParametersResponse)
def get_pipeline_parameters(pipeline_type: str):
    """Editable workflow parameters introspected from the pipeline's JSON."""
    pipeline = _get_available_pipeline(pipeline_type)
    return {"pipeline_type": pipeline_type, "nodes": pipeline.describe_parameters()}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest -p no:cacheprovider -q tests/test_pipelines_api.py -k "pipelines or parameters"`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add -f tests/test_pipelines_api.py
git add backend/models/workspace.py backend/api/workspace.py
git commit -m "feat(api): GET /workspace/pipelines and /pipelines/{type}/parameters"
```

---

### Task 5: Thread `workflow_overrides` through dispatch → task → generate_image

**Files:**
- Modify: `backend/models/workspace.py` (field on both request models ~line 39, 56)
- Modify: `backend/api/workspace.py` (pass `workflow_overrides` in `process` ~line 94-109 and `process_batch` ~line 121-136)
- Modify: `backend/services/image_processing.py` (`dispatch_processing` param ~line 120 + task kwarg ~line 144)
- Modify: `backend/tasks.py` (`process_image_task` ~line 132, `async_process_image` ~line 163, `generate_image` call ~line 238)
- Modify: `backend/third_parties/comfyui_client.py` (`generate_image` param ~line 448 + `GenerationInputs(...)` ~line 483)
- Test: `tests/test_pipelines_api.py`

**Interfaces:**
- Consumes: `GenerationInputs.workflow_overrides` (Task 3).
- Produces: `workflow_overrides: Dict[str, Dict[str, Any]] = {}` on `ProcessImageRequest`/`ProcessBatchRequest`; same-named kwarg defaulting to `{}` on `dispatch_processing`, `process_image_task`, `async_process_image`, and `generate_image`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_pipelines_api.py` (mirror the prior slice's fakes for `celery_app.send_task` / `_redis_client` and for `async_process_image`'s `get_instances`):

```python
def test_dispatch_forwards_workflow_overrides(monkeypatch):
    from backend.services import image_processing as ip

    captured = {}

    class _FakeTask:
        id = "t-1"

    def fake_send_task(name, kwargs, queue):
        captured.update(kwargs)
        return _FakeTask()

    monkeypatch.setattr(ip.celery_app, "send_task", fake_send_task)
    monkeypatch.setattr(ip, "_redis_client", lambda: (_ for _ in ()).throw(Exception("no redis")))

    svc = ip.ImageProcessingService()
    svc.dispatch_processing(
        image_path="/x.png", persona="emi", prepare=False,
        workflow_overrides={"125": {"strength_model": 1.3}},
    )
    assert captured["workflow_overrides"] == {"125": {"strength_model": 1.3}}


async def test_async_process_image_forwards_workflow_overrides(monkeypatch):
    import backend.tasks as tasks

    calls = {}

    class _FakeClient:
        async def generate_image(self, **kwargs):
            calls.update(kwargs)
            return "exec-1"

    class _FakeWorkflow:
        async def process(self, **kwargs):
            return {"generated_prompts": ["a prompt"]}

    class _FakeStorage:
        def log_execution(self, **kwargs): pass
        def log_failed_execution(self, **kwargs): pass

    monkeypatch.setattr(tasks, "get_instances",
                        lambda: (_FakeWorkflow(), _FakeClient(), _FakeStorage()))
    monkeypatch.setattr(tasks.download_execution_task, "apply_async", lambda *a, **k: None)

    class _Task:
        def update_state(self, **kwargs): pass

    await tasks.async_process_image(
        dest_image_path="/x.png", persona="emi", workflow_type="turbo",
        vision_model="gpt-4o", variation_count=1, strength_model=0.8,
        seed_strategy="random", base_seed=0, width=1024, height=1600,
        lora_name="", clip_model_type="qwen_image", task=_Task(),
        pipeline_type="image.unified",
        workflow_overrides={"125": {"strength_model": 1.3}},
    )
    assert calls["workflow_overrides"] == {"125": {"strength_model": 1.3}}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest -p no:cacheprovider -q tests/test_pipelines_api.py -k workflow_overrides`
Expected: FAIL — `TypeError: dispatch_processing() got an unexpected keyword argument 'workflow_overrides'`.

- [ ] **Step 3: Write minimal implementation**

`backend/models/workspace.py` — add to **both** `ProcessImageRequest` and `ProcessBatchRequest` (after `pipeline_type`):

```python
    workflow_overrides: Dict[str, Dict[str, Any]] = {}
```
(Ensure `from typing import Any, Dict` is imported in that file.)

`backend/api/workspace.py` — in `process`, add to the `dispatch_processing(...)` call (after `pipeline_type=body.pipeline_type,`):

```python
            workflow_overrides=body.workflow_overrides,
```
and the same line in `process_batch`'s `dispatch_batch(...)` call.

`backend/services/image_processing.py` — add the param to `dispatch_processing` (after `pipeline_type: str = "image.subject_environment",`):

```python
        workflow_overrides: Optional[Dict[str, Dict[str, Any]]] = None,
```
and inside, normalize + add to the task kwargs (after `"pipeline_type": pipeline_type,`):

```python
                "workflow_overrides": workflow_overrides or {},
```
(Ensure `from typing import Any, Dict, List, Optional` covers these.)

`backend/tasks.py` — `process_image_task`: add param after `pipeline_type=...`:

```python
    workflow_overrides=None,
```
and forward in the `async_process_image(...)` call:

```python
                workflow_overrides=workflow_overrides or {},
```
`async_process_image`: add `workflow_overrides=None` to the signature (end of params), and pass to `generate_image(...)` (after `pipeline_type=pipeline_type,`):

```python
            workflow_overrides=workflow_overrides or {},
```

`backend/third_parties/comfyui_client.py` — `generate_image`: add param after `pipeline_type: str = "image.subject_environment",`:

```python
        workflow_overrides: Optional[Dict[str, Dict[str, Any]]] = None,
```
and pass into `GenerationInputs(...)` (after `clip_model_type=clip_model_type,`):

```python
            workflow_overrides=workflow_overrides or {},
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest -p no:cacheprovider -q tests/test_pipelines_api.py`
Expected: PASS (all, including the prior slice's threading tests).

- [ ] **Step 5: Full backend regression**

Run: `pytest -p no:cacheprovider -q tests/test_pipeline_params.py tests/test_pipelines.py tests/test_pipelines_api.py tests/test_comfyui_client.py`
Expected: PASS (all green).

- [ ] **Step 6: Commit**

```bash
git add -f tests/test_pipelines_api.py
git add backend/models/workspace.py backend/api/workspace.py backend/services/image_processing.py backend/tasks.py backend/third_parties/comfyui_client.py
git commit -m "feat: thread workflow_overrides API->dispatch->task->generate_image"
```

---

### Task 6: Frontend types + API client

**Files:**
- Modify: `frontend/src/types/index.ts` (new types; extend `ProcessImageConfig`; trim `LastUsedConfig`)
- Modify: `frontend/src/api/workspace.ts` (two methods)

**Interfaces:**
- Produces: TS types `PipelineInfo`, `WorkflowParamInput`, `WorkflowParamNode`, `WorkflowParameters`; `ProcessImageConfig` gains `workflow_overrides?: Record<string, Record<string, unknown>>` and loses `width`/`height`/`strength`/`clip_model_type`; `workspaceApi.getPipelines()`, `workspaceApi.getPipelineParameters(pipelineType)`.

- [ ] **Step 1: Add types**

In `frontend/src/types/index.ts`, add:

```typescript
export interface PipelineInfo {
  pipeline_type: string
  media_type: string   // "image" | "video"
  label: string
  available: boolean
}

export interface WorkflowParamInput {
  key: string
  value: unknown
  type: 'integer' | 'number' | 'boolean' | 'string'
  locked: boolean
  locked_reason?: string | null
}

export interface WorkflowParamNode {
  node_id: string
  class_type: string
  title: string
  inputs: WorkflowParamInput[]
}

export interface WorkflowParameters {
  pipeline_type: string
  nodes: WorkflowParamNode[]
}
```

Update `ProcessImageConfig` — remove `width`, `height`, `strength`, `clip_model_type`; keep `pipeline_type?`; add overrides:

```typescript
export interface ProcessImageConfig {
  image_path: string
  persona: string
  workflow_type: string
  vision_model: string
  variation_count: number
  seed_strategy: string
  base_seed: number
  lora_name: string
  // Which generation pipeline builds the workflow (backend defaults when omitted).
  pipeline_type?: string
  // Per-run node-input overrides: { node_id: { input_key: value } }.
  workflow_overrides?: Record<string, Record<string, unknown>>
}
```

In `LastUsedConfig`, remove the `clip_model_type`, `strength`, `width`, `height` members (they are no longer app-level). Leave the rest.

- [ ] **Step 2: Add API methods**

In `frontend/src/api/workspace.ts`, add after `getImagePipelines`:

```typescript
  getPipelines: () =>
    apiClient.get<import('@/types').PipelineInfo[]>('/workspace/pipelines').then(r => r.data),

  getPipelineParameters: (pipelineType: string) =>
    apiClient
      .get<import('@/types').WorkflowParameters>(
        `/workspace/pipelines/${encodeURIComponent(pipelineType)}/parameters`,
      )
      .then(r => r.data),
```

- [ ] **Step 3: Typecheck**

Run: `cd frontend && npx tsc -b`
Expected: **non-zero exit** — `WorkspacePage.tsx` still references the removed `config.width`/`height`/`strength`/`clip_model_type`. This is expected; Task 8 fixes those references. (If you prefer a green gate here, do Steps 1-2 of Task 8 first; otherwise proceed — the next task resolves it.)

> Because removing fields breaks `WorkspacePage.tsx` until Task 8, **commit Tasks 6+7+8 together** at the end of Task 8. Do not commit a red typecheck.

---

### Task 7: `WorkflowParametersPanel` component

**Files:**
- Create: `frontend/src/components/workspace/WorkflowParametersPanel.tsx`

**Interfaces:**
- Consumes: `WorkflowParameters`, `WorkflowParamNode`, `WorkflowParamInput` (Task 6).
- Produces:
  - `buildInitialOverrides(params: WorkflowParameters): Record<string, Record<string, unknown>>` — every **editable** input, keyed `node_id → {key: value}` (locked inputs excluded). Pure.
  - `WorkflowParametersPanel` props: `{ params: WorkflowParameters | null; loading: boolean; error: string | null; values: Record<string, Record<string, unknown>>; onChange: (nodeId: string, key: string, value: unknown) => void; onReset: () => void }`.

- [ ] **Step 1: Implement the component (no test runner — `tsc -b` is the gate)**

Create `frontend/src/components/workspace/WorkflowParametersPanel.tsx`:

```tsx
import React from 'react'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Checkbox } from '@/components/ui/checkbox'
import { Button } from '@/components/ui/button'
import type { WorkflowParameters, WorkflowParamInput } from '@/types'

// Every editable input as { node_id: { key: value } }. Locked inputs excluded.
export function buildInitialOverrides(
  params: WorkflowParameters,
): Record<string, Record<string, unknown>> {
  const out: Record<string, Record<string, unknown>> = {}
  for (const node of params.nodes) {
    const editable = node.inputs.filter(i => !i.locked)
    if (editable.length === 0) continue
    out[node.node_id] = {}
    for (const inp of editable) out[node.node_id][inp.key] = inp.value
  }
  return out
}

interface Props {
  params: WorkflowParameters | null
  loading: boolean
  error: string | null
  values: Record<string, Record<string, unknown>>
  onChange: (nodeId: string, key: string, value: unknown) => void
  onReset: () => void
}

export const WorkflowParametersPanel: React.FC<Props> = ({
  params, loading, error, values, onChange, onReset,
}) => {
  if (loading) return <p className="text-xs text-muted-foreground">Loading parameters…</p>
  if (error) return <p className="text-xs text-destructive">{error}</p>
  if (!params || params.nodes.length === 0)
    return <p className="text-xs text-muted-foreground">No parameters for this pipeline.</p>

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <Label className="text-xs font-semibold">Workflow Parameters</Label>
        <button className="text-xs text-muted-foreground hover:text-foreground" onClick={onReset}>
          reset
        </button>
      </div>
      {params.nodes.map(node => (
        <details key={node.node_id} className="rounded border border-border/60 px-2 py-1.5">
          <summary className="cursor-pointer text-xs font-medium">
            {node.title}
            <span className="ml-1 font-mono text-[10px] text-muted-foreground">{node.class_type}</span>
          </summary>
          <div className="mt-2 space-y-2">
            {node.inputs.map(inp => (
              <ParamField
                key={inp.key}
                input={inp}
                value={values[node.node_id]?.[inp.key]}
                onChange={v => onChange(node.node_id, inp.key, v)}
              />
            ))}
          </div>
        </details>
      ))}
    </div>
  )
}

const ParamField: React.FC<{
  input: WorkflowParamInput
  value: unknown
  onChange: (v: unknown) => void
}> = ({ input, value, onChange }) => {
  if (input.locked) {
    return (
      <div className="space-y-0.5" title={input.locked_reason ?? undefined}>
        <Label className="text-[11px] text-muted-foreground">{input.key}</Label>
        <Input value={String(input.value)} disabled className="h-7 text-xs" />
        {input.locked_reason && (
          <p className="text-[10px] text-muted-foreground">{input.locked_reason}</p>
        )}
      </div>
    )
  }
  if (input.type === 'boolean') {
    return (
      <label className="flex items-center gap-2 text-[11px]">
        <Checkbox checked={Boolean(value)} onCheckedChange={c => onChange(Boolean(c))} />
        {input.key}
      </label>
    )
  }
  const isNumeric = input.type === 'integer' || input.type === 'number'
  return (
    <div className="space-y-0.5">
      <Label className="text-[11px]">{input.key}</Label>
      <Input
        type={isNumeric ? 'number' : 'text'}
        step={input.type === 'number' ? 'any' : undefined}
        value={value === undefined || value === null ? '' : String(value)}
        onChange={e => {
          const raw = e.target.value
          if (!isNumeric) return onChange(raw)
          const n = input.type === 'integer' ? parseInt(raw, 10) : parseFloat(raw)
          onChange(Number.isNaN(n) ? raw : n)
        }}
        className="h-7 text-xs"
      />
    </div>
  )
}
```

> Verify `@/components/ui/checkbox` exports `Checkbox` with an `onCheckedChange` prop; it exists in the repo (`checkbox.tsx`). If its API differs, adapt the prop names to match that file — do not add a new dependency.

- [ ] **Step 2: Typecheck (will be green after Task 8 fixes WorkspacePage)**

This component compiles on its own; the project-wide `tsc -b` stays red until Task 8. Commit with Task 8.

---

### Task 8: WorkspacePage integration (selector + panel + wiring)

**Files:**
- Modify: `frontend/src/pages/WorkspacePage.tsx`

**Interfaces:**
- Consumes: `workspaceApi.getPipelines`, `workspaceApi.getPipelineParameters` (Task 6); `WorkflowParametersPanel`, `buildInitialOverrides` (Task 7); `ProcessImageConfig` (Task 6).

- [ ] **Step 1: Imports + default config**

Add imports near the top:

```tsx
import { WorkflowParametersPanel, buildInitialOverrides } from '@/components/workspace/WorkflowParametersPanel'
import type { PipelineInfo, WorkflowParameters } from '@/types'
```

Replace `DEFAULT_CONFIG` (lines 29-41) with the trimmed version (no width/height/strength/clip_model_type; add pipeline_type):

```tsx
const DEFAULT_CONFIG: Omit<ProcessImageConfig, 'image_path'> = {
  persona: '',
  workflow_type: 'turbo',
  vision_model: 'gpt-4o',
  variation_count: 1,
  seed_strategy: 'random',
  base_seed: 0,
  lora_name: '',
  pipeline_type: 'image.subject_environment',
}
```

- [ ] **Step 2: State + queries**

After the `config` state (line 47), add:

```tsx
  const [overrides, setOverrides] = useState<Record<string, Record<string, unknown>>>({})

  const { data: pipelines = [] } = useQuery<PipelineInfo[]>({
    queryKey: ['pipelines'],
    queryFn: workspaceApi.getPipelines,
  })

  const pipelineType = config.pipeline_type || 'image.subject_environment'
  const {
    data: pipelineParams = null,
    isLoading: paramsLoading,
    error: paramsError,
  } = useQuery<WorkflowParameters>({
    queryKey: ['pipeline-params', pipelineType],
    queryFn: () => workspaceApi.getPipelineParameters(pipelineType),
  })

  // Re-seed override values whenever a new parameter set loads.
  React.useEffect(() => {
    if (pipelineParams) setOverrides(buildInitialOverrides(pipelineParams))
  }, [pipelineParams])
```

- [ ] **Step 3: Remove the lastUsed references to dropped fields**

In the `useLastUsed` load effect (~lines 85-93) and the save effect (~lines 104-114), delete the lines that read/write `clip_model_type`, `strength`, `width`, `height`. Leave persona/vision_model/variations/lora_name/seed_strategy/base_seed/workflow_type intact.

- [ ] **Step 4: Process mutation sends overrides**

In `processMutation` (~lines 128-136), include `workflow_overrides: overrides` in both calls:

```tsx
        const result = await workspaceApi.process({ ...config, workflow_overrides: overrides, image_path: paths[0], skip_prepare: true })
```
```tsx
        const result = await workspaceApi.processBatch(paths, { ...config, workflow_overrides: overrides, skip_prepare: true })
```

- [ ] **Step 5: Render — selector + panel; remove old controls**

Add the **Pipeline** selector as the first control in the sidebar (before Persona, after line 195's opening `<div className="p-4 space-y-4 flex-1">`):

```tsx
          {/* Pipeline */}
          <div className="space-y-2">
            <Label>Pipeline</Label>
            <Select
              value={pipelineType}
              onValueChange={(v) => setConfig(p => ({ ...p, pipeline_type: v }))}
            >
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                {pipelines.map(p => (
                  <SelectItem key={p.pipeline_type} value={p.pipeline_type} disabled={!p.available}>
                    {p.label}{!p.available ? ' (coming soon)' : ''}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
```

**Remove** these blocks (now workflow params): the **CLIP Model** block (lines 234-245), the **Strength** block (lines 259-267), and the **Dimensions** grid (lines 271-287). Remove the now-orphaned `<Separator />` at line 247 if it leaves two adjacent separators.

Add the panel just before the closing `</div>` of the controls container (before line 370's `</div>` that closes `p-4 space-y-4 flex-1`):

```tsx
          <Separator />
          <WorkflowParametersPanel
            params={pipelineParams}
            loading={paramsLoading}
            error={paramsError ? 'Failed to load workflow parameters' : null}
            values={overrides}
            onChange={(nodeId, key, value) =>
              setOverrides(prev => ({ ...prev, [nodeId]: { ...prev[nodeId], [key]: value } }))
            }
            onReset={() => pipelineParams && setOverrides(buildInitialOverrides(pipelineParams))}
          />
```

- [ ] **Step 6: Remove now-unused `clipModels`**

`useClipModels` (line 5 import, line 54 usage) is no longer referenced after the CLIP control is gone. Remove the `useClipModels` import and the `const { data: clipModels = [] } = useClipModels()` line to keep `tsc` clean (unused vars under `noUnusedLocals`).

- [ ] **Step 7: Typecheck**

Run: `cd frontend && npx tsc -b`
Expected: **exit 0** (clean).

- [ ] **Step 8: Commit (Tasks 6+7+8 together)**

```bash
git add frontend/src/types/index.ts frontend/src/api/workspace.ts \
        frontend/src/components/workspace/WorkflowParametersPanel.tsx \
        frontend/src/pages/WorkspacePage.tsx
git commit -m "feat(ui): pipeline selector + JSON-introspected workflow parameter panel"
```

---

### Task 9: End-to-end verification

**Files:** none (verification only)

- [ ] **Step 1: Full backend suite (isolated container)**

Run:
```bash
docker run --rm \
  -v "$PWD/backend:/app/backend:ro" -v "$PWD/tests:/app/tests:ro" \
  -v "$PWD/pytest.ini:/app/pytest.ini:ro" -v "$PWD/workflow.json:/app/workflow.json:ro" \
  -e PYTHONDONTWRITEBYTECODE=1 -e COMFYUI_CLIP_DEVICE=cpu ff-auto-backend:latest \
  pytest -p no:cacheprovider -q tests/test_pipeline_params.py tests/test_pipelines.py tests/test_pipelines_api.py tests/test_comfyui_client.py
```
Expected: all PASS, output pristine (only the known pre-existing Starlette deprecation warning, if any).

- [ ] **Step 2: Frontend typecheck**

Run: `cd frontend && npx tsc -b`
Expected: exit 0.

- [ ] **Step 3: Manual smoke (optional, against a dev stack)**

Open Workspace → confirm the **Pipeline** dropdown lists image pipelines (video greyed "coming soon"), the **Workflow Parameters** section populates from `workflow.json` (strength 1.15, EmptySD3 512×768, ImageScale 1024×1536, KSampler steps/cfg; seed/text/lora_name/device shown locked). Change `strength_model`, Process one image, and confirm the queued workflow used the overridden value (logs / ComfyUI).

---

## Self-Review

**Spec coverage:**
- Component 1 (pipeline metadata) → Task 1 + Task 4 (`/pipelines`). ✓
- Component 2 (introspection: editable=non-list, type inference, locked set, `_meta.title`) → Task 2 + Task 4 (`/parameters`, 400s). ✓
- Component 3 (override channel, applied last, type-coerce, skip locked, threading) → Task 3 + Task 5. ✓
- Component 4 (UI: selector grouped/disabled-video, panel grouped by node, locked disabled, reset, remove duplicate app controls, clip_model_type→panel) → Tasks 6-8. ✓
- Default-value shift (JSON as source of truth via full panel state) → Task 7 `buildInitialOverrides` (sends every editable input) + Task 3 (override beats legacy patch). ✓
- Error handling (400 unknown/unavailable; `apply_overrides` defensive; FE param-load failure) → Task 4 tests, Task 3 `apply_workflow_overrides`, Task 7 `error` prop. ✓
- Testing isolation → Global Constraints + Task 9. ✓
- `WorkspacePage` extraction concern → Task 7 dedicated component. ✓

**Placeholder scan:** No TBD/TODO; every code step shows complete code; commands have expected output. The only deferred-resolution note is the deliberate red typecheck between Tasks 6 and 8 (explicitly called out, committed together). ✓

**Type consistency:** `workflow_overrides: Dict[str, Dict[str, Any]]` (backend) ↔ `Record<string, Record<string, unknown>>` (frontend) throughout. `describe_workflow_parameters` / `apply_workflow_overrides` / `pipelines_metadata` / `load_template` / `describe_parameters` names match across base.py, image.py, `__init__.py`, API, and tests. `PipelineInfo`/`WorkflowParam*` Pydantic models ↔ TS interfaces field-for-field. `buildInitialOverrides` named consistently in Tasks 7-8. ✓

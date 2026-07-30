"""Tests for workflow-file selection: listing, loading by name, and traversal guards."""
import copy
import json

import pytest

from backend.pipelines import image as image_mod
from backend.pipelines import (
    GenerationInputs,
    PipelineInputError,
    get_pipeline,
    list_workflow_files,
    load_workflow_template,
)


@pytest.fixture
def wf_dir(tmp_path, monkeypatch):
    """A controlled workflows/ directory via WORKFLOWS_DIR."""
    (tmp_path / "workflow.json").write_text(json.dumps({"node": {"class_type": "X", "inputs": {"a": 1}}}))
    (tmp_path / "alt.json").write_text(json.dumps({"node": {"class_type": "Y", "inputs": {"b": 2}}}))
    (tmp_path / "notes.txt").write_text("ignore me")
    monkeypatch.setenv("WORKFLOWS_DIR", str(tmp_path))
    monkeypatch.delenv("WORKFLOW_JSON_PATH", raising=False)
    return tmp_path


def test_list_workflow_files_returns_sorted_json_only(wf_dir):
    assert list_workflow_files() == ["alt.json", "workflow.json"]


def test_load_workflow_template_by_name(wf_dir):
    assert load_workflow_template("alt.json")["node"]["class_type"] == "Y"


def test_load_workflow_template_defaults_to_workflow_json(wf_dir):
    assert load_workflow_template()["node"]["class_type"] == "X"


def test_resolve_rejects_path_traversal(wf_dir):
    for bad in ["../secret.json", "a/b.json", "..", "sub\\evil.json"]:
        with pytest.raises(PipelineInputError):
            load_workflow_template(bad)


def test_build_workflow_loads_selected_file(monkeypatch):
    captured = {}

    def fake_load(workflow_name=None):
        captured["name"] = workflow_name
        # minimal graph the unified pipeline can patch
        return {"txt": {"class_type": "CLIPTextEncode", "inputs": {"text": ""}}}

    monkeypatch.setattr(image_mod, "_load_workflow_json", fake_load)
    pipe = get_pipeline("image.unified")
    pipe.build_workflow(GenerationInputs(prompt="hi", workflow_name="alt.json"))
    assert captured["name"] == "alt.json"


# ---------------------------------------------------------------------------
# Endpoints: GET /workflows and /workflows/{name}/parameters (real workflows/)
# ---------------------------------------------------------------------------

def test_get_workflows_lists_json_files(client):
    resp = client.get("/api/workspace/workflows")
    assert resp.status_code == 200
    names = resp.json()
    assert "Z-image-control-net.json" in names
    assert "SeedVR_Image_Upscaler.json" in names
    assert "Qwen-2511-Multi-Angle.json" in names


def test_get_workflow_parameters_ok(client):
    resp = client.get("/api/workspace/workflows/Z-image-control-net.json/parameters")
    assert resp.status_code == 200
    body = resp.json()
    assert body["workflow"] == "Z-image-control-net.json"
    assert len(body["nodes"]) > 0


def test_get_workflow_parameters_unknown_404(client):
    assert client.get("/api/workspace/workflows/nope.json/parameters").status_code == 404


# ---------------------------------------------------------------------------
# workflow_name threading: dispatch + async_process_image
# ---------------------------------------------------------------------------

def test_dispatch_forwards_workflow_name(monkeypatch):
    from backend.services import image_processing

    captured = {}

    class _FakeTask:
        id = "t-1"

    class _FakeRedis:
        def sadd(self, *a, **k):
            pass

        def setex(self, *a, **k):
            pass

    def fake_send_task(name, kwargs, queue):
        captured.update(kwargs)
        return _FakeTask()

    monkeypatch.setattr(image_processing.celery_app, "send_task", fake_send_task)
    monkeypatch.setattr(image_processing, "_redis_client", lambda: _FakeRedis())

    image_processing.ImageProcessingService().dispatch_processing(
        image_path="/x.png", persona="emi", prepare=False, workflow_name="alt.json",
    )
    assert captured["workflow_name"] == "alt.json"


@pytest.mark.asyncio
async def test_async_process_image_forwards_workflow_name(monkeypatch, clean_tables):
    from backend import tasks
    from backend.database.generation_requests_storage import GenerationRequestsStorage

    class _FakeWorkflow:
        async def process(self, **kwargs):
            return {"generated_prompts": ["a prompt"]}

    class _FakeStorage:
        def log_execution(self, **kwargs):
            pass

        def log_failed_execution(self, **kwargs):
            pass

    class _FakeTask:
        def update_state(self, **kwargs):
            pass

    monkeypatch.setattr(
        tasks, "get_instances", lambda: (_FakeWorkflow(), object(), _FakeStorage())
    )

    result = await tasks.async_process_image(
        dest_image_path="/x.png", persona="emi", workflow_type="image_generation",
        vision_model="gpt-4o", variation_count=1, width=1024, height=1600,
        task=_FakeTask(), workflow_name="alt.json",
    )
    row = GenerationRequestsStorage().get_request(result["request_ids"][0])
    assert row["workflow_name"] == "alt.json"


# ---------------------------------------------------------------------------
# Node bindings: the configured node wins over detection
# ---------------------------------------------------------------------------

@pytest.fixture
def bindings(tmp_path, monkeypatch):
    """An isolated registry, and a helper to bind nodes for a workflow."""
    from backend.config import GlobalConfig
    from backend.services import workflow_registry

    prompts = tmp_path / "registry-prompts"
    prompts.mkdir()
    monkeypatch.setattr(GlobalConfig, "PROMPTS_DIR", str(prompts), raising=False)

    def bind(workflow_name, **entry):
        workflow_registry.save_entry(workflow_name, {"kinds": [], **entry})

    return bind


def _two_prompt_graph():
    # The shape that makes detection a coin toss: two CLIPTextEncode nodes, the
    # positive one second.
    return {
        "7": {"class_type": "CLIPTextEncode", "inputs": {"text": "blurry, watermark"}},
        "21": {"class_type": "CLIPTextEncode", "inputs": {"text": ""}},
        "12": {"class_type": "LoadImage", "inputs": {"image": "old.png"}},
        "13": {"class_type": "LoadImage", "inputs": {"image": "mask.png"}},
    }


def test_inject_single_prompt_prefers_the_bound_node(bindings):
    graph = _two_prompt_graph()

    image_mod._inject_single_prompt(graph, "a red maple leaf", "21")

    assert graph["21"]["inputs"]["text"] == "a red maple leaf"
    # Detection would have written 7, the negative prompt.
    assert graph["7"]["inputs"]["text"] == "blurry, watermark"


def test_inject_single_prompt_detects_when_unbound(bindings):
    graph = _two_prompt_graph()

    image_mod._inject_single_prompt(graph, "a red maple leaf")

    assert graph["7"]["inputs"]["text"] == "a red maple leaf"


def test_inject_single_prompt_falls_back_when_the_bound_node_is_gone(bindings):
    graph = _two_prompt_graph()

    # A binding left over from before the graph was edited must not silently
    # drop the prompt on the floor.
    image_mod._inject_single_prompt(graph, "a red maple leaf", "999")

    assert graph["7"]["inputs"]["text"] == "a red maple leaf"


def test_patch_load_image_prefers_the_bound_node(bindings):
    graph = _two_prompt_graph()

    assert image_mod.patch_load_image(graph, "uploaded.png", "13") is True

    assert graph["13"]["inputs"]["image"] == "uploaded.png"
    assert graph["12"]["inputs"]["image"] == "old.png"


def test_patch_load_image_falls_back_when_the_bound_node_is_gone(bindings):
    graph = _two_prompt_graph()

    assert image_mod.patch_load_image(graph, "uploaded.png", "999") is True

    assert graph["12"]["inputs"]["image"] == "uploaded.png"


def test_build_workflow_applies_the_configured_bindings(bindings, monkeypatch):
    graph = _two_prompt_graph()
    monkeypatch.setattr(image_mod, "_load_workflow_json", lambda workflow_name=None: graph)
    bindings("bound.json", prompt_node="21", image_node="13")

    get_pipeline("image.unified").build_workflow(
        GenerationInputs(prompt="a prompt", images=["uploaded.png"], workflow_name="bound.json")
    )

    assert graph["21"]["inputs"]["text"] == "a prompt"
    assert graph["13"]["inputs"]["image"] == "uploaded.png"


def test_inject_single_prompt_writes_a_qwen_prompt_input(bindings):
    # Qwen's text node calls the input "prompt", so detection (CLIPTextEncode /
    # "text") cannot reach it at all — binding is the only way in.
    graph = {
        "113": {"class_type": "TextEncodeQwenImageEditPlus",
                "inputs": {"prompt": "blurry, bad hands"}},
        "127": {"class_type": "TextEncodeQwenImageEditPlus",
                "inputs": {"prompt": ["3", 0]}},
    }

    image_mod._inject_single_prompt(graph, "low three-quarter view", "113")

    assert graph["113"]["inputs"]["prompt"] == "low three-quarter view"


def test_inject_single_prompt_ignores_a_bound_node_with_no_text_input(bindings):
    graph = {
        "5": {"class_type": "LoadImage", "inputs": {"image": "ref.png"}},
        "7": {"class_type": "CLIPTextEncode", "inputs": {"text": ""}},
    }

    # Bound at the wrong node: fall back to detection rather than dropping the
    # prompt or inventing an input on the node.
    image_mod._inject_single_prompt(graph, "a prompt", "5")

    assert graph["7"]["inputs"]["text"] == "a prompt"
    assert graph["5"]["inputs"] == {"image": "ref.png"}

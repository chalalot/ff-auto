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
    assert "workflow.json" in names
    assert "kling.json" in names


def test_get_workflow_parameters_ok(client):
    resp = client.get("/api/workspace/workflows/workflow.json/parameters")
    assert resp.status_code == 200
    body = resp.json()
    assert body["workflow"] == "workflow.json"
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
async def test_async_process_image_forwards_workflow_name(monkeypatch):
    from backend import tasks

    calls = {}

    class _FakeClient:
        async def generate_image(self, **kwargs):
            calls.update(kwargs)
            return "exec-1"

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
        tasks, "get_instances", lambda: (_FakeWorkflow(), _FakeClient(), _FakeStorage())
    )
    monkeypatch.setattr(tasks.download_execution_task, "apply_async", lambda *a, **k: None)

    await tasks.async_process_image(
        dest_image_path="/x.png", persona="emi", workflow_type="turbo",
        vision_model="gpt-4o", variation_count=1, strength_model=0.8,
        seed_strategy="random", base_seed=0, width=1024, height=1600,
        lora_name="", clip_model_type="qwen_image", task=_FakeTask(),
        workflow_name="alt.json",
    )
    assert calls["workflow_name"] == "alt.json"

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

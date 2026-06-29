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

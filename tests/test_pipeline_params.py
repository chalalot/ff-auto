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
    # Seeds are workflow-owned now — editable directly in the panel.
    assert _inputs(nodes, "3")["seed"]["locked"] is False
    assert _inputs(nodes, "4")["text"]["locked"] is True
    assert _inputs(nodes, "5")["device"]["locked"] is True
    # editable ones are not locked (lora_name is panel-controlled per node)
    assert _inputs(nodes, "1")["lora_name"]["locked"] is False
    assert _inputs(nodes, "1")["strength_model"]["locked"] is False
    assert _inputs(nodes, "2")["width"]["locked"] is False


def test_describe_uses_meta_title_else_class_type():
    nodes = describe_workflow_parameters(SAMPLE_WF)
    titles = {n["node_id"]: n["title"] for n in nodes}
    assert titles["3"] == "Main Sampler"
    assert titles["2"] == "EmptySD3LatentImage"


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
                                  "1": {"lora_name": "other.safetensors"}})
    assert wf["3"]["inputs"]["seed"] == 999            # workflow-owned, applied
    assert wf["3"]["inputs"]["steps"] == 12            # editable, applied
    assert wf["4"]["inputs"]["text"] == "hello"        # locked (prompt-owned), untouched
    assert wf["1"]["inputs"]["lora_name"] == "other.safetensors"  # panel-controlled


def test_apply_overrides_ignores_unknown_nodes_and_keys():
    wf = copy.deepcopy(SAMPLE_WF)
    apply_workflow_overrides(wf, {"99": {"width": 1}, "2": {"nope": 5}})
    assert "99" not in wf
    assert "nope" not in wf["2"]["inputs"]


def test_apply_overrides_empty_is_noop():
    wf = copy.deepcopy(SAMPLE_WF)
    apply_workflow_overrides(wf, {})
    assert wf == SAMPLE_WF


from backend.pipelines import find_unresolved_overrides


def test_find_unresolved_returns_empty_when_everything_applies():
    assert find_unresolved_overrides(SAMPLE_WF, {"2": {"width": 640}, "3": {"steps": 12}}) == []
    assert find_unresolved_overrides(SAMPLE_WF, {}) == []


def test_find_unresolved_reports_deleted_node_and_renamed_key():
    stale = find_unresolved_overrides(SAMPLE_WF, {"99": {"width": 1}, "2": {"nope": 5}})
    assert sorted(stale) == ["2.nope", "99.width"]


def test_find_unresolved_reports_input_that_became_a_connection():
    # "model" on node 1 is wiring (a list), so an override targeting it is dead.
    assert find_unresolved_overrides(SAMPLE_WF, {"1": {"model": 0}}) == ["1.model"]


def test_find_unresolved_ignores_locked_keys():
    # Locked keys are a by-design skip, not staleness — no false alarm.
    assert find_unresolved_overrides(SAMPLE_WF, {"4": {"text": "HACK"}}) == []


def test_find_unresolved_matches_what_apply_silently_drops():
    overrides = {"99": {"width": 1}, "2": {"nope": 5, "width": 640}, "1": {"model": 0}}
    wf = copy.deepcopy(SAMPLE_WF)
    apply_workflow_overrides(wf, overrides)

    assert wf["2"]["inputs"]["width"] == 640                 # the one that landed
    assert sorted(find_unresolved_overrides(SAMPLE_WF, overrides)) == [
        "1.model", "2.nope", "99.width",
    ]


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
    monkeypatch.setattr(image_mod, "_load_workflow_json", lambda *a, **k: copy.deepcopy(IMAGE_WF))


def test_build_workflow_override_sets_dimensions(patched_template):
    pipe = get_pipeline("image.unified")
    inputs = GenerationInputs(prompt="hi",
                              workflow_overrides={"latent": {"width": 700, "height": 900}})
    wf = pipe.build_workflow(inputs)
    assert wf["latent"]["inputs"]["width"] == 700
    assert wf["latent"]["inputs"]["height"] == 900


def test_build_workflow_override_sets_strength(patched_template):
    pipe = get_pipeline("image.unified")
    wf = pipe.build_workflow(GenerationInputs(
        prompt="hi", workflow_overrides={"lora": {"strength_model": 1.4}}))
    assert wf["lora"]["inputs"]["strength_model"] == 1.4


def test_build_workflow_override_lora_beats_selector(patched_template):
    """Per-node panel override wins; the legacy top-level lora_name is ignored."""
    pipe = get_pipeline("image.unified")
    wf = pipe.build_workflow(GenerationInputs(
        prompt="hi", lora_name="selector.safetensors",
        workflow_overrides={"lora": {"lora_name": "panel.safetensors"}}))
    assert wf["lora"]["inputs"]["lora_name"] == "panel.safetensors"


def test_build_workflow_override_sets_seed(patched_template):
    """Seeds are workflow-owned — the panel override is applied verbatim."""
    pipe = get_pipeline("image.unified")
    wf = pipe.build_workflow(GenerationInputs(
        prompt="hi", workflow_overrides={"ks": {"seed": 5}}))
    assert wf["ks"]["inputs"]["seed"] == 5


def test_build_workflow_empty_overrides_keeps_authored_values(patched_template):
    pipe = get_pipeline("image.unified")
    wf = pipe.build_workflow(GenerationInputs(prompt="hi"))
    # No overrides: everything stays exactly as authored in the workflow JSON.
    assert wf["scale"]["inputs"]["width"] == 1024
    assert wf["latent"]["inputs"]["width"] == 512
    assert wf["ks"]["inputs"]["seed"] == 1
    assert wf["lora"]["inputs"]["lora_name"] == "base.safetensors"
    assert wf["clip"]["inputs"]["type"] == "qwen_image"

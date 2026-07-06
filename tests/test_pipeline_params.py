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

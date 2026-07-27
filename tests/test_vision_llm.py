"""The one multimodal seam: provider routing, mime sniffing, and trace shape.

No network. Each provider client is faked and the outgoing request is asserted.
"""
from types import SimpleNamespace

import pytest
from PIL import Image

from backend.config import GlobalConfig
from backend.services import vision_llm


@pytest.fixture
def png(tmp_path):
    path = tmp_path / "reference.png"
    Image.new("RGB", (2, 2), "white").save(path)
    return str(path)


def _fake_openai(monkeypatch, captured, content="described"):
    class FakeCompletions:
        def create(self, **kwargs):
            captured["request"] = kwargs
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
                usage=None,
            )

    class FakeOpenAI:
        def __init__(self, **kwargs):
            captured["client"] = kwargs
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setattr("openai.OpenAI", FakeOpenAI)


def _fake_google(monkeypatch, captured, text="described"):
    class FakeModels:
        def generate_content(self, **kwargs):
            captured["request"] = kwargs
            return SimpleNamespace(text=text, usage_metadata=None)

    class FakeClient:
        def __init__(self, **kwargs):
            captured["client"] = kwargs
            self.models = FakeModels()

    monkeypatch.setattr("google.genai.Client", FakeClient)


# ---- provider routing ----------------------------------------------------

def test_resolve_model_routes_by_prefix_and_maps_retired_gemini():
    assert vision_llm.resolve_model("gpt-4o") == ("openai", "gpt-4o")
    assert vision_llm.resolve_model("grok-2-vision") == ("grok", "grok-2-vision")
    assert vision_llm.resolve_model("gemma-4-31b-it") == ("google", "gemma-4-31b-it")
    assert vision_llm.resolve_model("gemini-1.5-pro") == ("google", "gemini-2.5-flash")


def test_openai_sends_system_prompt_and_inline_image(monkeypatch, png):
    captured = {}
    _fake_openai(monkeypatch, captured)

    result = vision_llm.complete(
        model_name="gpt-4o", prompt="Describe it",
        image_path=png, system_prompt="Observe only", max_tokens=1000,
    )

    assert result == "described"
    messages = captured["request"]["messages"]
    assert messages[0] == {"role": "system", "content": "Observe only"}
    assert messages[1]["content"][0] == {"type": "text", "text": "Describe it"}
    # real mime type, not a hardcoded image/jpeg for a PNG
    assert messages[1]["content"][1]["image_url"]["url"].startswith(
        "data:image/png;base64,"
    )
    assert captured["request"]["max_tokens"] == 1000


def test_max_tokens_omitted_when_not_requested(monkeypatch, png):
    captured = {}
    _fake_openai(monkeypatch, captured)

    vision_llm.complete(model_name="gpt-4o", prompt="Describe it", image_path=png)

    assert "max_tokens" not in captured["request"]


def test_text_only_call_sends_a_plain_string_content(monkeypatch):
    captured = {}
    _fake_openai(monkeypatch, captured)

    vision_llm.complete(model_name="gpt-4o", prompt="No image here")

    assert captured["request"]["messages"][0] == {
        "role": "user", "content": "No image here",
    }


def test_grok_uses_xai_base_url(monkeypatch, png):
    captured = {}
    _fake_openai(monkeypatch, captured)
    monkeypatch.setattr(GlobalConfig, "GROK_API_KEY", "xai-key")

    vision_llm.complete(model_name="grok-2-vision", prompt="Describe", image_path=png)

    assert captured["client"] == {
        "api_key": "xai-key", "base_url": "https://api.x.ai/v1",
    }


def test_gemma_folds_system_prompt_into_user_content(monkeypatch, png):
    # Gemma's native Gemini-API surface takes no separate system role.
    captured = {}
    _fake_google(monkeypatch, captured)
    monkeypatch.setattr(GlobalConfig, "GEMINI_API_KEY", "google-key")

    result = vision_llm.complete(
        model_name="gemma-4-31b-it", prompt="Describe the image",
        image_path=png, system_prompt="Observe only",
    )

    assert result == "described"
    assert captured["client"] == {"api_key": "google-key"}
    assert captured["request"]["model"] == "gemma-4-31b-it"
    assert captured["request"]["contents"][0] == "Observe only\n\nDescribe the image"
    assert captured["request"]["config"] is None
    assert isinstance(captured["request"]["contents"][1], Image.Image)


def test_gemini_passes_system_instruction_separately(monkeypatch, png):
    captured = {}
    _fake_google(monkeypatch, captured)
    monkeypatch.setattr(GlobalConfig, "GEMINI_API_KEY", "google-key")

    vision_llm.complete(
        model_name="gemini-2.5-flash", prompt="Describe the image",
        image_path=png, system_prompt="Observe only",
    )

    assert captured["request"]["contents"][0] == "Describe the image"
    assert captured["request"]["config"].system_instruction == "Observe only"


# ---- failure modes -------------------------------------------------------

def test_missing_image_raises_before_any_provider_call(monkeypatch):
    def _boom(**kwargs):
        raise AssertionError("provider must not be reached")

    monkeypatch.setattr("openai.OpenAI", _boom)

    with pytest.raises(vision_llm.VisionLLMError, match="not found"):
        vision_llm.complete(
            model_name="gpt-4o", prompt="Describe", image_path="/nope/missing.png",
        )


def test_empty_response_is_an_error_not_an_empty_prompt(monkeypatch, png):
    _fake_openai(monkeypatch, {}, content="   ")

    with pytest.raises(vision_llm.VisionLLMError, match="empty response"):
        vision_llm.complete(model_name="gpt-4o", prompt="Describe", image_path=png)


def test_missing_google_key_is_reported(monkeypatch, png):
    monkeypatch.setattr(GlobalConfig, "GEMINI_API_KEY", "")

    with pytest.raises(vision_llm.VisionLLMError, match="GEMINI_API_KEY"):
        vision_llm.complete(model_name="gemini-2.5-flash", prompt="x", image_path=png)


# ---- trace payload -------------------------------------------------------

def test_trace_records_the_call_without_inlining_base64(monkeypatch, png):
    recorded = []
    _fake_openai(monkeypatch, {})
    monkeypatch.setattr(
        "backend.services.vision_llm.record_llm_call", recorded.append
    )

    vision_llm.complete(
        model_name="gpt-4o", prompt="Describe", image_path=png,
        system_prompt="Observe only",
    )

    assert len(recorded) == 1
    payload = recorded[0]
    assert payload["model"] == "gpt-4o"
    assert payload["response"]["text"] == "described"
    image = payload["request"]["image"]
    assert image == {"path": png, "mime_type": "image/png", "bytes": image["bytes"]}
    assert "base64" not in str(payload["request"])
    assert payload["started_at"] and payload["finished_at"]


def test_trace_records_failures(monkeypatch, png):
    recorded = []
    monkeypatch.setattr(
        "backend.services.vision_llm.record_llm_call", recorded.append
    )

    with pytest.raises(vision_llm.VisionLLMError):
        vision_llm.complete(
            model_name="gpt-4o", prompt="Describe", image_path="/nope/missing.png",
        )

    assert recorded[0]["error"]["type"] == "VisionLLMError"
    assert recorded[0]["response"] is None

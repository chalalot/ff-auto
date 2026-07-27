import httpx
import pytest

from backend.third_parties import comfyui_client
from backend.third_parties.comfyui_client import ComfyUIClient


class FakeAsyncClient:
    def __init__(self, responses, calls):
        self.responses = responses
        self.calls = calls

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, json, headers):
        self.calls.append({"url": url, "json": json, "headers": headers})
        return self.responses.pop(0)


@pytest.mark.asyncio
async def test_queue_prompt_retries_transient_502(monkeypatch):
    request = httpx.Request("POST", "https://comfy.example/prompt")
    responses = [
        httpx.Response(502, text="<!DOCTYPE html><html>bad gateway</html>", request=request),
        httpx.Response(200, json={"prompt_id": "prompt-123"}, request=request),
    ]
    calls = []
    sleep_calls = []

    monkeypatch.setattr(
        comfyui_client.httpx,
        "AsyncClient",
        lambda *args, **kwargs: FakeAsyncClient(responses, calls),
    )
    monkeypatch.setattr(comfyui_client, "_calculate_backoff_delay", lambda attempt: 0.0)

    async def fake_sleep(delay):
        sleep_calls.append(delay)

    monkeypatch.setattr(comfyui_client.asyncio, "sleep", fake_sleep)

    client = ComfyUIClient(
        cloud_api_url="https://comfy.example",
        api_key="test-key",
        max_retries=1,
    )

    prompt_id = await client.queue_prompt({"1": {"inputs": {}}})

    assert prompt_id == "prompt-123"
    assert len(calls) == 2
    assert sleep_calls == [0.0]
    assert calls[0]["url"] == "https://comfy.example/prompt"
    assert calls[0]["json"]["extra_data"] == {"api_key_comfy_org": "test-key"}


@pytest.mark.asyncio
async def test_generate_image_patches_current_workflow_nodes(monkeypatch, tmp_path):
    workflow_path = tmp_path / "workflow.json"
    workflow_path.write_text(
        """
        {
          "2": {
            "class_type": "EmptySD3LatentImage",
            "inputs": {"width": 512, "height": 768, "batch_size": 1}
          },
          "7": {
            "class_type": "LoraLoaderModelOnly",
            "inputs": {"lora_name": "", "strength_model": 1.15}
          },
          "9": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": "", "clip": ["11", 0]}
          },
          "10": {
            "class_type": "KSampler",
            "inputs": {"seed": 1, "latent_image": ["2", 0]}
          },
          "11": {
            "class_type": "CLIPLoader",
            "inputs": {"type": "sd3", "clip_name": "qwen_3_4b.safetensors", "device": "default"}
          },
          "15": {
            "class_type": "ImageScale",
            "inputs": {"width": 1024, "height": 1536, "image": ["4", 0]}
          },
          "16": {
            "class_type": "KSampler",
            "inputs": {"seed": 2, "latent_image": ["13", 0]}
          }
        }
        """,
        encoding="utf-8",
    )
    monkeypatch.setenv("WORKFLOW_JSON_PATH", str(workflow_path))
    monkeypatch.setenv("COMFYUI_CLIP_DEVICE", "cpu")

    captured_workflow = {}

    async def fake_queue_prompt(self, workflow):
        captured_workflow.update(workflow)
        return "prompt-123"

    monkeypatch.setattr(ComfyUIClient, "queue_prompt", fake_queue_prompt)

    client = ComfyUIClient(cloud_api_url="https://comfy.example", api_key=None)

    prompt_id = await client.generate_image(
        "a prompt",
        workflow_overrides={"7": {"strength_model": 0.8}},
    )

    assert prompt_id == "prompt-123"
    # Seeds, LoRA, dims, CLIP type are workflow-owned — untouched unless overridden.
    assert captured_workflow["2"]["inputs"]["width"] == 512
    assert captured_workflow["2"]["inputs"]["height"] == 768
    assert captured_workflow["15"]["inputs"]["width"] == 1024
    assert captured_workflow["15"]["inputs"]["height"] == 1536
    assert captured_workflow["7"]["inputs"]["lora_name"] == ""
    assert captured_workflow["7"]["inputs"]["strength_model"] == 0.8
    assert captured_workflow["9"]["inputs"]["text"] == "a prompt"
    assert captured_workflow["10"]["inputs"]["seed"] == 1
    assert captured_workflow["11"]["inputs"]["type"] == "sd3"
    assert captured_workflow["11"]["inputs"]["device"] == "cpu"
    assert captured_workflow["16"]["inputs"]["seed"] == 2


@pytest.mark.asyncio
async def test_generate_image_patches_input_image_into_load_image(monkeypatch, tmp_path):
    workflow_path = tmp_path / "workflow.json"
    workflow_path.write_text(
        """
        {
          "1": {"class_type": "LoadImage", "inputs": {"image": "baked.png"}},
          "45": {"class_type": "CLIPTextEncode", "inputs": {"text": ""}}
        }
        """,
        encoding="utf-8",
    )
    monkeypatch.setenv("WORKFLOW_JSON_PATH", str(workflow_path))

    captured_workflow = {}

    async def fake_queue_prompt(self, workflow):
        captured_workflow.update(workflow)
        return "prompt-123"

    monkeypatch.setattr(ComfyUIClient, "queue_prompt", fake_queue_prompt)

    client = ComfyUIClient(cloud_api_url="https://comfy.example", api_key=None)

    prompt_id = await client.generate_image(
        "a prompt",
        input_image="uploaded_ref.png",
    )

    assert prompt_id == "prompt-123"
    assert captured_workflow["1"]["inputs"]["image"] == "uploaded_ref.png"
    assert captured_workflow["45"]["inputs"]["text"] == "a prompt"


@pytest.mark.asyncio
async def test_generate_image_uploads_library_image_override(monkeypatch, tmp_path):
    """A LoadImage override picked from the image library is uploaded to
    ComfyUI and the uploaded filename lands in the submitted graph."""
    from backend.config import GlobalConfig

    workflow_path = tmp_path / "workflow.json"
    workflow_path.write_text(
        '{"1": {"class_type": "LoadImage", "inputs": {"image": "baked.png"}}}',
        encoding="utf-8",
    )
    monkeypatch.setenv("WORKFLOW_JSON_PATH", str(workflow_path))

    library = tmp_path / "library"
    library.mkdir()
    (library / "ref.png").write_bytes(b"png")
    monkeypatch.setattr(GlobalConfig, "PROCESSED_DIR", str(library))

    captured_workflow = {}

    async def fake_queue_prompt(self, workflow):
        captured_workflow.update(workflow)
        return "prompt-123"

    async def fake_upload_image(self, path):
        assert path == str(library / "ref.png")
        return "uploaded_ref.png"

    monkeypatch.setattr(ComfyUIClient, "queue_prompt", fake_queue_prompt)
    monkeypatch.setattr(ComfyUIClient, "upload_image", fake_upload_image)

    client = ComfyUIClient(cloud_api_url="https://comfy.example", api_key=None)
    prompt_id = await client.generate_image(
        "a prompt",
        workflow_overrides={"1": {"image": "ref.png"}},
    )

    assert prompt_id == "prompt-123"
    assert captured_workflow["1"]["inputs"]["image"] == "uploaded_ref.png"


def test_extract_comfy_error_message_from_nested_json_string():
    message = comfyui_client._extract_comfy_error_message(
        {
            "status": "failed",
            "error_message": (
                '{"exception_message":"VRAM grow failed: 777912320 bytes\\n",'
                '"exception_type":"RuntimeError","node_id":"9","node_type":"CLIPTextEncode"}'
            ),
        }
    )

    assert message == "VRAM grow failed: 777912320 bytes at node 9 (CLIPTextEncode)"

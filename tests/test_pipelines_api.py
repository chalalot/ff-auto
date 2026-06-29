"""Tests that `pipeline_type` is threaded through the image generation API.

Covers the request contract (model defaults/overrides), pipeline-type
validation at the route boundary, and the two pass-through hops that actually
carry the value to the generator: the Celery dispatch and async_process_image.

Self-contained: Celery, Redis, CrewAI, and the ComfyUI client are all faked, so
no broker, network, or real data dir is touched.
"""
import pytest


# ---------------------------------------------------------------------------
# Request contract
# ---------------------------------------------------------------------------

def test_process_image_request_defaults_pipeline_type():
    from backend.models.workspace import ProcessImageRequest

    req = ProcessImageRequest(image_path="/x.png", persona="Jennie")
    assert req.pipeline_type == "image.subject_environment"


def test_process_image_request_accepts_override():
    from backend.models.workspace import ProcessImageRequest

    req = ProcessImageRequest(image_path="/x.png", persona="Jennie", pipeline_type="image.unified")
    assert req.pipeline_type == "image.unified"


def test_process_batch_request_defaults_pipeline_type():
    from backend.models.workspace import ProcessBatchRequest

    req = ProcessBatchRequest(image_paths=["/x.png"], persona="Jennie")
    assert req.pipeline_type == "image.subject_environment"


# ---------------------------------------------------------------------------
# Route-boundary validation
# ---------------------------------------------------------------------------

def test_validate_image_pipeline_accepts_image_pipeline():
    from backend.api.workspace import _validate_image_pipeline_type

    # Should not raise.
    _validate_image_pipeline_type("image.unified")
    _validate_image_pipeline_type("image.subject_environment")


def test_validate_image_pipeline_rejects_unknown():
    from fastapi import HTTPException
    from backend.api.workspace import _validate_image_pipeline_type

    with pytest.raises(HTTPException) as exc:
        _validate_image_pipeline_type("image.bogus")
    assert exc.value.status_code == 400


def test_validate_image_pipeline_rejects_video_pipeline():
    from fastapi import HTTPException
    from backend.api.workspace import _validate_image_pipeline_type

    with pytest.raises(HTTPException) as exc:
        _validate_image_pipeline_type("video.first_frame")
    assert exc.value.status_code == 400


# ---------------------------------------------------------------------------
# Service hop: dispatch_processing -> Celery task kwargs
# ---------------------------------------------------------------------------

def test_dispatch_processing_forwards_pipeline_type(monkeypatch):
    from backend.services import image_processing

    captured = {}

    class _FakeTask:
        id = "task-1"

    def fake_send_task(name, kwargs, queue):
        captured["kwargs"] = kwargs
        return _FakeTask()

    class _FakeRedis:
        def sadd(self, *a, **k):
            pass

        def setex(self, *a, **k):
            pass

    monkeypatch.setattr(image_processing.celery_app, "send_task", fake_send_task)
    monkeypatch.setattr(image_processing, "_redis_client", lambda: _FakeRedis())

    svc = image_processing.ImageProcessingService()
    task_id = svc.dispatch_processing(
        image_path="/x/y.png",
        persona="Jennie",
        pipeline_type="image.unified",
        prepare=False,
    )

    assert task_id == "task-1"
    assert captured["kwargs"]["pipeline_type"] == "image.unified"


# ---------------------------------------------------------------------------
# Deepest hop: async_process_image -> client.generate_image
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_async_process_image_forwards_pipeline_type_to_generate_image(monkeypatch):
    from backend import tasks

    captured = {}

    class _FakeWorkflow:
        async def process(self, **kwargs):
            return {"generated_prompts": ["a prompt"]}

    class _FakeClient:
        async def generate_image(self, **kwargs):
            captured.update(kwargs)
            return "exec-1"

    class _FakeStorage:
        def log_execution(self, **k):
            pass

        def log_failed_execution(self, **k):
            pass

    class _FakeTask:
        def update_state(self, **k):
            pass

    monkeypatch.setattr(
        tasks, "get_instances", lambda: (_FakeWorkflow(), _FakeClient(), _FakeStorage())
    )
    monkeypatch.setattr(tasks.download_execution_task, "apply_async", lambda *a, **k: None)

    await tasks.async_process_image(
        dest_image_path="/x/y.png",
        persona="Jennie",
        workflow_type="turbo",
        vision_model="gpt-4o",
        variation_count=1,
        strength_model=0.8,
        seed_strategy="random",
        base_seed=0,
        width=1024,
        height=1600,
        lora_name="",
        clip_model_type="qwen_image",
        pipeline_type="image.unified",
        task=_FakeTask(),
    )

    assert captured["pipeline_type"] == "image.unified"


# ---------------------------------------------------------------------------
# Discovery endpoints: GET /pipelines and /pipelines/{type}/parameters
# ---------------------------------------------------------------------------

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

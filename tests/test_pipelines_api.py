"""Tests that `pipeline_type` is threaded through the image generation API.

Covers the request contract (model defaults/overrides), pipeline-type
validation at the route boundary, and the two pass-through hops that actually
carry the value to the generator: the Celery dispatch and async_process_image.

Self-contained: Celery, Redis, CrewAI, and the ComfyUI client are all faked, so
no broker, network, or real data dir is touched.
"""
from unittest.mock import MagicMock

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
# Deepest hop: async_process_image -> review queue row
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_async_process_image_writes_review_request_with_pipeline_type(
    monkeypatch, clean_tables
):
    from backend import tasks as tasks_module
    from backend.database.generation_requests_storage import GenerationRequestsStorage

    class FakeWorkflow:
        async def process(self, **kwargs):
            return {"generated_prompts": ["a prompt"]}

    class FakeClient:
        async def generate_image(self, **kwargs):
            raise AssertionError("pipeline must NOT dispatch — review queue only")

    monkeypatch.setattr(
        tasks_module, "get_instances",
        lambda: (FakeWorkflow(), FakeClient(), MagicMock()),
    )

    result = await tasks_module.async_process_image(
        dest_image_path="/tmp/img.png",
        persona="p1",
        workflow_type="turbo",
        vision_model="gpt-4o",
        variation_count=1,
        strength_model=1.0,
        seed_strategy="random",
        base_seed=0,
        width=1024,
        height=1024,
        lora_name="lora",
        clip_model_type="qwen_image",
        pipeline_type="image.pose_transfer",
        workflow_overrides={"steps": 20},
        workflow_name="pose.json",
        task=MagicMock(),
    )

    assert result["success"] is True
    assert result["queued_for_review"] == 1
    row = GenerationRequestsStorage().get_request(result["request_ids"][0])
    assert row["status"] == "pending_review"
    assert row["provider"] == "comfy_image"
    assert row["prompt"] == "a prompt"
    assert row["workflow_name"] == "pose.json"
    assert row["settings"]["pipeline_type"] == "image.pose_transfer"
    assert row["settings"]["workflow_overrides"] == {"steps": 20}
    assert row["settings"]["persona"] == "p1"


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


# ---------------------------------------------------------------------------
# workflow_overrides threading: dispatch + async_process_image
# ---------------------------------------------------------------------------

def test_dispatch_forwards_workflow_overrides(monkeypatch):
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

    svc = image_processing.ImageProcessingService()
    svc.dispatch_processing(
        image_path="/x.png", persona="emi", prepare=False,
        workflow_overrides={"125": {"strength_model": 1.3}},
    )
    assert captured["workflow_overrides"] == {"125": {"strength_model": 1.3}}


@pytest.mark.asyncio
async def test_async_process_image_writes_workflow_overrides_to_settings(
    monkeypatch, clean_tables
):
    from backend import tasks as tasks_module
    from backend.database.generation_requests_storage import GenerationRequestsStorage

    class _FakeClient:
        async def generate_image(self, **kwargs):
            raise AssertionError("pipeline must NOT dispatch — review queue only")

    class _FakeWorkflow:
        async def process(self, **kwargs):
            return {"generated_prompts": ["a prompt"]}

    monkeypatch.setattr(
        tasks_module, "get_instances",
        lambda: (_FakeWorkflow(), _FakeClient(), MagicMock()),
    )

    result = await tasks_module.async_process_image(
        dest_image_path="/x.png", persona="emi", workflow_type="turbo",
        vision_model="gpt-4o", variation_count=1, strength_model=0.8,
        seed_strategy="random", base_seed=0, width=1024, height=1600,
        lora_name="", clip_model_type="qwen_image", task=MagicMock(),
        pipeline_type="image.unified",
        workflow_overrides={"125": {"strength_model": 1.3}},
    )

    assert result["success"] is True
    assert result["queued_for_review"] == 1
    row = GenerationRequestsStorage().get_request(result["request_ids"][0])
    assert row["settings"]["workflow_overrides"] == {"125": {"strength_model": 1.3}}

"""
dispatch_generation_request_task: routes an approved generation_requests row
to the right provider, is idempotent, and turns provider errors into
status=failed on that row only.
"""
from unittest.mock import MagicMock, patch

import pytest

from backend.database.generation_requests_storage import GenerationRequestsStorage


@pytest.fixture
def storage(clean_tables):
    return GenerationRequestsStorage()


def _create(storage, provider, settings=None, claim=True):
    result = storage.create_requests([{
        "source_image_path": "/app/processed/img.png",
        "prompt": "a prompt",
        "provider": provider,
        "workflow_name": "wf.json",
        "settings": settings or {},
    }])
    rid = result["request_ids"][0]
    if claim:
        storage.claim_for_dispatch([rid])
    return rid


def test_dispatch_comfy_image(storage):
    from backend import tasks as tasks_module
    rid = _create(storage, "comfy_image", settings={
        "persona": "p1", "workflow_type": "turbo", "pipeline_type": "image.subject_environment",
        "width": 1024, "height": 1024,
    })

    fake_client = MagicMock()
    async def fake_generate_image(**kwargs):
        fake_client.captured = kwargs
        return "exec-img-1"
    fake_client.generate_image = fake_generate_image
    fake_image_storage = MagicMock()

    with patch.object(tasks_module, "get_instances",
                      return_value=(None, fake_client, fake_image_storage)), \
         patch.object(tasks_module.download_execution_task, "apply_async") as mock_dl:
        result = tasks_module.dispatch_generation_request_task.run(rid)

    assert result["execution_id"] == "exec-img-1"
    assert fake_client.captured["positive_prompt"] == "a prompt"
    assert fake_client.captured["pipeline_type"] == "image.subject_environment"
    fake_image_storage.log_execution.assert_called_once()
    mock_dl.assert_called_once()
    row = storage.get_request(rid)
    assert row["status"] == "dispatched"
    assert row["execution_id"] == "exec-img-1"


def test_dispatch_kling_video(storage):
    from backend import tasks as tasks_module
    rid = _create(storage, "kling", settings={"model_name": "kling-v1-6", "mode": "std"})

    with patch("backend.services.video.VideoService") as MockSvc:
        MockSvc.return_value.queue_video.return_value = "kling-task-1"
        result = tasks_module.dispatch_generation_request_task.run(rid)

    assert result["execution_id"] == "kling-task-1"
    assert storage.get_request(rid)["status"] == "dispatched"


def test_dispatch_comfy_video(storage):
    from backend import tasks as tasks_module
    rid = _create(storage, "comfy_video", settings={"mode": "std", "duration": "5"})

    with patch("backend.services.video.VideoService") as MockSvc:
        MockSvc.return_value.queue_video_comfy.return_value = "prompt-id-1"
        result = tasks_module.dispatch_generation_request_task.run(rid)

    assert result["execution_id"] == "prompt-id-1"
    assert storage.get_request(rid)["status"] == "dispatched"


def test_dispatch_provider_error_marks_failed(storage):
    from backend import tasks as tasks_module
    rid = _create(storage, "kling")

    with patch("backend.services.video.VideoService") as MockSvc:
        MockSvc.return_value.queue_video.side_effect = RuntimeError("kling down")
        result = tasks_module.dispatch_generation_request_task.run(rid)

    assert "error" in result
    row = storage.get_request(rid)
    assert row["status"] == "failed"
    assert "kling down" in row["error"]


def test_dispatch_unclaimed_row_skips(storage):
    from backend import tasks as tasks_module
    rid = _create(storage, "kling", claim=False)  # still pending_review
    result = tasks_module.dispatch_generation_request_task.run(rid)
    assert result["skipped"] is True
    assert storage.get_request(rid)["status"] == "pending_review"


def test_poll_kling_video_task_exists():
    from backend.tasks import poll_kling_video_task  # was a phantom import before
    assert poll_kling_video_task.name == "backend.tasks.poll_kling_video_task"

"""
Tests for /api/workspace/* endpoints.
Celery tasks are mocked — no real workers needed.
"""
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from tests.conftest import make_png


# ---- input images ----

def test_list_input_images_empty(client):
    r = client.get("/api/workspace/input-images")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_list_input_images_returns_file(client, input_png):
    r = client.get("/api/workspace/input-images")
    assert r.status_code == 200
    data = r.json()
    filenames = [item["filename"] for item in data]
    assert input_png.name in filenames


def test_list_input_images_fields(client, input_png):
    r = client.get("/api/workspace/input-images")
    items = r.json()
    item = next(i for i in items if i["filename"] == input_png.name)
    assert "size_bytes" in item
    assert "modified_at" in item
    assert "thumbnail_url" in item


def test_input_thumbnail(client, input_png):
    r = client.get(f"/api/workspace/input-images/{input_png.name}/thumbnail")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/jpeg"


def test_input_thumbnail_not_found(client):
    r = client.get("/api/workspace/input-images/ghost.png/thumbnail")
    assert r.status_code == 404


# ---- process ----

def test_process_image_dispatches_task(client, input_png):
    mock_task = MagicMock()
    mock_task.id = "fake-task-123"

    with patch("backend.celery_app.celery_app.send_task", return_value=mock_task):
        r = client.post(
            "/api/workspace/process",
            json={
                "image_path": str(input_png),
                "persona": "Jennie",
                "workflow_type": "turbo",
                "vision_model": "gpt-4o",
                "variation_count": 1,
                "strength": 0.8,
                "seed_strategy": "random",
                "base_seed": 0,
                "width": 1024,
                "height": 1600,
                "lora_name": "",
                "clip_model_type": "sd3",
            },
        )
    assert r.status_code == 200
    assert r.json()["task_id"] == "fake-task-123"


def test_process_image_missing_file(client):
    with patch("backend.celery_app.celery_app.send_task"):
        r = client.post(
            "/api/workspace/process",
            json={
                "image_path": "/nonexistent/path/image.png",
                "persona": "Jennie",
            },
        )
    assert r.status_code == 404


def test_process_batch(client, _temp_dirs):
    imgs = [make_png(_temp_dirs["INPUT_DIR"], f"batch_{i}.png") for i in range(3)]

    mock_task = MagicMock()
    mock_task.id = "batch-task-id"

    with patch("backend.celery_app.celery_app.send_task", return_value=mock_task):
        r = client.post(
            "/api/workspace/process-batch",
            json={
                "image_paths": [str(p) for p in imgs],
                "persona": "Sephera",
                "workflow_type": "turbo",
                "vision_model": "gpt-4o",
                "variation_count": 1,
                "strength": 0.8,
                "seed_strategy": "random",
                "base_seed": 0,
                "width": 1024,
                "height": 1600,
                "lora_name": "",
                "clip_model_type": "sd3",
            },
        )
    assert r.status_code == 200
    data = r.json()
    assert "task_ids" in data
    assert len(data["task_ids"]) == 3


# ---- task status ----

def test_task_status_pending(client):
    mock_result = MagicMock()
    mock_result.state = "PENDING"
    mock_result.info = {}
    mock_result.result = None

    with patch("backend.services.image_processing.AsyncResult", return_value=mock_result):
        r = client.get("/api/workspace/task/some-task-id/status")
    assert r.status_code == 200
    data = r.json()
    assert data["task_id"] == "some-task-id"
    assert data["state"] == "PENDING"


def test_task_status_success(client):
    mock_result = MagicMock()
    mock_result.state = "SUCCESS"
    mock_result.info = {"status": "✅ Done", "progress": 100}
    mock_result.result = {"success": True, "queued_variations": 2}

    with patch("backend.services.image_processing.AsyncResult", return_value=mock_result):
        r = client.get("/api/workspace/task/done-task-id/status")
    assert r.status_code == 200
    data = r.json()
    assert data["state"] == "SUCCESS"
    assert data["progress"] == 100


def test_task_status_failure(client):
    mock_result = MagicMock()
    mock_result.state = "FAILURE"
    mock_result.info = Exception("Something went wrong")
    mock_result.result = None

    with patch("backend.services.image_processing.AsyncResult", return_value=mock_result):
        r = client.get("/api/workspace/task/failed-task/status")
    assert r.status_code == 200
    data = r.json()
    assert data["state"] == "FAILURE"


# ---- executions ----

def test_executions_returns_list(client):
    r = client.get("/api/workspace/executions")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_executions_limit_param(client):
    r = client.get("/api/workspace/executions?limit=5")
    assert r.status_code == 200


def test_executions_invalid_limit(client):
    r = client.get("/api/workspace/executions?limit=0")
    assert r.status_code == 422

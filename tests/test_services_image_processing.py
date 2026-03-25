"""
Unit tests for ImageProcessingService.
Celery dispatch is mocked.
"""
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from tests.conftest import make_png


@pytest.fixture
def svc(_temp_dirs):
    from backend.services.image_processing import ImageProcessingService
    return ImageProcessingService()


def test_scan_input_dir_empty(svc):
    result = svc.scan_input_directory()
    assert isinstance(result, list)


def test_scan_input_dir_finds_files(svc, _temp_dirs):
    img = make_png(_temp_dirs["INPUT_DIR"], "scan_test.png")
    result = svc.scan_input_directory()
    filenames = [r["filename"] for r in result]
    assert "scan_test.png" in filenames


def test_scan_input_dir_fields(svc, _temp_dirs):
    img = make_png(_temp_dirs["INPUT_DIR"], "fields_test.png")
    result = svc.scan_input_directory()
    item = next(r for r in result if r["filename"] == "fields_test.png")
    assert "size_bytes" in item
    assert "modified_at" in item
    assert "thumbnail_url" in item
    assert item["size_bytes"] > 0


def test_prepare_image_creates_ref(svc, _temp_dirs):
    src = make_png(_temp_dirs["INPUT_DIR"], "prepare_src.png")
    dest = svc.prepare_image(str(src))
    assert Path(dest).exists()
    assert Path(dest).name.startswith("ref_")
    assert _temp_dirs["PROCESSED_DIR"] in dest


def test_prepare_image_preserves_extension(svc, _temp_dirs):
    src = make_png(_temp_dirs["INPUT_DIR"], "ext_test.png")
    dest = svc.prepare_image(str(src))
    assert dest.endswith(".png")


def test_prepare_image_missing_raises(svc):
    with pytest.raises(FileNotFoundError):
        svc.prepare_image("/nonexistent/path/image.png")


def test_prepare_image_unique_names(svc, _temp_dirs):
    src = make_png(_temp_dirs["INPUT_DIR"], "unique_src.png")
    dest1 = svc.prepare_image(str(src))
    # Re-create so we can call prepare again
    src2 = make_png(_temp_dirs["INPUT_DIR"], "unique_src2.png")
    dest2 = svc.prepare_image(str(src2))
    assert dest1 != dest2


def test_dispatch_processing_returns_task_id(svc, _temp_dirs):
    src = make_png(_temp_dirs["INPUT_DIR"], "dispatch_test.png")
    mock_task = MagicMock()
    mock_task.id = "test-celery-task-id"

    with patch("backend.celery_app.celery_app.send_task", return_value=mock_task):
        task_id = svc.dispatch_processing(
            image_path=str(src),
            persona="Jennie",
        )
    assert task_id == "test-celery-task-id"


def test_dispatch_batch_returns_multiple_ids(svc, _temp_dirs):
    imgs = [make_png(_temp_dirs["INPUT_DIR"], f"batch_{i}.png") for i in range(3)]
    mock_task = MagicMock()
    mock_task.id = "batch-id"

    with patch("backend.celery_app.celery_app.send_task", return_value=mock_task):
        ids = svc.dispatch_batch([str(p) for p in imgs], persona="Sephera")
    assert len(ids) == 3


def test_get_task_status_pending(svc):
    mock_result = MagicMock()
    mock_result.state = "PENDING"
    mock_result.info = {}
    mock_result.result = None

    with patch("backend.services.image_processing.AsyncResult", return_value=mock_result):
        status = svc.get_task_status("pending-id")

    assert status["state"] == "PENDING"
    assert status["task_id"] == "pending-id"
    assert status["result"] is None


def test_get_task_status_success(svc):
    mock_result = MagicMock()
    mock_result.state = "SUCCESS"
    mock_result.info = {"status": "done", "progress": 100}
    mock_result.result = {"success": True}

    with patch("backend.services.image_processing.AsyncResult", return_value=mock_result):
        status = svc.get_task_status("success-id")

    assert status["state"] == "SUCCESS"
    assert status["progress"] == 100
    assert status["result"]["success"] is True


def test_get_task_status_custom_state(svc):
    mock_result = MagicMock()
    mock_result.state = "GENERATING_PROMPT"
    mock_result.info = {"status": "🤖 Analyzing...", "progress": 40}
    mock_result.result = None

    with patch("backend.services.image_processing.AsyncResult", return_value=mock_result):
        status = svc.get_task_status("custom-state-id")

    assert status["state"] == "GENERATING_PROMPT"
    assert status["progress"] == 40


def test_input_thumbnail_generated(svc, _temp_dirs):
    img = make_png(_temp_dirs["INPUT_DIR"], "thumb_gen.png")
    data = svc.get_input_image_thumbnail("thumb_gen.png")
    assert data is not None
    assert data[:2] == b"\xff\xd8"  # JPEG magic bytes


def test_input_thumbnail_not_found(svc):
    result = svc.get_input_image_thumbnail("ghost.png")
    assert result is None

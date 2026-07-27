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
                "workflow_type": "image_generation",
                "vision_model": "gpt-4o",
                "variation_count": 1,
                "width": 1024,
                "height": 1600,
            },
        )
    assert r.status_code == 200
    assert r.json()["task_id"] == "fake-task-123"


def test_process_image_missing_file(client, _temp_dirs):
    ghost = str(Path(_temp_dirs["INPUT_DIR"]) / "ghost.png")
    with patch("backend.celery_app.celery_app.send_task"):
        r = client.post(
            "/api/workspace/process",
            json={"image_path": ghost, "persona": "Jennie"},
        )
    assert r.status_code == 404


def test_process_image_rejects_path_outside_roots(client):
    """A dispatch path is read off disk and shipped to ComfyUI / a vision model,
    so anything outside the image directories is an arbitrary-file read."""
    with patch("backend.celery_app.celery_app.send_task") as send:
        r = client.post(
            "/api/workspace/process",
            json={"image_path": "/etc/passwd", "persona": "Jennie"},
        )
    assert r.status_code == 400
    assert "outside the allowed directories" in r.json()["detail"]
    send.assert_not_called()


def test_process_image_rejects_traversal_out_of_roots(client, _temp_dirs):
    escape = str(Path(_temp_dirs["INPUT_DIR"]) / ".." / ".." / ".." / "etc" / "passwd")
    with patch("backend.celery_app.celery_app.send_task") as send:
        r = client.post(
            "/api/workspace/process",
            json={"image_path": escape, "persona": "Jennie"},
        )
    assert r.status_code == 400
    send.assert_not_called()


def test_process_batch_rejects_path_outside_roots(client, _temp_dirs):
    good = make_png(_temp_dirs["INPUT_DIR"], "roots_ok.png")
    with patch("backend.celery_app.celery_app.send_task") as send:
        r = client.post(
            "/api/workspace/process-batch",
            json={"image_paths": [str(good), "/etc/hosts"], "persona": "Jennie"},
        )
    assert r.status_code == 400
    send.assert_not_called()  # one bad path fails the whole batch


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
                "workflow_type": "image_generation",
                "vision_model": "gpt-4o",
                "variation_count": 1,
                "width": 1024,
                "height": 1600,
            },
        )
    assert r.status_code == 200
    data = r.json()
    assert "task_ids" in data
    assert len(data["task_ids"]) == 3


def test_process_batch_stamps_identity(client, _temp_dirs, clean_tables):
    """Batch runs must carry project/member like single /process does —
    unstamped runs vanish from the project-scoped run and review lists."""
    from backend.database.projects_storage import ProjectsStorage

    pid = ProjectsStorage().create_project("batch-proj")["id"]
    imgs = [make_png(_temp_dirs["INPUT_DIR"], f"ident_{i}.png") for i in range(2)]

    mock_task = MagicMock()
    mock_task.id = "batch-ident-task"

    with patch("backend.celery_app.celery_app.send_task", return_value=mock_task) as send:
        r = client.post(
            "/api/workspace/process-batch",
            json={
                "image_paths": [str(p) for p in imgs],
                "persona": "Sephera",
                "skip_prepare": True,
            },
            headers={"X-Project-Id": pid, "X-Member-Name": "Batcher"},
        )
    assert r.status_code == 200
    for call in send.call_args_list:
        assert call.kwargs["kwargs"]["project_id"] == pid
        assert call.kwargs["kwargs"]["created_by_member_id"] is not None


# ---- run-direct (image upscaler / multiangle edit / manual prompt) ----

def test_run_direct_dispatches_task(client, input_png, monkeypatch, _temp_dirs):
    import backend.pipelines as pipelines_pkg

    monkeypatch.setattr(
        pipelines_pkg, "list_workflow_files", lambda: ["SeedVR_Image_Upscaler.json"]
    )
    mock_task = MagicMock()
    mock_task.id = "direct-task-1"

    with patch("backend.celery_app.celery_app.send_task", return_value=mock_task) as send:
        r = client.post(
            "/api/workspace/run-direct",
            json={
                "image_paths": [str(input_png)],
                "workflow_name": "SeedVR_Image_Upscaler.json",
                "workflow_type": "image_upscaler",
            },
        )
    assert r.status_code == 200
    assert r.json()["task_ids"] == ["direct-task-1"]
    assert send.call_args.kwargs["kwargs"]["workflow_name"] == "SeedVR_Image_Upscaler.json"
    assert send.call_args.kwargs["kwargs"]["image_path"] == str(input_png)


def test_run_direct_unknown_workflow_404(client, input_png):
    r = client.post(
        "/api/workspace/run-direct",
        json={
            "image_paths": [str(input_png)],
            "workflow_name": "no-such-workflow.json",
            "workflow_type": "image_upscaler",
        },
    )
    assert r.status_code == 404


def test_run_direct_missing_image_404(client, monkeypatch, _temp_dirs):
    import backend.pipelines as pipelines_pkg

    monkeypatch.setattr(
        pipelines_pkg, "list_workflow_files", lambda: ["SeedVR_Image_Upscaler.json"]
    )
    r = client.post(
        "/api/workspace/run-direct",
        json={
            "image_paths": [str(Path(_temp_dirs["INPUT_DIR"]) / "ghost.png")],
            "workflow_name": "SeedVR_Image_Upscaler.json",
            "workflow_type": "image_upscaler",
        },
    )
    assert r.status_code == 404


def test_run_direct_rejects_path_outside_roots(client, monkeypatch):
    """Without a roots check this endpoint uploads any readable file — e.g. a
    service-account key — straight to ComfyUI."""
    import backend.pipelines as pipelines_pkg

    monkeypatch.setattr(
        pipelines_pkg, "list_workflow_files", lambda: ["SeedVR_Image_Upscaler.json"]
    )
    with patch("backend.celery_app.celery_app.send_task") as send:
        r = client.post(
            "/api/workspace/run-direct",
            json={
                "image_paths": ["/etc/passwd"],
                "workflow_name": "SeedVR_Image_Upscaler.json",
                "workflow_type": "image_upscaler",
            },
        )
    assert r.status_code == 400
    assert "outside the allowed directories" in r.json()["detail"]
    send.assert_not_called()


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


# ---- fetch-image (drag & drop from other web pages) ----

def _fetch_image_client_patch(resp=None, error=None, responses=None):
    """Patch httpx.AsyncClient so /fetch-image sees canned responses or an error.

    `stream()` is a plain (non-async) call returning an async context manager,
    so the mock has to mirror that shape rather than being an AsyncMock.
    """
    from unittest.mock import AsyncMock

    queued = list(responses) if responses else None

    def fake_stream(method, url, **kwargs):
        fake_stream.calls.append((str(url), kwargs))
        if error:
            raise error
        current = queued.pop(0) if queued else resp
        cm = AsyncMock()
        cm.__aenter__.return_value = current
        cm.__aexit__.return_value = False
        return cm

    fake_stream.calls = []
    http = MagicMock()
    http.stream = fake_stream
    client_cm = AsyncMock()
    client_cm.__aenter__.return_value = http
    client_cm.__aexit__.return_value = False
    p = patch("backend.api.workspace.httpx.AsyncClient", return_value=client_cm)
    p.stream_calls = fake_stream.calls
    return p


def _resolve_patch(hosts_to_ips=None):
    """Patch DNS resolution: public IP by default, overridable per host."""
    def fake_resolve(host):
        if hosts_to_ips and host in hosts_to_ips:
            return hosts_to_ips[host]
        return ["93.184.216.34"]
    return patch("backend.api.workspace._resolve_host_ips", side_effect=fake_resolve)


def _image_response(content: bytes, content_type: str, headers=None, chunk_size=None):
    """A streamed response. `chunk_size` splits the body so the size cap can be
    observed tripping part-way through instead of after a full buffer."""
    resp = MagicMock()
    resp.headers = {"content-type": content_type, **(headers or {})}
    resp.is_redirect = False
    resp.raise_for_status = MagicMock()
    size = chunk_size or max(len(content), 1)
    resp.streamed = []

    async def aiter_bytes():
        for i in range(0, len(content), size):
            chunk = content[i:i + size]
            resp.streamed.append(len(chunk))
            yield chunk

    resp.aiter_bytes = aiter_bytes
    return resp


def _redirect_response(location: str):
    resp = MagicMock()
    resp.is_redirect = True
    resp.headers = {"location": location}
    return resp


def test_fetch_image_success(client):
    with _resolve_patch(), _fetch_image_client_patch(resp=_image_response(b"\x89PNGdata", "image/png")):
        r = client.post("/api/workspace/fetch-image", json={"url": "https://example.com/pic.png"})
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert r.content == b"\x89PNGdata"


def test_fetch_image_normalizes_jpg_mime(client):
    with _resolve_patch(), _fetch_image_client_patch(resp=_image_response(b"jpg", "image/jpg")):
        r = client.post("/api/workspace/fetch-image", json={"url": "https://example.com/pic"})
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/jpeg"


def test_fetch_image_octet_stream_falls_back_to_url_ext(client):
    with _resolve_patch(), _fetch_image_client_patch(resp=_image_response(b"webp", "application/octet-stream")):
        r = client.post("/api/workspace/fetch-image", json={"url": "https://example.com/pic.webp?w=200"})
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/webp"


def test_fetch_image_rejects_non_image(client):
    with _resolve_patch(), _fetch_image_client_patch(resp=_image_response(b"<html>", "text/html")):
        r = client.post("/api/workspace/fetch-image", json={"url": "https://example.com/page"})
    assert r.status_code == 415


def test_fetch_image_rejects_non_http_scheme(client):
    r = client.post("/api/workspace/fetch-image", json={"url": "file:///etc/passwd"})
    assert r.status_code == 400


def test_fetch_image_rejects_private_address(client):
    with _resolve_patch({"internal.service": ["10.0.0.5"]}), _fetch_image_client_patch():
        r = client.post("/api/workspace/fetch-image", json={"url": "http://internal.service/admin"})
    assert r.status_code == 400
    assert "non-public" in r.json()["detail"]


def test_fetch_image_rejects_loopback(client):
    with _resolve_patch({"localhost": ["127.0.0.1"]}), _fetch_image_client_patch():
        r = client.post("/api/workspace/fetch-image", json={"url": "http://localhost:6379/x.png"})
    assert r.status_code == 400


def test_fetch_image_follows_public_redirect(client):
    responses = [
        _redirect_response("https://cdn.example.com/real.png"),
        _image_response(b"png", "image/png"),
    ]
    with _resolve_patch(), _fetch_image_client_patch(responses=responses):
        r = client.post("/api/workspace/fetch-image", json={"url": "https://example.com/pic"})
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"


def test_fetch_image_rejects_redirect_to_private_address(client):
    responses = [_redirect_response("http://169.254.169.254/latest/meta-data")]
    with _resolve_patch({"169.254.169.254": ["169.254.169.254"]}), _fetch_image_client_patch(responses=responses):
        r = client.post("/api/workspace/fetch-image", json={"url": "https://example.com/pic"})
    assert r.status_code == 400


def test_fetch_image_upstream_error(client):
    import httpx
    with _resolve_patch(), _fetch_image_client_patch(error=httpx.ConnectError("boom")):
        r = client.post("/api/workspace/fetch-image", json={"url": "https://example.com/pic.png"})
    assert r.status_code == 502


def test_fetch_image_too_large(client):
    mb = 1024 * 1024
    big = b"x" * (30 * mb + 1)
    resp = _image_response(big, "image/png", chunk_size=mb)
    with _resolve_patch(), _fetch_image_client_patch(resp=resp):
        r = client.post("/api/workspace/fetch-image", json={"url": "https://example.com/big.png"})
    assert r.status_code == 413
    # Aborted on the chunk that crossed the limit, not after buffering it all.
    assert sum(resp.streamed) <= 31 * mb


def test_fetch_image_rejects_oversized_content_length(client):
    resp = _image_response(b"png", "image/png", headers={"content-length": str(99 * 1024 * 1024)})
    with _resolve_patch(), _fetch_image_client_patch(resp=resp):
        r = client.post("/api/workspace/fetch-image", json={"url": "https://example.com/big.png"})
    assert r.status_code == 413
    assert resp.streamed == []  # rejected before reading a single chunk


def test_fetch_image_connects_to_the_validated_ip(client):
    """The request must be pinned to the address the guard checked, so a second
    DNS lookup can't swing the connection to a private address (rebinding)."""
    patcher = _fetch_image_client_patch(resp=_image_response(b"png", "image/png"))
    with _resolve_patch({"example.com": ["93.184.216.34"]}), patcher:
        r = client.post("/api/workspace/fetch-image", json={"url": "https://example.com/pic.png"})
    assert r.status_code == 200
    (url, kwargs), = patcher.stream_calls
    assert url == "https://93.184.216.34/pic.png"
    assert kwargs["headers"]["Host"] == "example.com"
    assert kwargs["extensions"]["sni_hostname"] == "example.com"


def test_fetch_image_pins_each_redirect_hop(client):
    responses = [
        _redirect_response("https://cdn.example.com/real.png"),
        _image_response(b"png", "image/png"),
    ]
    hosts = {"example.com": ["93.184.216.34"], "cdn.example.com": ["151.101.1.140"]}
    patcher = _fetch_image_client_patch(responses=responses)
    with _resolve_patch(hosts), patcher:
        r = client.post("/api/workspace/fetch-image", json={"url": "https://example.com/pic"})
    assert r.status_code == 200
    assert [url for url, _ in patcher.stream_calls] == [
        "https://93.184.216.34/pic",
        "https://151.101.1.140/real.png",
    ]

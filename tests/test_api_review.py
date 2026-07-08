"""
/api/review/* endpoint tests. Real throwaway Postgres (clean_tables); Celery
dispatch is mocked — no broker, no providers.
"""
import os
from unittest.mock import patch

import pytest

from tests.conftest import make_png
from backend.database.generation_requests_storage import GenerationRequestsStorage


@pytest.fixture
def storage(clean_tables):
    return GenerationRequestsStorage()


def _payload(**overrides):
    # Must live under an allowed image root (PROCESSED_DIR here) — the API
    # rejects paths outside INPUT/PROCESSED/OUTPUT.
    item = {
        "source_image_path": os.path.join(os.environ["PROCESSED_DIR"], "img.png"),
        "prompt": "a prompt",
        "provider": "comfy_image",
        "workflow_name": "wf.json",
        "settings": {"persona": "p1"},
    }
    item.update(overrides)
    return {"items": [item]}


def test_create_and_list(client, storage):
    r = client.post("/api/review/requests", json=_payload())
    assert r.status_code == 200
    body = r.json()
    assert len(body["request_ids"]) == 1

    r = client.get("/api/review/requests?status=pending_review")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 1
    item = data["items"][0]
    assert item["status"] == "pending_review"
    assert item["original_prompt"] == "a prompt"
    assert item["settings"] == {"persona": "p1"}


def test_create_rejects_unknown_provider(client, storage):
    r = client.post("/api/review/requests", json=_payload(provider="dreamania"))
    assert r.status_code == 422


def test_list_invalid_status_422(client, storage):
    assert client.get("/api/review/requests?status=bogus").status_code == 422


def test_patch_prompt(client, storage):
    rid = client.post("/api/review/requests", json=_payload()).json()["request_ids"][0]
    r = client.patch(f"/api/review/requests/{rid}", json={"prompt": "edited"})
    assert r.status_code == 200
    assert r.json()["prompt"] == "edited"


def test_patch_missing_404(client, storage):
    assert client.patch("/api/review/requests/nope", json={"prompt": "x"}).status_code == 404


def test_patch_after_dispatch_409(client, storage):
    rid = client.post("/api/review/requests", json=_payload()).json()["request_ids"][0]
    storage.claim_for_dispatch([rid])
    r = client.patch(f"/api/review/requests/{rid}", json={"prompt": "late"})
    assert r.status_code == 409


def test_discard(client, storage):
    rid = client.post("/api/review/requests", json=_payload()).json()["request_ids"][0]
    r = client.delete(f"/api/review/requests/{rid}")
    assert r.status_code == 200
    assert r.json()["status"] == "discarded"


def test_discard_dispatched_409(client, storage):
    rid = client.post("/api/review/requests", json=_payload()).json()["request_ids"][0]
    storage.claim_for_dispatch([rid])
    storage.begin_dispatch(rid)
    assert client.delete(f"/api/review/requests/{rid}").status_code == 409


def test_dispatch_claims_and_enqueues(client, storage):
    ids = client.post(
        "/api/review/requests",
        json={"items": [
            dict(_payload()["items"][0]),
            dict(_payload(provider="kling")["items"][0]),
        ]},
    ).json()["request_ids"]

    with patch("backend.tasks.dispatch_generation_request_task.apply_async") as mock_aa:
        r = client.post("/api/review/dispatch", json={"ids": ids + ["missing"]})

    assert r.status_code == 200
    body = r.json()
    assert set(body["dispatched"]) == set(ids)
    assert body["skipped"] == ["missing"]
    assert mock_aa.call_count == 2
    queues = {c.kwargs["queue"] for c in mock_aa.call_args_list}
    assert queues == {"image", "video"}  # per-provider routing
    for rid in ids:
        assert storage.get_request(rid)["status"] == "approved"


def test_dispatch_is_idempotent(client, storage):
    rid = client.post("/api/review/requests", json=_payload()).json()["request_ids"][0]
    with patch("backend.tasks.dispatch_generation_request_task.apply_async") as mock_aa:
        client.post("/api/review/dispatch", json={"ids": [rid]})
        r2 = client.post("/api/review/dispatch", json={"ids": [rid]})
    assert r2.json()["dispatched"] == []
    assert mock_aa.call_count == 1


def test_thumbnail_serves_source_image(client, storage, _temp_dirs):
    png = make_png(_temp_dirs["PROCESSED_DIR"], "src.png")
    rid = client.post(
        "/api/review/requests",
        json={"items": [dict(_payload()["items"][0], source_image_path=str(png))]},
    ).json()["request_ids"][0]
    r = client.get(f"/api/review/requests/{rid}/thumbnail")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/jpeg"


def test_thumbnail_missing_file_404(client, storage):
    rid = client.post("/api/review/requests", json=_payload()).json()["request_ids"][0]
    assert client.get(f"/api/review/requests/{rid}/thumbnail").status_code == 404


def test_create_rejects_path_outside_image_roots(client, storage):
    r = client.post(
        "/api/review/requests",
        json={"items": [dict(_payload()["items"][0], source_image_path="/etc/passwd")]},
    )
    assert r.status_code == 422


def test_thumbnail_refuses_row_with_escaped_path(client, storage, tmp_path):
    # A row written outside the API (no ingress validation) must still not
    # leak files outside the image roots via the thumbnail endpoint.
    png = make_png(str(tmp_path), "outside.png")
    created = storage.create_requests([
        {
            "source_image_path": str(png),
            "prompt": "p",
            "provider": "comfy_image",
            "workflow_name": None,
            "settings": {},
        }
    ])
    rid = created["request_ids"][0]
    assert client.get(f"/api/review/requests/{rid}/thumbnail").status_code == 404

"""
Tests for /api/gallery/* endpoints.
Uses real file fixtures (temp directories), no Celery/ComfyUI.
"""
import os
import json
from pathlib import Path

import pytest

from tests.conftest import make_png


# ---- listing ----

def test_gallery_list_pending_empty(client):
    r = client.get("/api/gallery/images?status=pending")
    assert r.status_code == 200
    data = r.json()
    assert "items" in data
    assert "total" in data
    assert "pages" in data


def test_gallery_list_returns_image(_temp_dirs, client, output_png):
    r = client.get("/api/gallery/images?status=pending")
    assert r.status_code == 200
    data = r.json()
    filenames = [item["filename"] for item in data["items"]]
    assert output_png.name in filenames


def test_gallery_list_approved_empty(client):
    r = client.get("/api/gallery/images?status=approved")
    assert r.status_code == 200
    assert r.json()["total"] >= 0


def test_gallery_pagination(client, _temp_dirs):
    """Create 5 images, request per_page=2 and check pages."""
    for i in range(5):
        make_png(_temp_dirs["OUTPUT_DIR"], f"page_test_{i}.png")

    r = client.get("/api/gallery/images?status=pending&per_page=2")
    assert r.status_code == 200
    data = r.json()
    assert data["per_page"] == 2
    assert len(data["items"]) <= 2
    assert data["pages"] >= 1


def test_gallery_invalid_status(client):
    r = client.get("/api/gallery/images?status=invalid")
    assert r.status_code == 422


# ---- thumbnail ----

def test_thumbnail_returns_jpeg(client, output_png):
    r = client.get(f"/api/gallery/images/{output_png.name}/thumbnail?status=pending")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/jpeg"


def test_thumbnail_not_found(client):
    r = client.get("/api/gallery/images/nonexistent.png/thumbnail?status=pending")
    assert r.status_code == 404


# ---- metadata ----

def test_metadata_returns_dict(client, output_png):
    r = client.get(f"/api/gallery/images/{output_png.name}/metadata?status=pending")
    assert r.status_code == 200
    data = r.json()
    assert "seed" in data
    assert "prompt" in data
    assert "raw_metadata" in data


# ---- approve / disapprove / undo ----

def test_approve_image(client, _temp_dirs):
    img = make_png(_temp_dirs["OUTPUT_DIR"], "to_approve.png")
    r = client.post("/api/gallery/approve", json={"filenames": ["to_approve.png"]})
    assert r.status_code == 200
    result = r.json()
    assert result["moved"] == 1
    assert "to_approve.png" not in os.listdir(_temp_dirs["OUTPUT_DIR"])
    assert "to_approve.png" in os.listdir(str(Path(_temp_dirs["OUTPUT_DIR"]) / "approved"))


def test_approve_with_rename(client, _temp_dirs):
    img = make_png(_temp_dirs["OUTPUT_DIR"], "to_rename.png")
    r = client.post(
        "/api/gallery/approve",
        json={"filenames": ["to_rename.png"], "rename_map": {"to_rename.png": "renamed_output"}},
    )
    assert r.status_code == 200
    approved_dir = Path(_temp_dirs["OUTPUT_DIR"]) / "approved"
    approved_files = os.listdir(str(approved_dir))
    assert any("renamed_output" in f for f in approved_files)


def test_disapprove_image(client, _temp_dirs):
    img = make_png(_temp_dirs["OUTPUT_DIR"], "to_disapprove.png")
    r = client.post("/api/gallery/disapprove", json={"filenames": ["to_disapprove.png"]})
    assert r.status_code == 200
    result = r.json()
    assert result["moved"] == 1
    disapproved_dir = Path(_temp_dirs["OUTPUT_DIR"]) / "disapproved"
    assert "to_disapprove.png" in os.listdir(str(disapproved_dir))


def test_undo_approved(client, _temp_dirs):
    # Put an image in approved first
    approved_dir = Path(_temp_dirs["OUTPUT_DIR"]) / "approved"
    img = make_png(str(approved_dir), "to_undo.png")

    r = client.post("/api/gallery/undo", json={"filenames": ["to_undo.png"], "from_status": "approved"})
    assert r.status_code == 200
    result = r.json()
    assert result["moved"] == 1
    assert "to_undo.png" in os.listdir(_temp_dirs["OUTPUT_DIR"])


def test_approve_missing_file(client):
    r = client.post("/api/gallery/approve", json={"filenames": ["does_not_exist.png"]})
    assert r.status_code == 200
    assert r.json()["failed"] == ["does_not_exist.png"]


# ---- stats ----

def test_stats_structure(client):
    r = client.get("/api/gallery/stats")
    assert r.status_code == 200
    data = r.json()
    assert "daily" in data
    assert "totals" in data
    assert "approved" in data["totals"]


# ---- download ----

def test_download_image(client, output_png):
    r = client.get(f"/api/gallery/download/{output_png.name}?status=pending")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"


def test_download_image_not_found(client):
    r = client.get("/api/gallery/download/nonexistent.png")
    assert r.status_code == 404


def test_download_zip_by_filenames(client, _temp_dirs):
    img = make_png(_temp_dirs["OUTPUT_DIR"], "zip_test.png")
    # Move to approved first
    client.post("/api/gallery/approve", json={"filenames": ["zip_test.png"]})

    r = client.post("/api/gallery/download-zip", json={"filenames": ["zip_test.png"]})
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/zip"


def test_download_zip_empty_raises(client):
    r = client.post("/api/gallery/download-zip", json={})
    assert r.status_code == 400


# ---- notes ----

def test_get_notes_returns_dict(client):
    r = client.get("/api/gallery/notes")
    assert r.status_code == 200
    assert isinstance(r.json(), dict)


def test_save_and_read_note(client):
    r = client.put("/api/gallery/notes", json={"date": "2026-03-24", "text": "Good batch today"})
    assert r.status_code == 200

    r2 = client.get("/api/gallery/notes")
    assert r2.json().get("2026-03-24") == "Good batch today"

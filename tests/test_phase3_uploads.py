"""Uploads: rows stamped at upload time; per-project listing; safe thumbnails."""
import io

import pytest
from PIL import Image

from backend.database.projects_storage import ProjectsStorage
from backend.database.uploads_storage import UploadsStorage


@pytest.fixture
def project_id(clean_tables):
    return ProjectsStorage().create_project("uploads-proj")["id"]


def _png_file():
    buf = io.BytesIO()
    Image.new("RGB", (10, 10)).save(buf, format="PNG")
    buf.seek(0)
    return ("files", ("pic.png", buf, "image/png"))


def test_upload_creates_stamped_row(client, project_id):
    r = client.post(
        "/api/workspace/upload",
        files=[_png_file()],
        headers={"X-Member-Name": "Uploader", "X-Project-Id": project_id},
    )
    assert r.status_code == 200
    listing = UploadsStorage().list_uploads(project_id=project_id)
    assert listing["total"] == 1
    row = listing["items"][0]
    assert row["kind"] == "input"
    assert row["project_id"] == project_id
    assert row["created_by_member_id"] is not None


def test_upload_without_headers_lands_unassigned(client, clean_tables):
    r = client.post("/api/workspace/upload", files=[_png_file()])
    assert r.status_code == 200
    listing = UploadsStorage().list_uploads(project_id="unassigned")
    assert listing["total"] == 1
    assert listing["items"][0]["project_id"] is None


def test_ref_upload_kind_ref(client, project_id):
    r = client.post(
        "/api/workspace/ref-images/upload",
        files=[_png_file()],
        headers={"X-Project-Id": project_id},
    )
    assert r.status_code == 200
    listing = UploadsStorage().list_uploads(project_id=project_id)
    assert listing["items"][0]["kind"] == "ref"


def test_uploads_api_list_and_thumbnail(client, project_id):
    client.post("/api/workspace/upload", files=[_png_file()],
                headers={"X-Project-Id": project_id})
    r = client.get("/api/uploads", params={"project_id": project_id})
    assert r.status_code == 200
    upload_id = r.json()["items"][0]["id"]
    r = client.get(f"/api/uploads/{upload_id}/thumbnail")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/jpeg"


def test_thumbnail_refuses_row_with_escaped_path(client, clean_tables):
    row = UploadsStorage().add_upload(
        filename="passwd", path="/etc/passwd", kind="input")
    r = client.get(f"/api/uploads/{row['id']}/thumbnail")
    assert r.status_code == 404

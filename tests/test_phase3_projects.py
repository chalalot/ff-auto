"""Projects CRUD + membership + archived visibility."""
import pytest

from backend.database.members_storage import MembersStorage
from backend.database.projects_storage import ProjectsStorage


@pytest.fixture
def storage(clean_tables):
    return ProjectsStorage()


def test_create_list_get(client, storage):
    r = client.post("/api/projects", json={"name": "Emi Q3", "description": "campaign"},
                    headers={"X-Member-Name": "Khang"})
    assert r.status_code == 200
    proj = r.json()
    assert proj["name"] == "Emi Q3"
    assert proj["owner_member_id"] is not None  # stamped from header

    r = client.get("/api/projects")
    assert [p["id"] for p in r.json()] == [proj["id"]]

    assert storage.exists(proj["id"]) is True
    assert storage.exists("nope") is False


def test_archive_hides_from_default_list(client, storage):
    pid = storage.create_project("temp")["id"]
    r = client.patch(f"/api/projects/{pid}", json={"archived": True})
    assert r.status_code == 200
    assert r.json()["archived_at"] is not None
    assert client.get("/api/projects").json() == []
    listed = client.get("/api/projects", params={"include_archived": "true"}).json()
    assert [p["id"] for p in listed] == [pid]


def test_patch_unknown_project_404(client, clean_tables):
    assert client.patch("/api/projects/nope", json={"name": "x"}).status_code == 404


def test_membership_add_remove(client, storage):
    pid = storage.create_project("p")["id"]
    mid = MembersStorage().get_or_create("Ana")
    r = client.post(f"/api/projects/{pid}/members", json={"member_id": mid})
    assert r.status_code == 200
    assert storage.list_member_ids(pid) == [mid]
    r = client.delete(f"/api/projects/{pid}/members/{mid}")
    assert r.status_code == 200
    assert storage.list_member_ids(pid) == []


def test_identity_resolves_valid_project(storage):
    from backend.api.identity import get_identity
    pid = storage.create_project("live")["id"]
    ident = get_identity(x_member_name=None, x_project_id=pid)
    assert ident.project_id == pid


def test_assign_rows_moves_bucket(client, storage):
    from backend.database.generation_requests_storage import GenerationRequestsStorage
    pid = storage.create_project("assignee")["id"]
    created = GenerationRequestsStorage().create_requests([{
        "source_image_path": "/x/img.png", "prompt": "p", "provider": "comfy_image",
        "settings": {},
    }])
    rid = created["request_ids"][0]
    r = client.post(f"/api/projects/{pid}/assign",
                    json={"table": "generation_requests", "ids": [rid, "ghost"]})
    assert r.status_code == 200
    assert r.json()["updated"] == 1
    from sqlalchemy import text
    from backend.database.engine import session_scope
    with session_scope() as session:
        val = session.execute(
            text("SELECT project_id FROM generation_requests WHERE id = :i"), {"i": rid}
        ).scalar()
    assert val == pid


def test_assign_unknown_table_422(client, storage):
    pid = storage.create_project("p422")["id"]
    r = client.post(f"/api/projects/{pid}/assign",
                    json={"table": "runpod_jobs", "ids": ["1"]})
    assert r.status_code == 422


def test_assign_int_pk_table_coerces_ids(client, storage):
    from backend.database.image_logs_storage import ImageLogsStorage
    pid = storage.create_project("intpk")["id"]
    row_id = ImageLogsStorage().log_execution(execution_id="e1", prompt="p")
    r = client.post(f"/api/projects/{pid}/assign",
                    json={"table": "image_logs", "ids": [str(row_id), "not-an-int"]})
    assert r.status_code == 200
    assert r.json()["updated"] == 1

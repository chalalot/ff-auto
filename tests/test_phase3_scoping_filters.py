"""Project A never sees project B rows; 'unassigned' sees only NULL rows."""
import os

import pytest

from tests.conftest import make_png
from backend.database.generation_requests_storage import GenerationRequestsStorage
from backend.database.image_logs_storage import ImageLogsStorage
from backend.database.projects_storage import ProjectsStorage


@pytest.fixture
def two_projects(clean_tables):
    ps = ProjectsStorage()
    return ps.create_project("A")["id"], ps.create_project("B")["id"]


def _mk_request(project_id=None, prompt="p"):
    return GenerationRequestsStorage().create_requests(
        [{"source_image_path": "/x/i.png", "prompt": prompt,
          "provider": "comfy_image", "settings": {}}],
        project_id=project_id,
    )["request_ids"][0]


def _clear_dir(out):
    for f in os.listdir(out):
        p = os.path.join(out, f)
        if os.path.isfile(p):
            os.remove(p)


def test_review_list_scoped(client, two_projects):
    pa, pb = two_projects
    _mk_request(pa, "in-a"); _mk_request(pb, "in-b"); _mk_request(None, "loose")

    items = client.get("/api/review/requests", params={"project_id": pa}).json()["items"]
    assert [i["prompt"] for i in items] == ["in-a"]

    items = client.get("/api/review/requests",
                       params={"project_id": "unassigned"}).json()["items"]
    assert [i["prompt"] for i in items] == ["loose"]

    assert client.get("/api/review/requests").json()["total"] == 3


def test_gallery_list_scoped(client, two_projects, _temp_dirs):
    pa, pb = two_projects
    out = _temp_dirs["OUTPUT_DIR"]
    _clear_dir(out)
    logs = ImageLogsStorage()
    make_png(out, "a_img.png"); make_png(out, "b_img.png"); make_png(out, "loose.png")
    logs.log_execution(execution_id="ea", prompt="p",
                       project_id=pa, created_by_member_id=None)
    logs.update_result_path(execution_id="ea", result_image_path=f"{out}/a_img.png")
    logs.log_execution(execution_id="eb", prompt="p",
                       project_id=pb, created_by_member_id=None)
    logs.update_result_path(execution_id="eb", result_image_path=f"{out}/b_img.png")

    names = [i["filename"] for i in client.get(
        "/api/gallery/images", params={"status": "pending", "project_id": pa}
    ).json()["items"]]
    assert names == ["a_img.png"]

    names = [i["filename"] for i in client.get(
        "/api/gallery/images", params={"status": "pending", "project_id": "unassigned"}
    ).json()["items"]]
    assert names == ["loose.png"]  # file with no assigned DB row


def test_analysis_scoped(client, two_projects, _temp_dirs):
    pa, _ = two_projects
    out = _temp_dirs["OUTPUT_DIR"]
    _clear_dir(out)
    make_png(out, "an_a.png")
    logs = ImageLogsStorage()
    logs.log_execution(execution_id="eaa", prompt="p", project_id=pa)
    logs.update_result_path(execution_id="eaa", result_image_path=f"{out}/an_a.png")
    data = client.get("/api/analysis", params={"project_id": pa}).json()
    assert [i["filename"] for i in data["items"]] == ["an_a.png"]


def test_evaluations_list_scoped(client, two_projects):
    pa, pb = two_projects
    from backend.database.evaluations_storage import EvaluationsStorage
    es = EvaluationsStorage()
    es.create_pending(media_type="image", media_path="/a.png", prompt=None,
                      model="m", rubric_version="v", project_id=pa)
    es.create_pending(media_type="image", media_path="/b.png", prompt=None,
                      model="m", rubric_version="v", project_id=pb)
    es.create_pending(media_type="image", media_path="/c.png", prompt=None,
                      model="m", rubric_version="v")
    items = client.get("/api/evaluations", params={"project_id": pa}).json()["items"]
    assert [i["media_path"] for i in items] == ["/a.png"]
    items = client.get("/api/evaluations",
                       params={"project_id": "unassigned"}).json()["items"]
    assert [i["media_path"] for i in items] == ["/c.png"]


def test_gallery_stats_scoped(client, two_projects, _temp_dirs):
    pa, _ = two_projects
    out = _temp_dirs["OUTPUT_DIR"]
    _clear_dir(out)
    logs = ImageLogsStorage()
    make_png(out, "st_a.png"); make_png(out, "st_loose.png")
    logs.log_execution(execution_id="est", prompt="p", project_id=pa)
    logs.update_result_path(execution_id="est", result_image_path=f"{out}/st_a.png")

    totals = client.get("/api/gallery/stats", params={"project_id": pa}).json()["totals"]
    assert totals["pending"] == 1 and totals["total"] == 1

    totals = client.get("/api/gallery/stats",
                        params={"project_id": "unassigned"}).json()["totals"]
    assert totals["pending"] == 1

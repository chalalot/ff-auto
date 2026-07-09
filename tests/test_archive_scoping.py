"""Archive list filters result images to the selected project's basenames."""
import pytest

from tests.conftest import make_png
from backend.database.image_logs_storage import ImageLogsStorage
from backend.database.projects_storage import ProjectsStorage
import backend.services.archive as archive_mod


@pytest.fixture
def two_projects(clean_tables):
    ps = ProjectsStorage()
    return ps.create_project("A")["id"], ps.create_project("B")["id"]


def test_archive_list_scoped(client, two_projects, tmp_path, monkeypatch):
    pa, pb = two_projects
    # Point ARCHIVE_BASE at a temp tree: <base>/srv1/results/{a,b}.png
    results = tmp_path / "srv1" / "results"
    results.mkdir(parents=True)
    make_png(str(results), "arc_a.png")
    make_png(str(results), "arc_b.png")
    monkeypatch.setattr(archive_mod, "ARCHIVE_BASE", tmp_path)

    logs = ImageLogsStorage()
    logs.log_execution(execution_id="aa", prompt="p", project_id=pa)
    logs.update_result_path(execution_id="aa", result_image_path="/whatever/arc_a.png")

    names = [i["filename"] for i in client.get(
        "/api/archive/list", params={"project_id": pa}
    ).json()["items"]]
    assert names == ["arc_a.png"]

    # Global view (no project) returns both.
    assert client.get("/api/archive/list").json()["total"] == 2

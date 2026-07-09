"""Video list is scoped by project_id; None aggregates all."""
import pytest

from backend.database.projects_storage import ProjectsStorage
from backend.database.video_logs_storage import VideoLogsStorage


@pytest.fixture
def two_projects(clean_tables):
    ps = ProjectsStorage()
    return ps.create_project("A")["id"], ps.create_project("B")["id"]


def _mk_video(project_id, execution_id, prompt):
    VideoLogsStorage().log_execution(
        execution_id=execution_id, prompt=prompt,
        source_image_path="/x/i.png", project_id=project_id,
    )


def test_video_list_scoped(client, two_projects):
    pa, pb = two_projects
    _mk_video(pa, "va", "in-a")
    _mk_video(pb, "vb", "in-b")
    _mk_video(None, "vc", "loose")

    items = client.get("/api/video/list", params={"project_id": pa}).json()["items"]
    assert [i["prompt"] for i in items] == ["in-a"]

    assert client.get("/api/video/list").json()["total"] == 3

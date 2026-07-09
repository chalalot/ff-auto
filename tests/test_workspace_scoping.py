"""Workspace Library (ref images) and Execution History scope by project_id.

None aggregates all; a project id restricts; legacy rows (no project) show
only in the global view — matching the Gallery/Archive contract.
"""
import os

import pytest

from tests.conftest import make_png
from backend.database.image_logs_storage import ImageLogsStorage
from backend.database.projects_storage import ProjectsStorage
from backend.database.uploads_storage import UploadsStorage


@pytest.fixture
def two_projects(clean_tables):
    ps = ProjectsStorage()
    return ps.create_project("A")["id"], ps.create_project("B")["id"]


def _clear_dir(out):
    for f in os.listdir(out):
        p = os.path.join(out, f)
        if os.path.isfile(p):
            os.remove(p)


def test_executions_scoped(client, two_projects):
    pa, pb = two_projects
    logs = ImageLogsStorage()
    logs.log_execution(execution_id="xa", prompt="in-a", project_id=pa)
    logs.log_execution(execution_id="xb", prompt="in-b", project_id=pb)
    logs.log_execution(execution_id="xc", prompt="loose", project_id=None)

    rows = client.get("/api/workspace/executions", params={"project_id": pa}).json()
    assert [r["prompt"] for r in rows] == ["in-a"]

    # Global view returns all three.
    assert len(client.get("/api/workspace/executions").json()) == 3


def test_ref_library_scoped(client, two_projects, _temp_dirs):
    pa, pb = two_projects
    processed = _temp_dirs["PROCESSED_DIR"]
    _clear_dir(processed)
    make_png(processed, "ref_a.png")
    make_png(processed, "ref_b.png")
    make_png(processed, "ref_loose.png")  # on disk but never uploaded under a project

    uploads = UploadsStorage()
    uploads.add_upload(filename="ref_a.png", path=f"{processed}/ref_a.png",
                       kind="ref", project_id=pa)
    uploads.add_upload(filename="ref_b.png", path=f"{processed}/ref_b.png",
                       kind="ref", project_id=pb)

    names = [i["filename"] for i in client.get(
        "/api/workspace/ref-images", params={"project_id": pa}
    ).json()]
    assert names == ["ref_a.png"]

    # Global view returns every file on disk, including the unassigned one.
    all_names = {i["filename"] for i in client.get("/api/workspace/ref-images").json()}
    assert all_names == {"ref_a.png", "ref_b.png", "ref_loose.png"}

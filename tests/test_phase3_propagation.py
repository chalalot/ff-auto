"""Scoping copies from generation_requests to logs; ingress stamps evals/exports."""
from unittest.mock import MagicMock, patch

import pytest

from backend.database.generation_requests_storage import GenerationRequestsStorage
from backend.database.image_logs_storage import ImageLogsStorage
from backend.database.projects_storage import ProjectsStorage
from backend.database.members_storage import MembersStorage


@pytest.fixture
def scoped_request(clean_tables):
    pid = ProjectsStorage().create_project("prop-proj")["id"]
    mid = MembersStorage().get_or_create("Propagator")
    created = GenerationRequestsStorage().create_requests(
        [{
            "source_image_path": "/x/img.png", "prompt": "p",
            "provider": "comfy_image", "settings": {},
        }],
        project_id=pid, created_by_member_id=mid,
    )
    rid = created["request_ids"][0]
    GenerationRequestsStorage().claim_for_dispatch([rid])
    return rid, pid, mid


def test_dispatch_copies_scoping_to_image_log(scoped_request):
    rid, pid, mid = scoped_request
    from backend import tasks as tasks_mod

    fake_client = MagicMock()
    fake_client.generate_image = MagicMock()
    with patch.object(tasks_mod, "get_instances",
                      return_value=(MagicMock(), fake_client, ImageLogsStorage())), \
         patch.object(tasks_mod.asyncio, "run", return_value="exec-prop-1"), \
         patch.object(tasks_mod.download_execution_task, "apply_async"):
        tasks_mod.dispatch_generation_request_task.run(rid)

    from sqlalchemy import text
    from backend.database.engine import session_scope
    with session_scope() as session:
        rec = session.execute(text(
            "SELECT project_id, created_by_member_id FROM image_logs WHERE execution_id = :e"
        ), {"e": "exec-prop-1"}).one()
    assert rec.project_id == pid and rec.created_by_member_id == mid


def test_evaluation_create_stamped(client, clean_tables, monkeypatch):
    pid = ProjectsStorage().create_project("eval-proj")["id"]
    from backend.services.evaluation import EvaluationService
    monkeypatch.setattr(
        EvaluationService, "evaluate",
        lambda self, request, project_id=None, member_id=None: {
            "id": 1, "status": "pending", "media_type": request.media_type,
            "media_path": request.media_path, "model": "m",
            "rubric_version": "v1", "created_at": "2026-07-08 00:00:00",
            "project_id": project_id,
        },
    )
    r = client.post("/api/evaluations",
                    json={"media_type": "image", "media_path": "/x/a.png"},
                    headers={"X-Project-Id": pid})
    assert r.status_code == 200


def test_evaluations_storage_create_pending_stamps(clean_tables):
    from backend.database.evaluations_storage import EvaluationsStorage
    pid = ProjectsStorage().create_project("es-proj")["id"]
    eid = EvaluationsStorage().create_pending(
        media_type="image", media_path="/x/a.png", prompt=None,
        model="m", rubric_version="v1", project_id=pid,
    )
    rows = EvaluationsStorage().list_evaluations(limit=5)
    assert any(r["id"] == eid for r in rows)

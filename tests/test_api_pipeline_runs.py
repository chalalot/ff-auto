from backend.database.pipeline_runs_storage import PipelineRunsStorage
from backend.database.engine import session_scope
from backend.database.models import Project


def test_get_pipeline_run_returns_ordered_live_trace(client, clean_tables):
    storage = PipelineRunsStorage()
    run_id = storage.create_run("image_to_prompt", {"image_path": "ref.png"}, None, None)
    storage.start_run(run_id)
    storage.create_step(run_id, "analyst", 2)
    vision_id = storage.create_step(run_id, "vision_observation", 1)
    storage.start_step(vision_id, {"image_path": "ref.png"}, None, None, "gpt-4o")
    storage.complete_step(vision_id, {"observation": "subject"}, None)

    response = client.get(f"/api/pipeline-runs/{run_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == run_id
    assert body["status"] == "running"
    assert [step["step_key"] for step in body["steps"]] == [
        "vision_observation",
        "analyst",
    ]
    assert body["steps"][0]["output_payload"] == {"observation": "subject"}
    assert body["steps"][1]["status"] == "queued"


def test_get_pipeline_run_returns_failed_trace(client, clean_tables):
    storage = PipelineRunsStorage()
    run_id = storage.create_run("image_to_prompt", {}, None, None)
    step_id = storage.create_step(run_id, "analyst", 2)
    storage.start_step(step_id, {}, "system", [], "gpt-4o")
    storage.fail_step(step_id, {"type": "ValueError", "message": "failed"}, None)
    storage.fail_run(run_id, {"type": "ValueError", "message": "failed"})

    response = client.get(f"/api/pipeline-runs/{run_id}")

    assert response.status_code == 200
    assert response.json()["status"] == "failed"
    assert response.json()["steps"][0]["error"]["message"] == "failed"


def test_get_missing_pipeline_run_returns_404(client):
    response = client.get("/api/pipeline-runs/missing")

    assert response.status_code == 404
    assert response.json()["detail"] == "Pipeline run not found"


def test_fail_closes_out_a_run_no_worker_will_finish(client, clean_tables):
    storage = PipelineRunsStorage()
    # Queued and never picked up — the shape that accumulated in the dev DB and
    # kept the history list polling every 5s for work that wasn't happening.
    run_id = storage.create_run("image_to_prompt", {}, None, None)

    response = client.post(f"/api/pipeline-runs/{run_id}/fail")

    assert response.status_code == 200
    assert response.json()["status"] == "failed"
    body = client.get(f"/api/pipeline-runs/{run_id}").json()
    assert body["status"] == "failed"
    assert body["finished_at"] is not None


def test_fail_a_running_run(client, clean_tables):
    storage = PipelineRunsStorage()
    run_id = storage.create_run("image_to_prompt", {}, None, None)
    storage.start_run(run_id)

    assert client.post(f"/api/pipeline-runs/{run_id}/fail").status_code == 200


def test_fail_refuses_a_finished_run(client, clean_tables):
    storage = PipelineRunsStorage()
    run_id = storage.create_run("image_to_prompt", {}, None, None)
    storage.complete_run(run_id, {"prompt": "done"})

    response = client.post(f"/api/pipeline-runs/{run_id}/fail")

    # A stray click must not rewrite a run that already landed.
    assert response.status_code == 409
    assert client.get(f"/api/pipeline-runs/{run_id}").json()["status"] == "succeeded"


def test_fail_missing_run_returns_404(client, clean_tables):
    assert client.post("/api/pipeline-runs/missing/fail").status_code == 404


def test_in_flight_finds_a_stalled_run_the_recent_list_hides(client, clean_tables):
    storage = PipelineRunsStorage()
    stalled = storage.create_run("image_to_prompt", {}, None, None)
    for _ in range(5):
        finished = storage.create_run("image_to_prompt", {}, None, None)
        storage.complete_run(finished, {})

    # The recent window is newest-first, so the stalled run drops out of it.
    recent = client.get("/api/pipeline-runs?limit=3").json()
    assert stalled not in [r["id"] for r in recent]

    in_flight = client.get("/api/pipeline-runs?in_flight=true").json()

    assert [r["id"] for r in in_flight] == [stalled]
    assert client.post(f"/api/pipeline-runs/{stalled}/fail").status_code == 200
    assert client.get("/api/pipeline-runs?in_flight=true").json() == []


def test_list_pipeline_runs_returns_summaries(client, clean_tables):
    storage = PipelineRunsStorage()
    with session_scope() as session:
        session.add(Project(id="project-a", name="Project A"))
    run_id = storage.create_run("image_to_prompt", {"image_path": "ref.png"}, "project-a", None)

    response = client.get("/api/pipeline-runs?project_id=project-a")

    assert response.status_code == 200
    assert response.json()[0]["id"] == run_id
    assert "steps" not in response.json()[0]

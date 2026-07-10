from backend.database.pipeline_runs_storage import PipelineRunsStorage


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

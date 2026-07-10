from backend.database.pipeline_runs_storage import PipelineRunsStorage


def test_run_and_steps_round_trip(clean_tables):
    storage = PipelineRunsStorage()
    run_id = storage.create_run(
        "image_to_prompt",
        {"image_path": "ref.png"},
        None,
        None,
    )
    storage.create_step(run_id, "analyst", 2)
    vision_id = storage.create_step(run_id, "vision_observation", 1)

    storage.start_step(
        vision_id,
        {"prompt": "observe"},
        None,
        None,
        "gpt-4o",
    )
    storage.complete_step(
        vision_id,
        {"observation": "subject"},
        {"input_tokens": 3},
    )

    trace = storage.get_run_with_steps(run_id)

    assert trace["pipeline_name"] == "image_to_prompt"
    assert [step["step_key"] for step in trace["steps"]] == [
        "vision_observation",
        "analyst",
    ]
    assert trace["steps"][0]["status"] == "succeeded"
    assert trace["steps"][0]["output_payload"] == {"observation": "subject"}
    assert trace["steps"][0]["usage"] == {"input_tokens": 3}


def test_step_failure_and_run_failure_are_readable(clean_tables):
    storage = PipelineRunsStorage()
    run_id = storage.create_run("image_to_prompt", {}, None, None)
    step_id = storage.create_step(run_id, "analyst", 2)

    storage.start_step(step_id, {"input": "x"}, "system", [], "gpt-4o")
    storage.fail_step(
        step_id,
        {"type": "ValueError", "message": "model failed"},
        {"partial": "response"},
    )
    storage.fail_run(
        run_id,
        {"type": "ValueError", "message": "model failed"},
    )

    trace = storage.get_run_with_steps(run_id)

    assert trace["status"] == "failed"
    assert trace["error"]["message"] == "model failed"
    assert trace["steps"][0]["status"] == "failed"
    assert trace["steps"][0]["partial_output"] == {"partial": "response"}
    assert trace["steps"][0]["system_prompt"] == "system"


def test_missing_run_returns_none(clean_tables):
    assert PipelineRunsStorage().get_run_with_steps("missing") is None

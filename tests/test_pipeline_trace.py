from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from backend.services.pipeline_trace import (
    PipelineTraceRecorder,
    TraceLiteLLMCallback,
    normalize_payload,
)


@pytest.fixture
def fake_storage():
    storage = MagicMock()
    storage.create_step.side_effect = ["step-1", "step-2"]
    return storage


def test_failed_step_is_persisted_with_error(fake_storage):
    recorder = PipelineTraceRecorder(fake_storage, "run-1")

    with pytest.raises(ValueError):
        with recorder.step("analyst", 2, {"observation": "x"}):
            raise ValueError("model failed")

    fake_storage.fail_step.assert_called_once()
    args = fake_storage.fail_step.call_args.args
    assert args[0] == "step-1"
    assert args[1] == {"type": "ValueError", "message": "model failed"}


def test_successful_step_persists_prompt_and_output(fake_storage):
    recorder = PipelineTraceRecorder(fake_storage, "run-1")

    with recorder.step("analyst", 2, {"observation": "x"}) as step:
        step.capture_prompt("system", [{"role": "user", "content": "x"}], "gpt-4o")
        step.capture_output("analysis", {"output_tokens": 4})

    fake_storage.update_step_prompt.assert_called_once_with(
        "step-1",
        "system",
        [{"role": "user", "content": "x"}],
        "gpt-4o",
    )
    fake_storage.complete_step.assert_called_once_with(
        "step-1", "analysis", {"output_tokens": 4}
    )


def test_normalize_payload_marks_truncation():
    result = normalize_payload({"long": "abcdefghij"}, max_chars=20)

    assert result["truncated"] is True
    assert result["original_length"] > 20
    assert isinstance(result["value"], str)


def test_callback_captures_messages_without_credentials(fake_storage):
    recorder = PipelineTraceRecorder(fake_storage, "run-1")
    with recorder.step("analyst", 2) as step:
        callback = TraceLiteLLMCallback()
        callback.log_success_event(
            {
                "model": "gpt-4o",
                "messages": [{"role": "system", "content": "secret prompt"}],
                "api_key": "do-not-store",
                "authorization": "Bearer do-not-store",
            },
            {"choices": [{"message": {"content": "answer"}}]},
            datetime.now(timezone.utc),
            datetime.now(timezone.utc),
        )

    call_payload = fake_storage.append_llm_call.call_args.args[1]
    assert call_payload["request"]["messages"][0]["content"] == "secret prompt"
    assert "api_key" not in call_payload["request"]
    assert "authorization" not in call_payload["request"]
    assert call_payload["response"]["choices"][0]["message"]["content"] == "answer"


def test_step_captures_tool_calls(fake_storage):
    recorder = PipelineTraceRecorder(fake_storage, "run-1")

    with recorder.step("analyst", 2) as step:
        step.append_tool_call(
            "Skill Reader",
            {"ref_path": "SKILL.md"},
            "skill contents",
        )

    fake_storage.append_tool_call.assert_called_once_with(
        "step-1",
        {
            "tool": "Skill Reader",
            "input": {"ref_path": "SKILL.md"},
            "output": "skill contents",
        },
    )


def test_step_persistence_failure_does_not_fail_workflow():
    class BrokenStorage:
        def create_step(self, *args, **kwargs):
            raise RuntimeError("database unavailable")

    recorder = PipelineTraceRecorder(BrokenStorage(), "run-1")
    with recorder.step("analyst", 2) as step:
        step.capture_output("workflow output")

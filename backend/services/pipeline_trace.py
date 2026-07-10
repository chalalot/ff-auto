import json
import logging
import os
from contextvars import ContextVar, Token
from datetime import datetime
from typing import Any, Optional

from backend.database.pipeline_runs_storage import PipelineRunsStorage

logger = logging.getLogger(__name__)

DEFAULT_MAX_CHARS = 200_000
_SENSITIVE_KEYS = {
    "api_key",
    "apikey",
    "authorization",
    "access_token",
    "id_token",
    "client_secret",
    "password",
    "secret",
}

current_trace_step: ContextVar[Optional["PipelineStepRecorder"]] = ContextVar(
    "current_trace_step", default=None
)


def _max_chars() -> int:
    raw = os.getenv("PIPELINE_TRACE_MAX_CHARS", str(DEFAULT_MAX_CHARS))
    try:
        return max(1, int(raw))
    except ValueError:
        return DEFAULT_MAX_CHARS


def _is_sensitive_key(key: object) -> bool:
    normalized = str(key).lower().replace("-", "_")
    return normalized in _SENSITIVE_KEYS or normalized.endswith("_api_key")


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): "[REDACTED]" if _is_sensitive_key(key) else _sanitize(item)
            for key, item in value.items()
            if not _is_sensitive_key(key)
        }
    if isinstance(value, (list, tuple)):
        return [_sanitize(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if hasattr(value, "model_dump"):
        return _sanitize(value.model_dump())
    if hasattr(value, "dict") and callable(value.dict):
        return _sanitize(value.dict())
    if hasattr(value, "__dict__"):
        return _sanitize(vars(value))
    return str(value)


def normalize_payload(value: Any, max_chars: Optional[int] = None) -> Any:
    """Return JSON-safe data with an explicit marker when it is too large."""
    normalized = _sanitize(value)
    limit = max_chars if max_chars is not None else _max_chars()
    encoded = json.dumps(normalized, ensure_ascii=True, default=str)
    if len(encoded) <= limit:
        return normalized
    return {
        "value": encoded[:limit],
        "truncated": True,
        "original_length": len(encoded),
    }


def _timestamp(value: Any) -> Optional[str]:
    return value.isoformat() if isinstance(value, datetime) else None


class PipelineStepRecorder:
    def __init__(
        self,
        storage: PipelineRunsStorage,
        step_id: str,
        step_key: str,
        sequence: int,
        input_payload: Any,
    ):
        self.storage = storage
        self.step_id = step_id
        self.step_key = step_key
        self.sequence = sequence
        self.input_payload = normalize_payload(input_payload)
        self.output_payload: Any = None
        self.usage: Optional[dict] = None
        self._context_token: Optional[Token] = None

    def __enter__(self) -> "PipelineStepRecorder":
        self.storage.start_step(
            self.step_id,
            self.input_payload,
            None,
            None,
            None,
        )
        self._context_token = current_trace_step.set(self)
        return self

    def __exit__(self, exc_type, exc_value, _traceback) -> bool:
        try:
            if exc_value is None:
                self.storage.complete_step(
                    self.step_id,
                    normalize_payload(self.output_payload),
                    normalize_payload(self.usage) if self.usage is not None else None,
                )
            else:
                self.storage.fail_step(
                    self.step_id,
                    {
                        "type": exc_type.__name__ if exc_type else "Exception",
                        "message": str(exc_value),
                    },
                    normalize_payload(self.output_payload),
                )
        except Exception as storage_error:
            logger.warning(
                "[pipeline_trace] failed to persist step %s: %s",
                self.step_key,
                storage_error,
            )
        finally:
            if self._context_token is not None:
                current_trace_step.reset(self._context_token)
        return False

    def capture_prompt(
        self,
        system_prompt: Optional[str],
        rendered_context: Any,
        model_name: Optional[str],
    ) -> None:
        self.storage.update_step_prompt(
            self.step_id,
            normalize_payload(system_prompt),
            normalize_payload(rendered_context),
            model_name,
        )

    def capture_output(self, output_payload: Any, usage: Optional[dict] = None) -> None:
        self.output_payload = output_payload
        self.usage = usage

    def append_llm_call(self, call_payload: dict) -> None:
        self.storage.append_llm_call(self.step_id, normalize_payload(call_payload))


class PipelineTraceRecorder:
    def __init__(self, storage: PipelineRunsStorage, run_id: str):
        self.storage = storage
        self.run_id = run_id

    def step(
        self,
        step_key: str,
        sequence: int,
        input_payload: Any = None,
    ) -> PipelineStepRecorder:
        step_id = self.storage.create_step(self.run_id, step_key, sequence)
        return PipelineStepRecorder(
            self.storage,
            step_id,
            step_key,
            sequence,
            input_payload,
        )


class TraceLiteLLMCallback:
    def _record(
        self,
        kwargs: dict,
        response_obj: Any,
        start_time: Any,
        end_time: Any,
        error: Optional[Exception] = None,
    ) -> None:
        step = current_trace_step.get()
        if step is None:
            return
        call_payload = {
            "request": normalize_payload(kwargs),
            "response": normalize_payload(response_obj),
            "model": kwargs.get("model"),
            "started_at": _timestamp(start_time),
            "finished_at": _timestamp(end_time),
        }
        if error is not None:
            call_payload["error"] = {
                "type": type(error).__name__,
                "message": str(error),
            }
        try:
            step.append_llm_call(call_payload)
        except Exception as callback_error:
            logger.warning("[pipeline_trace] callback capture failed: %s", callback_error)

    def log_success_event(self, kwargs, response_obj, start_time, end_time):
        self._record(kwargs, response_obj, start_time, end_time)

    def log_failure_event(self, kwargs, response_obj, start_time, end_time):
        error = response_obj if isinstance(response_obj, Exception) else None
        self._record(kwargs, response_obj, start_time, end_time, error)

    async def async_log_success_event(self, kwargs, response_obj, start_time, end_time):
        self.log_success_event(kwargs, response_obj, start_time, end_time)

    async def async_log_failure_event(self, kwargs, response_obj, start_time, end_time):
        self.log_failure_event(kwargs, response_obj, start_time, end_time)


_TRACE_CALLBACK: Optional[TraceLiteLLMCallback] = None


def install_litellm_trace_callback() -> TraceLiteLLMCallback:
    global _TRACE_CALLBACK
    import litellm

    if _TRACE_CALLBACK is None:
        _TRACE_CALLBACK = TraceLiteLLMCallback()
    if _TRACE_CALLBACK not in litellm.callbacks:
        litellm.callbacks.append(_TRACE_CALLBACK)
    return _TRACE_CALLBACK

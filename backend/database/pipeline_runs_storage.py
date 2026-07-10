import logging
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import select, update

from .engine import session_scope
from .models import PipelineRun, PipelineStep

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _run_dict(row: PipelineRun) -> dict:
    return {
        "id": row.id,
        "pipeline_name": row.pipeline_name,
        "status": row.status,
        "input_payload": row.input_payload,
        "final_output": row.final_output,
        "error": row.error,
        "started_at": row.started_at,
        "finished_at": row.finished_at,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "project_id": row.project_id,
        "created_by_member_id": row.created_by_member_id,
    }


def _run_summary_dict(row: PipelineRun) -> dict:
    return {
        "id": row.id,
        "pipeline_name": row.pipeline_name,
        "status": row.status,
        "input_payload": row.input_payload,
        "error": row.error,
        "started_at": row.started_at,
        "finished_at": row.finished_at,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "project_id": row.project_id,
        "created_by_member_id": row.created_by_member_id,
    }


def _step_dict(row: PipelineStep) -> dict:
    return {
        "id": row.id,
        "run_id": row.run_id,
        "step_key": row.step_key,
        "sequence": row.sequence,
        "status": row.status,
        "input_payload": row.input_payload,
        "system_prompt": row.system_prompt,
        "rendered_context": row.rendered_context,
        "output_payload": row.output_payload,
        "usage": row.usage,
        "partial_output": row.partial_output,
        "error": row.error,
        "model_name": row.model_name,
        "started_at": row.started_at,
        "finished_at": row.finished_at,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


class PipelineRunsStorage:
    def create_run(
        self,
        pipeline_name: str,
        input_payload: dict,
        project_id: Optional[str],
        created_by_member_id: Optional[str],
    ) -> str:
        run_id = str(uuid4())
        with session_scope() as session:
            session.add(
                PipelineRun(
                    id=run_id,
                    pipeline_name=pipeline_name,
                    status="queued",
                    input_payload=input_payload,
                    project_id=project_id,
                    created_by_member_id=created_by_member_id,
                )
            )
        return run_id

    def create_step(self, run_id: str, step_key: str, sequence: int) -> str:
        step_id = str(uuid4())
        with session_scope() as session:
            session.add(
                PipelineStep(
                    id=step_id,
                    run_id=run_id,
                    step_key=step_key,
                    sequence=sequence,
                    status="queued",
                )
            )
        return step_id

    def start_run(self, run_id: str) -> None:
        now = _now()
        with session_scope() as session:
            session.execute(
                update(PipelineRun)
                .where(PipelineRun.id == run_id)
                .values(status="running", started_at=now, updated_at=now)
            )

    def start_step(
        self,
        step_id: str,
        input_payload: dict | None,
        system_prompt: str | None,
        rendered_context: Any,
        model_name: str | None,
    ) -> None:
        now = _now()
        with session_scope() as session:
            session.execute(
                update(PipelineStep)
                .where(PipelineStep.id == step_id)
                .values(
                    status="running",
                    input_payload=input_payload,
                    system_prompt=system_prompt,
                    rendered_context=rendered_context,
                    model_name=model_name,
                    started_at=now,
                    updated_at=now,
                )
            )

    def append_llm_call(self, step_id: str, call_payload: dict) -> None:
        with session_scope() as session:
            row = session.execute(
                select(PipelineStep).where(PipelineStep.id == step_id)
            ).scalars().first()
            if row is None:
                return
            context = row.rendered_context
            if isinstance(context, dict):
                context = {
                    "workflow_context": context,
                    "llm_calls": [call_payload],
                }
            elif isinstance(context, list):
                context = {"llm_calls": [*context, call_payload]}
            elif context is None:
                context = {"llm_calls": [call_payload]}
            else:
                context = {
                    "workflow_context": str(context),
                    "llm_calls": [call_payload],
                }
            row.rendered_context = context
            row.updated_at = _now()

    def update_step_prompt(
        self,
        step_id: str,
        system_prompt: str | None,
        rendered_context: Any,
        model_name: str | None,
    ) -> None:
        with session_scope() as session:
            session.execute(
                update(PipelineStep)
                .where(PipelineStep.id == step_id)
                .values(
                    system_prompt=system_prompt,
                    rendered_context=rendered_context,
                    model_name=model_name,
                    updated_at=_now(),
                )
            )

    def complete_step(
        self,
        step_id: str,
        output_payload: Any,
        usage: dict | None,
    ) -> None:
        now = _now()
        with session_scope() as session:
            session.execute(
                update(PipelineStep)
                .where(PipelineStep.id == step_id)
                .values(
                    status="succeeded",
                    output_payload=output_payload,
                    usage=usage,
                    finished_at=now,
                    updated_at=now,
                )
            )

    def fail_step(
        self,
        step_id: str,
        error: dict,
        partial_output: Any,
    ) -> None:
        now = _now()
        with session_scope() as session:
            session.execute(
                update(PipelineStep)
                .where(PipelineStep.id == step_id)
                .values(
                    status="failed",
                    error=error,
                    partial_output=partial_output,
                    finished_at=now,
                    updated_at=now,
                )
            )

    def complete_run(self, run_id: str, final_output: dict | None) -> None:
        now = _now()
        with session_scope() as session:
            session.execute(
                update(PipelineRun)
                .where(PipelineRun.id == run_id)
                .values(
                    status="succeeded",
                    final_output=final_output,
                    finished_at=now,
                    updated_at=now,
                )
            )

    def fail_run(self, run_id: str, error: dict) -> None:
        now = _now()
        with session_scope() as session:
            session.execute(
                update(PipelineRun)
                .where(PipelineRun.id == run_id)
                .values(status="failed", error=error, finished_at=now, updated_at=now)
            )

    def get_run_with_steps(self, run_id: str) -> Optional[dict]:
        with session_scope() as session:
            run = session.execute(
                select(PipelineRun).where(PipelineRun.id == run_id)
            ).scalars().first()
            if run is None:
                return None
            steps = session.execute(
                select(PipelineStep)
                .where(PipelineStep.run_id == run_id)
                .order_by(PipelineStep.sequence.asc())
            ).scalars().all()
            result = _run_dict(run)
            result["steps"] = [_step_dict(step) for step in steps]
            return result

    def list_runs(
        self,
        limit: int = 20,
        project_id: Optional[str] = None,
    ) -> list[dict]:
        with session_scope() as session:
            query = select(PipelineRun)
            if project_id is not None:
                query = query.where(PipelineRun.project_id == project_id)
            query = query.order_by(
                PipelineRun.created_at.desc(), PipelineRun.id.desc()
            ).limit(limit)
            runs = session.execute(query).scalars().all()
            return [_run_summary_dict(run) for run in runs]

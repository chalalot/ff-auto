"""
Task 2 tests: alembic baseline migration, session_scope semantics, and a
round-trip through every declarative model.

Runs against the throwaway postgres from docker-compose.test.yml only.
"""
import pytest
from sqlalchemy import inspect, select

EXPECTED_TABLES = {
    "evaluations",
    "image_logs",
    "video_logs",
    "runpod_jobs",
    "caption_exports",
    "runs",
    "posts",
}


def test_migration_creates_all_tables(migrated_engine):
    names = set(inspect(migrated_engine).get_table_names())
    missing = EXPECTED_TABLES - names
    assert not missing, f"alembic upgrade head did not create: {missing}"


def test_runpod_job_id_is_unique(migrated_engine):
    constraints = inspect(migrated_engine).get_unique_constraints("runpod_jobs")
    indexes = inspect(migrated_engine).get_indexes("runpod_jobs")
    unique_cols = {tuple(c["column_names"]) for c in constraints} | {
        tuple(i["column_names"]) for i in indexes if i.get("unique")
    }
    assert ("job_id",) in unique_cols


def test_posts_and_runs_indexes_exist(migrated_engine):
    insp = inspect(migrated_engine)
    post_indexes = {i["name"] for i in insp.get_indexes("posts")}
    run_indexes = {i["name"] for i in insp.get_indexes("runs")}
    assert "idx_posts_run_id" in post_indexes
    assert "idx_runs_created_at" in run_indexes


def test_session_scope_rolls_back_on_error(migrated_engine, clean_tables):
    from backend.database.engine import session_scope
    from backend.database.models import Evaluation

    with pytest.raises(RuntimeError, match="boom"):
        with session_scope() as session:
            session.add(
                Evaluation(
                    media_type="image",
                    media_path="/x/a.png",
                    model="gpt",
                    rubric_version="v1",
                )
            )
            session.flush()
            raise RuntimeError("boom")

    with session_scope() as session:
        assert session.execute(select(Evaluation)).scalars().all() == []


def test_session_scope_commits_on_success(migrated_engine, clean_tables):
    from backend.database.engine import session_scope
    from backend.database.models import Evaluation

    with session_scope() as session:
        session.add(
            Evaluation(
                media_type="image",
                media_path="/x/b.png",
                model="gpt",
                rubric_version="v1",
            )
        )

    with session_scope() as session:
        rows = session.execute(select(Evaluation)).scalars().all()
        assert len(rows) == 1
        assert rows[0].status == "pending"  # server default
        assert rows[0].scores_json == "[]"  # server default
        assert rows[0].created_at is not None  # server default


def test_models_roundtrip(migrated_engine, clean_tables):
    """Insert + read one row per model."""
    from backend.database.engine import session_scope
    from backend.database.models import (
        CaptionExport,
        Evaluation,
        ImageLog,
        Post,
        Run,
        RunpodJob,
        VideoLog,
    )

    with session_scope() as session:
        session.add(
            Evaluation(
                media_type="video",
                media_path="/m/v.mp4",
                prompt="p",
                model="gemini",
                rubric_version="production-v1",
            )
        )
        session.add(
            ImageLog(execution_id="exec-1", prompt="an image", persona="dancer")
        )
        session.add(
            VideoLog(
                execution_id="exec-2",
                prompt="a video",
                batch_id="batch-1",
                filename_id="f-1",
            )
        )
        session.add(
            RunpodJob(
                job_id="job-1",
                endpoint_id="ep-1",
                lora_name="lora",
                submitted_at="2026-07-06T00:00:00",
                job_input='{"k": 1}',
            )
        )
        session.add(
            CaptionExport(
                file_id="file-1",
                filename="captions.zip",
                public_url="https://x/y.zip",
                image_count=3,
                exported_at="2026-07-06T00:00:00",
            )
        )
        session.add(
            Run(
                id="run-1",
                persona_name="dancer",
                trend_text="trend",
                num_posts=1,
                adapted_idea={"idea": "x"},
                metadata_={"m": 1},
                created_at=1751760000,
                updated_at=1751760000,
            )
        )
        # Flush so the run row exists before the post's FK references it
        # (mirrors real usage: save_run and save_post are separate calls).
        session.flush()
        session.add(
            Post(
                id="post-1",
                run_id="run-1",
                post_index=0,
                caption="hi",
                hashtags=["#a", "#b"],
                visual_plan={"scene": "beach"},
                metadata_={"tier": "a"},
                created_at=1751760000,
                updated_at=1751760000,
            )
        )

    with session_scope() as session:
        ev = session.execute(select(Evaluation)).scalar_one()
        assert (ev.media_type, ev.status) == ("video", "pending")

        il = session.execute(select(ImageLog)).scalar_one()
        assert (il.execution_id, il.status) == ("exec-1", "pending")

        vl = session.execute(select(VideoLog)).scalar_one()
        assert (vl.batch_id, vl.status) == ("batch-1", "pending")

        rj = session.execute(select(RunpodJob)).scalar_one()
        assert rj.job_id == "job-1"

        ce = session.execute(select(CaptionExport)).scalar_one()
        assert ce.image_count == 3

        run = session.execute(select(Run)).scalar_one()
        assert run.adapted_idea == {"idea": "x"}
        assert run.metadata_ == {"m": 1}

        post = session.execute(select(Post)).scalar_one()
        assert post.hashtags == ["#a", "#b"]  # TEXT[] round-trips as list
        assert post.visual_plan == {"scene": "beach"}  # JSONB round-trips
        assert post.run_id == "run-1"


def test_posts_cascade_on_run_delete(migrated_engine, clean_tables):
    from sqlalchemy import delete

    from backend.database.engine import session_scope
    from backend.database.models import Post, Run

    with session_scope() as session:
        session.add(
            Run(
                id="run-c",
                persona_name="p",
                trend_text="t",
                num_posts=1,
                created_at=1,
                updated_at=1,
            )
        )
        session.flush()
        session.add(
            Post(id="post-c", run_id="run-c", post_index=0, created_at=1, updated_at=1)
        )

    with session_scope() as session:
        session.execute(delete(Run).where(Run.id == "run-c"))

    with session_scope() as session:
        assert session.execute(select(Post)).scalars().all() == []


def test_engine_import_does_not_connect(monkeypatch):
    """Importing backend.database.engine must not open a DB connection."""
    import importlib
    import sys

    monkeypatch.setenv("DATABASE_URL", "postgresql://nobody:nope@127.0.0.1:1/nodb")
    original = sys.modules.get("backend.database.engine")
    sys.modules.pop("backend.database.engine", None)
    try:
        module = importlib.import_module("backend.database.engine")
        assert hasattr(module, "get_engine")
    finally:
        # Restore the original module object (if any) so modules that bound
        # to it earlier and later importers agree on one engine singleton —
        # leaving a fresh third copy behind causes order-dependent failures.
        if original is not None:
            sys.modules["backend.database.engine"] = original
        else:
            sys.modules.pop("backend.database.engine", None)

"""
Task 6 tests: idempotent sqlite -> postgres data migration.

Fixture sqlite files are built in-test with the LEGACY DDL (as it existed in
the sqlite storage modules), then migrated into the throwaway postgres.
"""
import sqlite3

import pytest
from sqlalchemy import select, text

from backend.database.engine import session_scope
from backend.database.models import (
    CaptionExport,
    Evaluation,
    ImageLog,
    RunpodJob,
    VideoLog,
)
from scripts.migrate_sqlite_to_pg import migrate


@pytest.fixture
def sqlite_dir(tmp_path):
    """Build legacy-shaped sqlite fixture files: evaluations.db, image_logs.db
    (which also carries runpod_jobs + caption_exports, as in production), and
    video_logs.db."""
    ev = sqlite3.connect(tmp_path / "evaluations.db")
    ev.execute(
        """
        CREATE TABLE evaluations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            media_type TEXT NOT NULL,
            media_path TEXT NOT NULL,
            prompt TEXT,
            model TEXT NOT NULL,
            rubric_version TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            scores_json TEXT NOT NULL DEFAULT '[]',
            overall_score REAL,
            summary TEXT,
            error_message TEXT,
            raw_response TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP
        )
        """
    )
    ev.execute(
        "INSERT INTO evaluations (id, media_type, media_path, model, rubric_version,"
        " status, scores_json, overall_score, created_at, completed_at) VALUES"
        " (7, 'image', '/x/a.png', 'gemini', 'v1', 'completed',"
        " '[{\"dimension\": \"d\", \"score\": 4, \"rationale\": \"r\"}]', 4.0,"
        " '2026-07-01 10:30:00', '2026-07-01 10:31:22')"
    )
    ev.execute(
        "INSERT INTO evaluations (id, media_type, media_path, model, rubric_version)"
        " VALUES (9, 'video', '/x/b.mp4', 'gemini', 'v1')"
    )
    ev.commit()
    ev.close()

    il = sqlite3.connect(tmp_path / "image_logs.db")
    il.execute(
        """
        CREATE TABLE image_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            execution_id TEXT NOT NULL,
            prompt TEXT NOT NULL,
            persona TEXT,
            image_ref_path TEXT,
            result_image_path TEXT,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    il.execute(
        "INSERT INTO image_logs (id, execution_id, prompt, persona, status,"
        " created_at) VALUES (3, 'exec-1', 'p1', 'dancer', 'completed',"
        " '2026-06-30 08:00:00')"
    )
    il.execute(
        """
        CREATE TABLE runpod_jobs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id      TEXT NOT NULL UNIQUE,
            endpoint_id TEXT NOT NULL,
            lora_name   TEXT NOT NULL,
            submitted_at TEXT NOT NULL,
            job_input   TEXT NOT NULL,
            status      TEXT,
            output      TEXT,
            updated_at  TEXT
        )
        """
    )
    il.execute(
        "INSERT INTO runpod_jobs (id, job_id, endpoint_id, lora_name, submitted_at,"
        " job_input, status) VALUES (2, 'job-1', 'ep-1', 'lora', '2026-06-01T00:00:00',"
        " '{\"k\": 1}', 'COMPLETED')"
    )
    il.execute(
        """
        CREATE TABLE caption_exports (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id      TEXT NOT NULL,
            filename     TEXT NOT NULL,
            public_url   TEXT NOT NULL,
            image_count  INTEGER NOT NULL DEFAULT 0,
            exported_at  TEXT NOT NULL
        )
        """
    )
    il.execute(
        "INSERT INTO caption_exports (id, file_id, filename, public_url, image_count,"
        " exported_at) VALUES (5, 'f-1', 'c.zip', 'https://u', 3, '2026-06-15T12:00:00')"
    )
    il.commit()
    il.close()

    vl = sqlite3.connect(tmp_path / "video_logs.db")
    vl.execute(
        """
        CREATE TABLE video_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id TEXT,
            execution_id TEXT NOT NULL,
            prompt TEXT NOT NULL,
            source_image_path TEXT,
            video_output_path TEXT,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            filename_id TEXT
        )
        """
    )
    vl.execute(
        "INSERT INTO video_logs (id, batch_id, execution_id, prompt, status,"
        " created_at) VALUES (11, 'batch-1', 'task-1', 'vp', 'completed',"
        " '2026-07-02 23:59:59')"
    )
    vl.commit()
    vl.close()

    return tmp_path


def test_migration_copies_rows_preserving_ids(sqlite_dir, clean_tables):
    stats = migrate(str(sqlite_dir))

    assert stats["evaluations"]["sqlite_rows"] == 2
    assert stats["evaluations"]["pg_before"] == 0
    assert stats["evaluations"]["pg_after"] == 2

    with session_scope() as session:
        ev = session.get(Evaluation, 7)
        assert ev is not None
        assert ev.status == "completed"
        assert ev.overall_score == 4.0

        assert session.get(Evaluation, 9).media_type == "video"
        assert session.get(ImageLog, 3).execution_id == "exec-1"
        assert session.get(VideoLog, 11).batch_id == "batch-1"
        rj = session.execute(select(RunpodJob)).scalar_one()
        assert (rj.id, rj.job_id) == (2, "job-1")
        ce = session.execute(select(CaptionExport)).scalar_one()
        assert (ce.id, ce.exported_at) == (5, "2026-06-15T12:00:00")


def test_migration_parses_legacy_timestamps_as_utc(sqlite_dir, clean_tables):
    migrate(str(sqlite_dir))
    with session_scope() as session:
        ev = session.get(Evaluation, 7)
        created = ev.created_at
        assert created.tzinfo is not None
        assert created.utcoffset().total_seconds() == 0
        assert created.strftime("%Y-%m-%d %H:%M:%S") == "2026-07-01 10:30:00"
        assert ev.completed_at.strftime("%Y-%m-%d %H:%M:%S") == "2026-07-01 10:31:22"


def test_migration_is_idempotent(sqlite_dir, clean_tables):
    migrate(str(sqlite_dir))
    stats = migrate(str(sqlite_dir))  # second run inserts nothing
    for table, s in stats.items():
        assert s["pg_before"] == s["pg_after"], f"{table} changed on second run"


def test_sequences_continue_after_explicit_ids(sqlite_dir, clean_tables):
    migrate(str(sqlite_dir))
    # A fresh insert must get an id above the migrated max, not collide.
    with session_scope() as session:
        row = Evaluation(
            media_type="image", media_path="/new.png", model="m", rubric_version="v1"
        )
        session.add(row)
        session.flush()
        assert row.id == 10  # max migrated id was 9

        il = ImageLog(execution_id="new", prompt="p")
        session.add(il)
        session.flush()
        assert il.id == 4  # max migrated id was 3


def test_missing_files_warn_and_skip(tmp_path, clean_tables, capsys):
    stats = migrate(str(tmp_path))  # empty dir: nothing to migrate
    assert stats == {}
    out = capsys.readouterr().out
    assert "skip" in out.lower() or "not found" in out.lower()


def test_dry_run_inserts_nothing(sqlite_dir, clean_tables):
    stats = migrate(str(sqlite_dir), dry_run=True)
    assert stats["evaluations"]["sqlite_rows"] == 2
    with session_scope() as session:
        assert session.execute(select(Evaluation)).scalars().all() == []


def test_conflicting_rows_are_skipped_not_overwritten(sqlite_dir, clean_tables):
    # Pre-seed pg with an evaluation at id 7 that differs from sqlite's.
    with session_scope() as session:
        session.add(
            Evaluation(
                id=7,
                media_type="image",
                media_path="/already/here.png",
                model="m",
                rubric_version="v1",
            )
        )
    stats = migrate(str(sqlite_dir))
    assert stats["evaluations"]["pg_before"] == 1
    assert stats["evaluations"]["pg_after"] == 2  # only id 9 added
    with session_scope() as session:
        assert session.get(Evaluation, 7).media_path == "/already/here.png"


def test_table_split_across_files_is_merged(tmp_path, clean_tables, capsys):
    """A table appearing in several sqlite files (empty auto-created copy in
    image_logs.db + real rows in a standalone db) must merge ALL files' rows,
    not silently first-file-win."""
    ddl = """
        CREATE TABLE runpod_jobs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id      TEXT NOT NULL UNIQUE,
            endpoint_id TEXT NOT NULL,
            lora_name   TEXT NOT NULL,
            submitted_at TEXT NOT NULL,
            job_input   TEXT NOT NULL,
            status      TEXT,
            output      TEXT,
            updated_at  TEXT
        )
    """
    il = sqlite3.connect(tmp_path / "image_logs.db")
    il.execute(ddl)
    il.execute(
        "INSERT INTO runpod_jobs (id, job_id, endpoint_id, lora_name,"
        " submitted_at, job_input) VALUES"
        " (1, 'job-a', 'ep', 'l', '2026-06-01T00:00:00', '{}')"
    )
    il.commit()
    il.close()

    standalone = sqlite3.connect(tmp_path / "runpod_jobs.db")
    standalone.execute(ddl)
    standalone.execute(
        "INSERT INTO runpod_jobs (id, job_id, endpoint_id, lora_name,"
        " submitted_at, job_input) VALUES"
        " (2, 'job-b', 'ep', 'l', '2026-06-02T00:00:00', '{}')"
    )
    standalone.commit()
    standalone.close()

    stats = migrate(str(tmp_path))

    assert stats["runpod_jobs"]["sqlite_rows"] == 2  # cumulative across files
    assert stats["runpod_jobs"]["pg_after"] == 2
    out = capsys.readouterr().out
    assert "WARNING" in out and "runpod_jobs" in out

    with session_scope() as session:
        job_ids = {r.job_id for r in session.execute(select(RunpodJob)).scalars()}
    assert job_ids == {"job-a", "job-b"}


LEGACY_RUNS_DDL = """
    CREATE TABLE runs (
        id TEXT PRIMARY KEY,
        persona_name TEXT NOT NULL,
        trend_text TEXT NOT NULL,
        num_posts INTEGER NOT NULL,
        adapted_idea JSONB,
        trend_profile JSONB,
        metadata JSONB,
        created_at BIGINT NOT NULL,
        updated_at BIGINT NOT NULL
    )
"""

# Deliberately WITHOUT versions/current_version: an older live DB.
LEGACY_POSTS_DDL = """
    CREATE TABLE posts (
        id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
        post_index INTEGER NOT NULL,
        caption TEXT,
        hashtags TEXT[],
        cta TEXT,
        image_url TEXT,
        image_prompt TEXT,
        positive_prompt TEXT,
        negative_prompt TEXT,
        visual_plan JSONB,
        content_seed JSONB,
        metadata JSONB,
        created_at BIGINT NOT NULL,
        updated_at BIGINT NOT NULL
    )
"""


@pytest.fixture
def legacy_pg_url(database_url):
    """A second database in the throwaway postgres, shaped like the legacy
    runs/posts DB (no versions/current_version columns)."""
    from sqlalchemy import create_engine

    admin = create_engine(database_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text("DROP DATABASE IF EXISTS ffauto_legacy_src WITH (FORCE)"))
        conn.execute(text("CREATE DATABASE ffauto_legacy_src"))
    admin.dispose()

    src_url = database_url.rsplit("/", 1)[0] + "/ffauto_legacy_src"
    src = create_engine(src_url)
    with src.begin() as conn:
        conn.execute(text(LEGACY_RUNS_DDL))
        conn.execute(text(LEGACY_POSTS_DDL))
        conn.execute(
            text(
                "INSERT INTO runs (id, persona_name, trend_text, num_posts,"
                " metadata, created_at, updated_at) VALUES"
                " ('run-1', 'dancer', 'trend', 2, '{\"k\": 1}', 100, 100)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO posts (id, run_id, post_index, caption, hashtags,"
                " created_at, updated_at) VALUES"
                " ('post-1', 'run-1', 0, 'cap', ARRAY['a','b'], 100, 100)"
            )
        )
    src.dispose()
    return src_url


def test_runs_posts_copied_from_legacy_postgres(
    tmp_path, legacy_pg_url, clean_tables
):
    from backend.database.models import Post, Run

    stats = migrate(str(tmp_path), source_database_url=legacy_pg_url)

    assert stats["runs"]["pg_after"] == 1
    assert stats["posts"]["pg_after"] == 1
    with session_scope() as session:
        run = session.get(Run, "run-1")
        assert run.persona_name == "dancer"
        assert run.metadata_ == {"k": 1}
        post = session.get(Post, "post-1")
        assert post.hashtags == ["a", "b"]
        # Columns absent from the legacy source keep their defaults.
        assert post.versions is None
        assert post.current_version is None


def test_runs_posts_skipped_when_source_is_target(
    tmp_path, database_url, clean_tables, capsys
):
    stats = migrate(str(tmp_path), source_database_url=database_url)
    assert "runs" not in stats and "posts" not in stats
    assert "same DB" in capsys.readouterr().out


def test_runs_posts_warns_when_no_source_given(tmp_path, clean_tables, capsys):
    migrate(str(tmp_path))
    out = capsys.readouterr().out
    assert "NOT migrated" in out

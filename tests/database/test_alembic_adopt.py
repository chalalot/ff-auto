"""
Adoption path for the 0001 baseline migration.

`alembic upgrade head` must work against a database that ALREADY contains the
legacy runs/posts tables (created by the old psycopg2 RunsPostsStorage outside
Alembic): skip creating what exists, create the five sqlite-era tables, and
add posts.versions / posts.current_version if the legacy table lacks them.
"""
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text

from tests.database.test_migrate_sqlite_to_pg import (
    LEGACY_POSTS_DDL,
    LEGACY_RUNS_DDL,
)

REPO_ROOT = Path(__file__).resolve().parents[2]

EXPECTED_TABLES = {
    "caption_exports",
    "evaluations",
    "image_logs",
    "runpod_jobs",
    "runs",
    "video_logs",
    "posts",
}


@pytest.fixture
def adopt_db_url(database_url):
    """A second database holding ONLY legacy runs/posts (one row each)."""
    admin = create_engine(database_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text("DROP DATABASE IF EXISTS ffauto_adopt WITH (FORCE)"))
        conn.execute(text("CREATE DATABASE ffauto_adopt"))
    admin.dispose()

    url = database_url.rsplit("/", 1)[0] + "/ffauto_adopt"
    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(text(LEGACY_RUNS_DDL))
        conn.execute(text(LEGACY_POSTS_DDL))
        conn.execute(
            text(
                "INSERT INTO runs (id, persona_name, trend_text, num_posts,"
                " created_at, updated_at) VALUES ('run-1', 'p', 't', 1, 1, 1)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO posts (id, run_id, post_index, created_at,"
                " updated_at) VALUES ('post-1', 'run-1', 0, 1, 1)"
            )
        )
    engine.dispose()
    return url


def test_upgrade_adopts_existing_runs_posts(adopt_db_url, monkeypatch):
    from alembic import command
    from alembic.config import Config

    # env.py resolves the URL via get_postgres_connection_string(), which
    # reads DATABASE_URL first.
    monkeypatch.setenv("DATABASE_URL", adopt_db_url)

    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option(
        "script_location", str(REPO_ROOT / "backend" / "database" / "alembic")
    )
    command.upgrade(cfg, "head")  # must NOT raise DuplicateTable

    engine = create_engine(adopt_db_url)
    try:
        inspector = inspect(engine)
        assert EXPECTED_TABLES <= set(inspector.get_table_names())

        # Version columns were added to the adopted posts table.
        post_cols = {c["name"] for c in inspector.get_columns("posts")}
        assert {"versions", "current_version"} <= post_cols

        with engine.connect() as conn:
            # Pre-existing data untouched.
            assert conn.execute(text("SELECT count(*) FROM runs")).scalar() == 1
            assert conn.execute(text("SELECT count(*) FROM posts")).scalar() == 1
            # And the DB is stamped at head.
            assert (
                conn.execute(
                    text("SELECT version_num FROM alembic_version")
                ).scalar()
                == "0001"
            )
    finally:
        engine.dispose()

"""
Fixtures for database-layer tests.

All tests here run against the THROWAWAY postgres from docker-compose.test.yml
(random host port, tmpfs, isolated network). They must never touch the live
stack or any real mounted data. The connection URL is resolved by:

  1. TEST_DATABASE_URL env var, if set, else
  2. asking docker compose for the random host port of `postgres-test`.

Start the stack first:  docker compose -f docker-compose.test.yml up -d
"""
import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILE = REPO_ROOT / "docker-compose.test.yml"


def _discover_test_database_url() -> str:
    explicit = os.getenv("TEST_DATABASE_URL")
    if explicit:
        return explicit

    result = subprocess.run(
        [
            "docker", "compose", "-f", str(COMPOSE_FILE),
            "port", "postgres-test", "5432",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 or not result.stdout.strip():
        pytest.fail(
            "Throwaway test postgres is not running. Start it with:\n"
            f"  docker compose -f {COMPOSE_FILE} up -d\n"
            f"(stderr: {result.stderr.strip()})"
        )
    port = result.stdout.strip().rsplit(":", 1)[1]
    return f"postgresql://test:test@localhost:{port}/ffauto_test"


@pytest.fixture(scope="session")
def database_url():
    """Resolve the throwaway DB URL and export it as DATABASE_URL."""
    url = _discover_test_database_url()
    os.environ["DATABASE_URL"] = url
    return url


@pytest.fixture(scope="session")
def migrated_engine(database_url):
    """A SQLAlchemy engine bound to a freshly-migrated (alembic head) test DB."""
    from sqlalchemy import create_engine, text

    from alembic import command
    from alembic.config import Config

    # Wipe everything so `alembic upgrade head` runs from a clean slate.
    admin_engine = create_engine(database_url)
    with admin_engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    admin_engine.dispose()

    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option(
        "script_location", str(REPO_ROOT / "backend" / "database" / "alembic")
    )
    command.upgrade(cfg, "head")

    from backend.database.engine import get_engine

    engine = get_engine()
    yield engine


@pytest.fixture()
def clean_tables(migrated_engine):
    """Truncate all application tables before each test (schema stays)."""
    from sqlalchemy import text

    from backend.database.models import Base

    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    with migrated_engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    yield

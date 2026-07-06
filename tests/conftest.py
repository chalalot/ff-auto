"""
Shared fixtures for ff-auto backend tests.

All tests run against temporary directories — no real Sorted/, processed/, or
results/ directories are touched.

Database fixtures (`database_url`, `migrated_engine`, `clean_tables`) bind
exclusively to the THROWAWAY postgres from docker-compose.test.yml (random
host port, tmpfs, isolated network). They are lazy: tests that don't request
them never touch a database. Start the stack first:

    docker compose -f docker-compose.test.yml up -d
"""
import os
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[1]
COMPOSE_TEST_FILE = REPO_ROOT / "docker-compose.test.yml"


def _discover_test_database_url() -> str:
    explicit = os.getenv("TEST_DATABASE_URL")
    if explicit:
        return explicit

    result = subprocess.run(
        [
            "docker", "compose", "-f", str(COMPOSE_TEST_FILE),
            "port", "postgres-test", "5432",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 or not result.stdout.strip():
        pytest.fail(
            "Throwaway test postgres is not running. Start it with:\n"
            f"  docker compose -f {COMPOSE_TEST_FILE} up -d\n"
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

    yield get_engine()


@pytest.fixture()
def clean_tables(migrated_engine):
    """Truncate all application tables before each test (schema stays)."""
    from sqlalchemy import text

    from backend.database.models import Base

    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    with migrated_engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    yield

# Point all directory env vars to temp paths before any backend import
@pytest.fixture(autouse=True, scope="session")
def _temp_dirs(tmp_path_factory):
    base = tmp_path_factory.mktemp("ff_auto")
    dirs = {
        "INPUT_DIR": str(base / "Sorted"),
        "PROCESSED_DIR": str(base / "processed"),
        "OUTPUT_DIR": str(base / "results"),
        "PROMPTS_DIR": str(base / "prompts"),
    }
    for path in dirs.values():
        os.makedirs(path, exist_ok=True)
    os.makedirs(str(base / "results" / "approved"), exist_ok=True)
    os.makedirs(str(base / "results" / "disapproved"), exist_ok=True)
    os.makedirs(str(base / "prompts" / "presets"), exist_ok=True)
    os.makedirs(str(base / "prompts" / "personas"), exist_ok=True)

    with patch.dict(os.environ, dirs):
        yield dirs


@pytest.fixture(scope="session")
def app(_temp_dirs):
    from backend.main import app
    return app


@pytest.fixture(scope="session")
def client(app):
    return TestClient(app)


# ---- Helper: create a fake PNG in a directory ----

def make_png(directory: str, filename: str = "test.png") -> Path:
    """Create a minimal valid 1x1 PNG file for testing."""
    from PIL import Image
    import io

    path = Path(directory) / filename
    img = Image.new("RGB", (100, 100), color=(128, 64, 32))
    img.save(str(path), format="PNG")
    return path


@pytest.fixture
def sample_png(tmp_path):
    """A temp PNG file usable as input."""
    return make_png(str(tmp_path), "sample.png")


@pytest.fixture
def input_png(_temp_dirs):
    """A PNG dropped into INPUT_DIR."""
    return make_png(_temp_dirs["INPUT_DIR"], "input_test.png")


@pytest.fixture
def output_png(_temp_dirs):
    """A PNG dropped into OUTPUT_DIR (pending)."""
    return make_png(_temp_dirs["OUTPUT_DIR"], "result_pending_test.png")

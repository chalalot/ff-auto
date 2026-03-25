"""
Shared fixtures for ff-auto backend tests.

All tests run against temporary directories — no real Sorted/, processed/, or
results/ directories are touched.
"""
import os
import json
import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

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

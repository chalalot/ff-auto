"""
Unit tests for GalleryService — direct service calls, no HTTP.
"""
import os
from pathlib import Path

import pytest

from tests.conftest import make_png


@pytest.fixture
def svc(_temp_dirs):
    # Re-import after env vars are patched
    from backend.services.gallery import GalleryService
    return GalleryService()


def test_list_images_empty(svc):
    result = svc.list_images(status="pending")
    assert result["total"] >= 0
    assert result["page"] == 1


def test_list_images_returns_created_file(svc, _temp_dirs):
    img = make_png(_temp_dirs["OUTPUT_DIR"], "svc_list_test.png")
    result = svc.list_images(status="pending")
    filenames = [i["filename"] for i in result["items"]]
    assert img.name in filenames


def test_list_images_pagination(svc, _temp_dirs):
    for i in range(6):
        make_png(_temp_dirs["OUTPUT_DIR"], f"svc_page_{i}.png")
    result = svc.list_images(status="pending", page=1, per_page=3)
    assert len(result["items"]) <= 3
    assert result["pages"] >= 2


def test_thumbnail_generated(svc, _temp_dirs):
    img = make_png(_temp_dirs["OUTPUT_DIR"], "svc_thumb.png")
    data = svc.get_thumbnail("svc_thumb.png", status="pending")
    assert data is not None
    assert len(data) > 0
    # Verify it's a JPEG (starts with FF D8)
    assert data[:2] == b"\xff\xd8"


def test_thumbnail_cached(svc, _temp_dirs):
    img = make_png(_temp_dirs["OUTPUT_DIR"], "svc_cache.png")
    data1 = svc.get_thumbnail("svc_cache.png", status="pending")
    data2 = svc.get_thumbnail("svc_cache.png", status="pending")
    assert data1 == data2


def test_extract_metadata_no_embed(svc, _temp_dirs):
    img = make_png(_temp_dirs["OUTPUT_DIR"], "svc_meta.png")
    meta = svc.extract_metadata("svc_meta.png", status="pending")
    assert meta["seed"] is None
    assert meta["prompt"] is None
    assert isinstance(meta["raw_metadata"], dict)


def test_approve_moves_file(svc, _temp_dirs):
    img = make_png(_temp_dirs["OUTPUT_DIR"], "svc_approve.png")
    result = svc.approve_images(["svc_approve.png"])
    assert result["moved"] == 1
    assert not (Path(_temp_dirs["OUTPUT_DIR"]) / "svc_approve.png").exists()
    assert (Path(_temp_dirs["OUTPUT_DIR"]) / "approved" / "svc_approve.png").exists()


def test_approve_with_rename(svc, _temp_dirs):
    img = make_png(_temp_dirs["OUTPUT_DIR"], "svc_rename.png")
    result = svc.approve_images(["svc_rename.png"], rename_map={"svc_rename.png": "final_name"})
    assert result["moved"] == 1
    approved_files = os.listdir(str(Path(_temp_dirs["OUTPUT_DIR"]) / "approved"))
    assert any("final_name" in f for f in approved_files)


def test_approve_missing_returns_failed(svc):
    result = svc.approve_images(["does_not_exist.png"])
    assert result["moved"] == 0
    assert "does_not_exist.png" in result["failed"]


def test_disapprove_moves_file(svc, _temp_dirs):
    img = make_png(_temp_dirs["OUTPUT_DIR"], "svc_disapp.png")
    result = svc.disapprove_images(["svc_disapp.png"])
    assert result["moved"] == 1
    assert (Path(_temp_dirs["OUTPUT_DIR"]) / "disapproved" / "svc_disapp.png").exists()


def test_undo_from_approved(svc, _temp_dirs):
    approved_dir = Path(_temp_dirs["OUTPUT_DIR"]) / "approved"
    img = make_png(str(approved_dir), "svc_undo.png")
    result = svc.undo_action(["svc_undo.png"], from_status="approved")
    assert result["moved"] == 1
    assert (Path(_temp_dirs["OUTPUT_DIR"]) / "svc_undo.png").exists()


def test_stats_structure(svc, _temp_dirs):
    make_png(_temp_dirs["OUTPUT_DIR"], "stats_test.png")
    stats = svc.get_stats()
    assert "daily" in stats
    assert "totals" in stats
    assert "approved" in stats["totals"]
    assert "pending" in stats["totals"]


def test_save_and_load_note(svc):
    svc.save_note("2026-03-24", "Test note content")
    notes = svc.load_notes()
    assert notes.get("2026-03-24") == "Test note content"


def test_build_zip(svc, _temp_dirs):
    approved_dir = Path(_temp_dirs["OUTPUT_DIR"]) / "approved"
    img = make_png(str(approved_dir), "zip_source.png")
    data = svc.build_zip(filenames=["zip_source.png"])
    assert isinstance(data, bytes)
    assert data[:2] == b"PK"  # ZIP magic bytes


def test_build_zip_by_date(svc, _temp_dirs):
    """Put an image in approved, then download by date."""
    img = make_png(_temp_dirs["OUTPUT_DIR"], "date_zip.png")
    svc.approve_images(["date_zip.png"])
    # Use today's date from the mtime of the approved file
    from datetime import datetime
    approved_dir = Path(_temp_dirs["OUTPUT_DIR"]) / "approved"
    mtime = (approved_dir / "date_zip.png").stat().st_mtime
    date_str = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")

    data = svc.build_zip(date=date_str)
    assert data[:2] == b"PK"


def test_build_zip_empty_raises(svc):
    with pytest.raises(ValueError):
        svc.build_zip(filenames=[])

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


def test_extract_metadata_names_the_workflow_and_its_note(
    svc, _temp_dirs, tmp_path, monkeypatch,
):
    from backend.config import GlobalConfig
    from backend.services import workflow_registry

    make_png(_temp_dirs["OUTPUT_DIR"], "svc_wf.png")
    monkeypatch.setattr(GlobalConfig, "PROMPTS_DIR", str(tmp_path), raising=False)
    workflow_registry.save_entry(
        "zib.json", {"kinds": [], "note": "Best for close-up portraits."},
    )
    monkeypatch.setattr(
        svc.storage, "get_execution_by_result_path",
        lambda path: {"execution_id": "e1", "workflow_name": "zib.json",
                      "prompt": "p", "persona": "EMI"},
    )

    meta = svc.extract_metadata("svc_wf.png", status="pending")

    assert meta["workflow"] == "zib.json"
    assert meta["workflow_note"] == "Best for close-up portraits."


def test_extract_metadata_falls_back_to_the_dispatching_request(
    svc, _temp_dirs, monkeypatch,
):
    """Images predating image_logs.workflow_name still name their workflow."""
    from backend.database import generation_requests_storage as grs

    make_png(_temp_dirs["OUTPUT_DIR"], "svc_wf_old.png")
    monkeypatch.setattr(
        svc.storage, "get_execution_by_result_path",
        lambda path: {"execution_id": "e-old", "workflow_name": None,
                      "prompt": "p", "persona": None},
    )

    class FakeRequests:
        def get_by_execution_id(self, execution_id):
            assert execution_id == "e-old"
            return {"workflow_name": "legacy.json"}

    monkeypatch.setattr(grs, "GenerationRequestsStorage", FakeRequests)

    meta = svc.extract_metadata("svc_wf_old.png", status="pending")

    assert meta["workflow"] == "legacy.json"


def test_extract_metadata_without_a_known_workflow(svc, _temp_dirs, monkeypatch):
    make_png(_temp_dirs["OUTPUT_DIR"], "svc_wf_none.png")
    monkeypatch.setattr(
        svc.storage, "get_execution_by_result_path", lambda path: None,
    )

    meta = svc.extract_metadata("svc_wf_none.png", status="pending")

    assert meta["workflow"] is None
    assert meta["workflow_note"] == ""


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

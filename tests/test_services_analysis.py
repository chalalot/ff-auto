import pytest

from tests.conftest import make_png


@pytest.fixture
def svc(_temp_dirs, tmp_path):
    from backend.services.gallery import GalleryService
    from backend.database.evaluations_storage import EvaluationsStorage
    from backend.services.analysis import AnalysisService

    gallery = GalleryService()
    # _temp_dirs is session-scoped, so wipe the three folders for a clean
    # universe in each test (exact-count assertions depend on it).
    for d in (gallery.output_dir, gallery.approved_dir, gallery.disapproved_dir):
        for entry in d.iterdir():
            if entry.is_file():
                entry.unlink()
    storage = EvaluationsStorage(db_path=str(tmp_path / "evals.db"))
    return AnalysisService(gallery_service=gallery, evaluations_storage=storage), gallery, storage


def _complete(storage, media_path, overall):
    eid = storage.create_pending(
        media_type="image", media_path=media_path,
        prompt=None, model="m", rubric_version="production-v1",
    )
    storage.update_completed(
        evaluation_id=eid,
        scores=[{"dimension": "artifact_free", "score": int(overall), "rationale": "r"}],
        overall_score=overall, summary="ok", raw_response={"ok": True},
    )


def test_summary_counts_and_rates(svc, _temp_dirs):
    service, gallery, storage = svc
    make_png(_temp_dirs["OUTPUT_DIR"], "a_pending.png")
    make_png(str(gallery.approved_dir), "b_approved.png")
    make_png(str(gallery.disapproved_dir), "c_disapproved.png")
    # Evaluate only the approved one.
    _complete(storage, str(gallery.approved_dir / "b_approved.png"), 4.0)

    resp = service.get_analysis(status="all", evaluated="all", per_page=50)
    s = resp.summary
    assert s.total == 3
    assert s.approval.approved == 1
    assert s.approval.disapproved == 1
    assert s.approval.pending == 1
    assert s.approval.approved_rate == pytest.approx(1 / 3, abs=1e-3)
    assert s.evaluation.evaluated == 1
    assert s.evaluation.not_evaluated == 2
    assert s.avg_overall_score == 4.0


def test_status_filter_restricts_universe(svc, _temp_dirs):
    service, gallery, storage = svc
    make_png(_temp_dirs["OUTPUT_DIR"], "p1.png")
    make_png(str(gallery.approved_dir), "ap1.png")

    resp = service.get_analysis(status="approved", per_page=50)
    assert resp.summary.total == 1
    assert all(r.status == "approved" for r in resp.items)


def test_evaluated_filter_no(svc, _temp_dirs):
    service, gallery, storage = svc
    make_png(_temp_dirs["OUTPUT_DIR"], "ev.png")
    make_png(_temp_dirs["OUTPUT_DIR"], "noev.png")
    _complete(storage, str(gallery.output_dir / "ev.png"), 5.0)

    resp = service.get_analysis(evaluated="no", per_page=50)
    names = {r.filename for r in resp.items}
    assert "noev.png" in names
    assert "ev.png" not in names
    assert all(r.eval_status == "not_evaluated" for r in resp.items)


def test_row_carries_scores_and_metadata(svc, _temp_dirs):
    service, gallery, storage = svc
    make_png(str(gallery.approved_dir), "scored.png")
    _complete(storage, str(gallery.approved_dir / "scored.png"), 4.0)

    resp = service.get_analysis(status="approved", evaluated="yes", per_page=50)
    row = next(r for r in resp.items if r.filename == "scored.png")
    assert row.eval_status == "completed"
    assert row.overall_score == 4.0
    assert row.scores[0].dimension == "artifact_free"


def test_empty_universe(svc):
    service, _, _ = svc
    resp = service.get_analysis()
    assert resp.summary.total == 0
    assert resp.summary.avg_overall_score is None
    assert resp.items == []
    assert resp.pages == 1

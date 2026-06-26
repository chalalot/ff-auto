import pytest

from backend.database.evaluations_storage import EvaluationsStorage


@pytest.fixture
def storage(tmp_path):
    return EvaluationsStorage(db_path=str(tmp_path / "evals.db"))


def _complete(storage, media_path, overall, dims):
    eid = storage.create_pending(
        media_type="image", media_path=media_path,
        prompt=None, model="m", rubric_version="production-v1",
    )
    storage.update_completed(
        evaluation_id=eid,
        scores=[{"dimension": d, "score": s, "rationale": "r"} for d, s in dims],
        overall_score=overall, summary="ok", raw_response={"ok": True},
    )
    return eid


def test_get_latest_for_paths_returns_latest_row(storage):
    _complete(storage, "/img/a.png", 3.0, [("artifact_free", 3)])
    _complete(storage, "/img/a.png", 5.0, [("artifact_free", 5)])  # newer
    out = storage.get_latest_for_paths(["/img/a.png", "/img/missing.png"])
    assert set(out.keys()) == {"/img/a.png"}
    assert out["/img/a.png"]["overall_score"] == 5.0
    assert out["/img/a.png"]["scores"][0]["score"] == 5


def test_get_latest_for_paths_empty(storage):
    assert storage.get_latest_for_paths([]) == {}


def test_get_score_summary_counts_and_average(storage):
    _complete(storage, "/img/a.png", 4.0, [("artifact_free", 4)])
    _complete(storage, "/img/b.png", 2.0, [("artifact_free", 2)])
    eid = storage.create_pending(
        media_type="image", media_path="/img/c.png",
        prompt=None, model="m", rubric_version="production-v1",
    )
    storage.update_failed(evaluation_id=eid, error_message="boom", raw_response=None)
    summary = storage.get_score_summary()
    assert summary["evaluated"] == 2
    assert summary["failed"] == 1
    assert summary["avg_overall_score"] == 3.0
    assert summary["evaluated_paths"] == {"/img/a.png", "/img/b.png"}

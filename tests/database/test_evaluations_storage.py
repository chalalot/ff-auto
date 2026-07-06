"""
Task 3 tests: EvaluationsStorage ported to SQLAlchemy/Postgres.

Public method signatures and return shapes must match the legacy sqlite
implementation exactly (same dict keys, same status strings, timestamps as
'YYYY-MM-DD HH:MM:SS' strings).
"""
import pytest

from backend.database.evaluations_storage import EvaluationsStorage

LEGACY_KEYS = {
    "id",
    "media_type",
    "media_path",
    "prompt",
    "model",
    "rubric_version",
    "status",
    "overall_score",
    "summary",
    "error_message",
    "raw_response",
    "created_at",
    "completed_at",
    "scores",  # decoded from scores_json, which is popped
}


@pytest.fixture
def storage(clean_tables):
    return EvaluationsStorage()


def _create(storage, media_path="/results/a.png", media_type="image"):
    return storage.create_pending(
        media_type=media_type,
        media_path=media_path,
        prompt="a prompt",
        model="gemini",
        rubric_version="production-v1",
    )


def test_create_pending_returns_int_id(storage):
    eid = _create(storage)
    assert isinstance(eid, int)
    row = storage.get_evaluation(eid)
    assert row is not None
    assert row["status"] == "pending"
    assert row["scores"] == []
    assert row["overall_score"] is None


def test_row_keys_match_legacy(storage):
    eid = _create(storage)
    row = storage.get_evaluation(eid)
    assert set(row.keys()) == LEGACY_KEYS
    assert "scores_json" not in row


def test_created_at_is_legacy_string_format(storage):
    import re

    eid = _create(storage)
    row = storage.get_evaluation(eid)
    assert isinstance(row["created_at"], str)
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", row["created_at"])
    assert row["completed_at"] is None


def test_update_completed_roundtrip(storage):
    eid = _create(storage)
    scores = [{"dimension": "artifact_free", "score": 4, "rationale": "ok"}]
    storage.update_completed(
        evaluation_id=eid,
        scores=scores,
        overall_score=4.0,
        summary="looks fine",
        raw_response={"scores": scores},
    )
    row = storage.get_evaluation(eid)
    assert row["status"] == "completed"
    assert row["scores"] == scores
    assert row["overall_score"] == 4.0
    assert row["summary"] == "looks fine"
    assert row["error_message"] is None
    assert isinstance(row["completed_at"], str)


def test_update_failed_clears_scores(storage):
    eid = _create(storage)
    storage.update_completed(
        evaluation_id=eid,
        scores=[{"dimension": "d", "score": 5, "rationale": "r"}],
        overall_score=5.0,
        summary="s",
        raw_response="raw text",
    )
    storage.update_failed(eid, error_message="boom", raw_response=None)
    row = storage.get_evaluation(eid)
    assert row["status"] == "failed"
    assert row["scores"] == []
    assert row["overall_score"] is None
    assert row["summary"] is None
    assert row["error_message"] == "boom"


def test_get_evaluation_missing_returns_none(storage):
    assert storage.get_evaluation(999999) is None


def test_list_filters_match_legacy_semantics(storage):
    ids = [_create(storage, media_path=f"/results/{i}.png") for i in range(5)]
    _create(storage, media_path="/results/0.png")  # second eval for same path

    # Default: newest (highest id) first, capped by limit.
    rows = storage.list_evaluations(limit=3)
    assert [r["id"] for r in rows] == sorted(
        [r["id"] for r in rows], reverse=True
    )
    assert len(rows) == 3

    # media_path filter returns only that path, newest first.
    rows = storage.list_evaluations(media_path="/results/0.png")
    assert len(rows) == 2
    assert all(r["media_path"] == "/results/0.png" for r in rows)
    assert rows[0]["id"] > rows[1]["id"]

    # limit applies within the filtered set.
    rows = storage.list_evaluations(limit=1, media_path="/results/0.png")
    assert len(rows) == 1
    assert rows[0]["id"] == max(ids) + 1


def test_get_latest_for_paths_higher_id_wins(storage):
    e1 = _create(storage, media_path="/x/a.png")
    e2 = _create(storage, media_path="/x/a.png")
    _create(storage, media_path="/x/b.png")

    latest = storage.get_latest_for_paths(["/x/a.png", "/x/b.png", "/x/missing.png"])
    assert set(latest.keys()) == {"/x/a.png", "/x/b.png"}
    assert latest["/x/a.png"]["id"] == e2
    assert e1 != e2


def test_get_latest_for_paths_empty_input(storage):
    assert storage.get_latest_for_paths([]) == {}


def test_get_score_summary_counts_and_average(storage):
    # completed at 4.0
    e1 = _create(storage, media_path="/x/1.png")
    storage.update_completed(e1, [{"dimension": "d", "score": 4, "rationale": "r"}], 4.0, None, None)
    # completed at 5.0
    e2 = _create(storage, media_path="/x/2.png")
    storage.update_completed(e2, [{"dimension": "d", "score": 5, "rationale": "r"}], 5.0, None, None)
    # failed
    e3 = _create(storage, media_path="/x/3.png")
    storage.update_failed(e3, "err")
    # pending — not counted in either bucket
    _create(storage, media_path="/x/4.png")

    summary = storage.get_score_summary()
    assert summary["evaluated"] == 2
    assert summary["failed"] == 1
    assert summary["avg_overall_score"] == 4.5
    assert summary["evaluated_paths"] == {"/x/1.png", "/x/2.png"}
    assert summary["failed_paths"] == {"/x/3.png"}


def test_get_score_summary_latest_row_wins(storage):
    # First attempt failed, retry completed: path counts as evaluated only.
    e1 = _create(storage, media_path="/x/retry.png")
    storage.update_failed(e1, "err")
    e2 = _create(storage, media_path="/x/retry.png")
    storage.update_completed(e2, [{"dimension": "d", "score": 3, "rationale": "r"}], 3.0, None, None)

    summary = storage.get_score_summary()
    assert summary["evaluated_paths"] == {"/x/retry.png"}
    assert summary["failed_paths"] == set()


def test_constructor_still_accepts_db_path(clean_tables):
    """Transitional: legacy call sites pass db_path; it is accepted and ignored."""
    storage = EvaluationsStorage(db_path="ignored.db")
    eid = _create(storage)
    assert storage.get_evaluation(eid) is not None

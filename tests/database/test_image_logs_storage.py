"""
Task 3 tests: ImageLogsStorage ported to SQLAlchemy/Postgres.

Return shapes must match the legacy sqlite implementation: plain dicts with
the same keys, status strings 'pending'/'completed'/'failed', created_at as a
'YYYY-MM-DD HH:MM:SS' string (ExecutionRecord.created_at is typed str).
"""
import pytest

from backend.database.image_logs_storage import ImageLogsStorage

LEGACY_KEYS = {
    "id",
    "execution_id",
    "prompt",
    "persona",
    "image_ref_path",
    "result_image_path",
    "status",
    "created_at",
}


@pytest.fixture
def storage(clean_tables):
    return ImageLogsStorage()


def test_log_execution_returns_int_id_and_pending(storage):
    row_id = storage.log_execution(
        "exec-1", "a prompt", image_ref_path="/ref/a.png", persona="dancer"
    )
    assert isinstance(row_id, int)
    rows = storage.get_pending_executions()
    assert len(rows) == 1
    row = rows[0]
    assert set(row.keys()) == LEGACY_KEYS
    assert row["execution_id"] == "exec-1"
    assert row["status"] == "pending"
    assert row["result_image_path"] is None
    assert isinstance(row["created_at"], str)


def test_update_result_path_completes(storage):
    storage.log_execution("exec-2", "p")
    storage.update_result_path("exec-2", "/results/out.png")
    assert storage.get_pending_executions() == []
    row = storage.get_execution_by_result_path("/results/out.png")
    assert row["status"] == "completed"
    assert row["result_image_path"] == "/results/out.png"
    assert row["image_ref_path"] is None


def test_update_result_path_with_new_ref(storage):
    storage.log_execution("exec-3", "p", image_ref_path="/ref/old.png")
    storage.update_result_path("exec-3", "/results/o.png", new_ref_path="/ref/new.png")
    row = storage.get_execution_by_result_path("/results/o.png")
    assert row["image_ref_path"] == "/ref/new.png"


def test_mark_as_failed(storage):
    storage.log_execution("exec-4", "p")
    storage.mark_as_failed("exec-4")
    assert storage.get_pending_executions() == []
    rows = storage.get_recent_executions()
    assert rows[0]["status"] == "failed"


def test_log_failed_execution_synthetic_id(storage):
    row_id = storage.log_failed_execution(
        "/ref/x.png", "vision refusal", persona="dancer"
    )
    assert isinstance(row_id, int)
    rows = storage.get_recent_executions()
    row = rows[0]
    assert row["status"] == "failed"
    assert row["execution_id"].startswith("failed_")
    assert row["prompt"] == "vision refusal"  # error stored in prompt column
    assert row["image_ref_path"] == "/ref/x.png"


def test_get_execution_by_result_path_exact_and_multi(storage):
    # Exact single-path match.
    storage.log_execution("exec-5", "p")
    storage.update_result_path("exec-5", "/results/single.png")
    assert storage.get_execution_by_result_path("/results/single.png")["execution_id"] == "exec-5"

    # Comma-joined list membership.
    storage.log_execution("exec-6", "p")
    storage.update_result_path("exec-6", "/results/v1.png,/results/v2.png")
    assert storage.get_execution_by_result_path("/results/v2.png")["execution_id"] == "exec-6"

    # Basename match across different mount prefixes.
    assert (
        storage.get_execution_by_result_path("/other/mount/v1.png")["execution_id"]
        == "exec-6"
    )

    # Miss returns None.
    assert storage.get_execution_by_result_path("/results/nope.png") is None


def test_get_recent_executions_order_and_limit(storage):
    for i in range(5):
        storage.log_execution(f"exec-r{i}", f"p{i}")
    rows = storage.get_recent_executions(limit=3)
    assert len(rows) == 3
    ids = [r["id"] for r in rows]
    assert ids == sorted(ids, reverse=True)
    assert rows[0]["execution_id"] == "exec-r4"


def test_get_ref_path_use_counts(storage):
    storage.log_execution("e1", "p", image_ref_path="/ref/a.png")
    storage.log_execution("e2", "p", image_ref_path="/ref/a.png")
    storage.log_execution("e3", "p", image_ref_path="/ref/b.png")
    storage.log_execution("e4", "p")  # NULL ref not counted
    counts = storage.get_ref_path_use_counts()
    assert counts == {"/ref/a.png": 2, "/ref/b.png": 1}


def test_get_all_completed_executions(storage):
    storage.log_execution("e1", "p")
    storage.update_result_path("e1", "/results/a.png")
    storage.log_execution("e2", "p")  # still pending, no result path
    rows = storage.get_all_completed_executions()
    assert len(rows) == 1
    assert rows[0]["execution_id"] == "e1"


def test_constructor_still_accepts_db_path(clean_tables):
    storage = ImageLogsStorage(db_path="ignored.db")
    assert storage.log_execution("e-compat", "p") >= 1

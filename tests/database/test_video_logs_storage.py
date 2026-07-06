"""
Task 4 tests: VideoLogsStorage ported to SQLAlchemy/Postgres.

Legacy semantics preserved: batch_id/filename_id round-trip, status defaults
'pending', dict rows with legacy keys, created_at as 'YYYY-MM-DD HH:MM:SS'.
"""
import pytest

from backend.database.video_logs_storage import VideoLogsStorage

LEGACY_KEYS = {
    "id",
    "batch_id",
    "execution_id",
    "prompt",
    "source_image_path",
    "video_output_path",
    "status",
    "created_at",
    "filename_id",
}


@pytest.fixture
def storage(clean_tables):
    return VideoLogsStorage()


def test_log_execution_returns_int_id_and_defaults_pending(storage):
    row_id = storage.log_execution(
        "task-1",
        "a video prompt",
        source_image_path="/img/src.png",
        batch_id="batch-A",
        filename_id="file-01",
    )
    assert isinstance(row_id, int)
    row = storage.get_execution("task-1")
    assert set(row.keys()) == LEGACY_KEYS
    assert row["status"] == "pending"
    assert row["batch_id"] == "batch-A"
    assert row["filename_id"] == "file-01"
    assert row["video_output_path"] is None
    assert isinstance(row["created_at"], str)


def test_get_execution_missing_returns_none(storage):
    assert storage.get_execution("nope") is None


def test_update_result_with_path(storage):
    storage.log_execution("task-2", "p")
    storage.update_result("task-2", video_output_path="/videos/out.mp4")
    row = storage.get_execution("task-2")
    assert row["status"] == "completed"
    assert row["video_output_path"] == "/videos/out.mp4"


def test_update_result_status_only_keeps_path_null(storage):
    storage.log_execution("task-3", "p")
    storage.update_result("task-3", status="failed")
    row = storage.get_execution("task-3")
    assert row["status"] == "failed"
    assert row["video_output_path"] is None


def test_get_recent_executions_order_and_limit(storage):
    for i in range(5):
        storage.log_execution(f"task-r{i}", f"p{i}")
    rows = storage.get_recent_executions(limit=3)
    assert len(rows) == 3
    ids = [r["id"] for r in rows]
    assert ids == sorted(ids, reverse=True)
    assert rows[0]["execution_id"] == "task-r4"


def test_get_incomplete_batches_semantics(storage):
    # batch-open: one pending, one completed -> incomplete.
    storage.log_execution("t1", "p", batch_id="batch-open")
    storage.log_execution("t2", "p", batch_id="batch-open")
    storage.update_result("t2", video_output_path="/v/2.mp4")
    # batch-done: everything terminal -> not returned.
    storage.log_execution("t3", "p", batch_id="batch-done")
    storage.update_result("t3", status="failed")
    # NULL batch_id pending row -> never returned.
    storage.log_execution("t4", "p")

    batches = storage.get_incomplete_batches()
    assert len(batches) == 1
    batch = batches[0]
    assert set(batch.keys()) == {"batch_id", "created_at", "count"}
    assert batch["batch_id"] == "batch-open"
    assert batch["count"] == 1  # only the still-pending row counts


def test_get_batch_executions_ascending(storage):
    storage.log_execution("b1", "p", batch_id="batch-B")
    storage.log_execution("b2", "p", batch_id="batch-B")
    storage.log_execution("x1", "p", batch_id="other")
    rows = storage.get_batch_executions("batch-B")
    assert [r["execution_id"] for r in rows] == ["b1", "b2"]
    assert all(r["batch_id"] == "batch-B" for r in rows)


def test_constructor_still_accepts_positional_db_path(clean_tables):
    """VideoService passes VideoLogsStorage(str(dir / 'video_logs.db'))."""
    storage = VideoLogsStorage("/tmp/does-not-matter/video_logs.db")
    assert storage.log_execution("compat", "p") >= 1

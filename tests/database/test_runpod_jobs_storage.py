"""
Task 4 tests: RunpodJobsStorage ported to SQLAlchemy/Postgres.

job_id uniqueness is DB-enforced; insert is upsert-style (conflict on job_id
is a no-op so callers never crash on a duplicate submit). job_input/output
round-trip as dicts, exactly like the legacy JSON-decode behavior.
"""
import pytest

from backend.database.runpod_jobs_storage import RunpodJobsStorage

LEGACY_KEYS = {
    "id",
    "job_id",
    "endpoint_id",
    "lora_name",
    "submitted_at",
    "job_input",
    "status",
    "output",
    "updated_at",
}


@pytest.fixture
def storage(clean_tables):
    return RunpodJobsStorage()


def _insert(storage, job_id="job-1", lora="my-lora"):
    storage.insert(
        job_id=job_id,
        endpoint_id="ep-1",
        lora_name=lora,
        submitted_at="2026-07-06T00:00:00",
        job_input={"lora_name": lora, "steps": 1000},
    )


def test_insert_and_get_job_roundtrip(storage):
    _insert(storage)
    job = storage.get_job("job-1")
    assert set(job.keys()) == LEGACY_KEYS
    assert job["job_id"] == "job-1"
    assert job["job_input"] == {"lora_name": "my-lora", "steps": 1000}  # dict, not str
    assert job["status"] is None
    assert job["output"] is None
    assert job["updated_at"] is None


def test_get_job_missing_returns_none(storage):
    assert storage.get_job("missing") is None


def test_insert_duplicate_job_id_is_noop(storage):
    _insert(storage, lora="first")
    _insert(storage, lora="second")  # duplicate job_id: must not raise
    job = storage.get_job("job-1")
    assert job["lora_name"] == "first"  # original row kept
    assert len(storage.list_jobs()) == 1


def test_update_status_sets_status_and_updated_at(storage):
    _insert(storage)
    storage.update_status("job-1", "IN_PROGRESS")
    job = storage.get_job("job-1")
    assert job["status"] == "IN_PROGRESS"
    assert job["updated_at"] is not None
    assert job["output"] is None


def test_update_status_coalesce_keeps_existing_output(storage):
    _insert(storage)
    storage.update_status("job-1", "COMPLETED", output={"weights_url": "s3://x"})
    # A later status poll without output must NOT wipe the stored output.
    storage.update_status("job-1", "COMPLETED")
    job = storage.get_job("job-1")
    assert job["output"] == {"weights_url": "s3://x"}


def test_delete_job(storage):
    _insert(storage)
    storage.delete_job("job-1")
    assert storage.get_job("job-1") is None
    storage.delete_job("job-1")  # deleting a missing job is a no-op


def test_list_jobs_order_and_limit(storage):
    for i in range(5):
        _insert(storage, job_id=f"job-l{i}")
    jobs = storage.list_jobs(limit=3)
    assert len(jobs) == 3
    assert [j["job_id"] for j in jobs] == ["job-l4", "job-l3", "job-l2"]
    assert all(isinstance(j["job_input"], dict) for j in jobs)


def test_constructor_takes_no_legacy_args(clean_tables):
    with pytest.raises(TypeError):
        RunpodJobsStorage(db_path="legacy.db")
    storage = RunpodJobsStorage()
    _insert(storage, job_id="no-args")
    assert storage.get_job("no-args") is not None

"""
Phase 2: generation_requests review queue — migration + storage tests.

State machine: pending_review -> approved -> dispatched -> completed|failed,
plus discarded (from pending_review/failed) and failed -> approved (retry).
"""
import pytest
from sqlalchemy import inspect


def test_migration_creates_generation_requests(migrated_engine):
    inspector = inspect(migrated_engine)
    assert "generation_requests" in inspector.get_table_names()
    cols = {c["name"] for c in inspector.get_columns("generation_requests")}
    assert {
        "id", "batch_id", "source_image_path", "original_prompt", "prompt",
        "provider", "workflow_name", "settings", "status", "execution_id",
        "result_path", "error", "created_at", "updated_at",
    } <= cols
    index_names = {ix["name"] for ix in inspector.get_indexes("generation_requests")}
    assert "idx_generation_requests_status" in index_names
    assert "idx_generation_requests_batch_id" in index_names
    assert "idx_generation_requests_execution_id" in index_names


from backend.database.generation_requests_storage import (
    GenerationRequestsStorage,
    InvalidStateError,
)


@pytest.fixture
def storage(clean_tables):
    return GenerationRequestsStorage()


def _item(prompt="a prompt", provider="comfy_image", **overrides):
    item = {
        "source_image_path": "/app/processed/img.png",
        "prompt": prompt,
        "provider": provider,
        "workflow_name": "wf.json",
        "settings": {"persona": "p1", "width": 1024},
    }
    item.update(overrides)
    return item


def _create_one(storage, **overrides):
    result = storage.create_requests([_item(**overrides)])
    return result["request_ids"][0]


# ---- create / get ----

def test_create_and_get_roundtrip(storage):
    result = storage.create_requests([_item(), _item(prompt="second")])
    assert len(result["request_ids"]) == 2
    row = storage.get_request(result["request_ids"][0])
    assert row["status"] == "pending_review"
    assert row["prompt"] == "a prompt"
    assert row["original_prompt"] == "a prompt"      # immutable copy
    assert row["settings"] == {"persona": "p1", "width": 1024}  # dict, not str
    assert row["batch_id"] == result["batch_id"]
    assert row["execution_id"] is None


def test_create_uses_given_batch_id(storage):
    result = storage.create_requests([_item()], batch_id="batch-x")
    assert result["batch_id"] == "batch-x"


def test_get_missing_returns_none(storage):
    assert storage.get_request("nope") is None


# ---- list ----

def test_list_filters_and_pagination(storage):
    storage.create_requests([_item() for _ in range(3)], batch_id="b1")
    storage.create_requests([_item()], batch_id="b2")
    assert storage.list_requests(batch_id="b1")["total"] == 3
    assert storage.list_requests(status="pending_review")["total"] == 4
    assert storage.list_requests(status="completed")["total"] == 0
    page = storage.list_requests(page=1, per_page=3)
    assert len(page["items"]) == 3
    assert page["pages"] == 2


# ---- edit ----

def test_update_prompt_while_pending(storage):
    rid = _create_one(storage)
    row = storage.update_request(rid, prompt="edited")
    assert row["prompt"] == "edited"
    assert row["original_prompt"] == "a prompt"      # untouched


def test_update_settings_while_pending(storage):
    rid = _create_one(storage)
    row = storage.update_request(rid, settings={"width": 512})
    assert row["settings"] == {"width": 512}


def test_update_after_claim_raises(storage):
    rid = _create_one(storage)
    storage.claim_for_dispatch([rid])
    with pytest.raises(InvalidStateError):
        storage.update_request(rid, prompt="too late")


def test_update_missing_returns_none(storage):
    assert storage.update_request("nope", prompt="x") is None


# ---- discard ----

def test_discard_pending(storage):
    rid = _create_one(storage)
    assert storage.discard_request(rid)["status"] == "discarded"


def test_discard_dispatched_raises(storage):
    rid = _create_one(storage)
    storage.claim_for_dispatch([rid])
    storage.begin_dispatch(rid)
    with pytest.raises(InvalidStateError):
        storage.discard_request(rid)


# ---- dispatch state machine ----

def test_claim_only_pending_or_failed(storage):
    rid1 = _create_one(storage)
    rid2 = _create_one(storage)
    storage.discard_request(rid2)
    claimed = storage.claim_for_dispatch([rid1, rid2, "missing"])
    assert claimed == [rid1]
    assert storage.get_request(rid1)["status"] == "approved"


def test_claim_twice_is_idempotent(storage):
    rid = _create_one(storage)
    assert storage.claim_for_dispatch([rid]) == [rid]
    assert storage.claim_for_dispatch([rid]) == []   # double-click / two members


def test_begin_dispatch_transitions_once(storage):
    rid = _create_one(storage)
    storage.claim_for_dispatch([rid])
    row = storage.begin_dispatch(rid)
    assert row["status"] == "dispatched"
    assert storage.begin_dispatch(rid) is None       # celery redelivery no-ops


def test_begin_dispatch_requires_approved(storage):
    rid = _create_one(storage)
    assert storage.begin_dispatch(rid) is None       # still pending_review


def test_execution_and_completion(storage):
    rid = _create_one(storage)
    storage.claim_for_dispatch([rid])
    storage.begin_dispatch(rid)
    storage.set_execution(rid, "exec-1")
    assert storage.get_request(rid)["execution_id"] == "exec-1"
    assert storage.mark_completed_by_execution("exec-1", "/app/results/v.mp4") is True
    row = storage.get_request(rid)
    assert row["status"] == "completed"
    assert row["result_path"] == "/app/results/v.mp4"


def test_mark_completed_unknown_execution_is_noop(storage):
    assert storage.mark_completed_by_execution("ghost") is False


def test_failed_then_retry(storage):
    rid = _create_one(storage)
    storage.claim_for_dispatch([rid])
    storage.begin_dispatch(rid)
    storage.mark_failed(rid, "provider exploded")
    row = storage.get_request(rid)
    assert row["status"] == "failed"
    assert row["error"] == "provider exploded"
    assert storage.claim_for_dispatch([rid]) == [rid]  # retry path
    assert storage.get_request(rid)["error"] is None   # cleared on retry


def test_mark_failed_by_execution(storage):
    rid = _create_one(storage)
    storage.claim_for_dispatch([rid])
    storage.begin_dispatch(rid)
    storage.set_execution(rid, "exec-f")
    assert storage.mark_failed_by_execution("exec-f", "comfy error") is True
    assert storage.get_request(rid)["status"] == "failed"


def test_constructor_takes_no_args(clean_tables):
    with pytest.raises(TypeError):
        GenerationRequestsStorage(db_path="legacy.db")

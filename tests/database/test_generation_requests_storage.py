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

"""Schema assertions for migration 0003 (projects & members)."""
from sqlalchemy import inspect

SCOPED_TABLES = [
    "generation_requests", "image_logs", "video_logs", "evaluations",
    "runs", "posts", "caption_exports",
]


def test_new_tables_exist(migrated_engine):
    names = set(inspect(migrated_engine).get_table_names())
    assert {"members", "projects", "project_members", "uploads"} <= names


def test_scoping_columns_added(migrated_engine):
    insp = inspect(migrated_engine)
    for table in SCOPED_TABLES:
        cols = {c["name"]: c for c in insp.get_columns(table)}
        assert "project_id" in cols, table
        assert "created_by_member_id" in cols, table
        assert cols["project_id"]["nullable"] is True, table
        assert cols["created_by_member_id"]["nullable"] is True, table


def test_runpod_jobs_stays_global(migrated_engine):
    cols = {c["name"] for c in inspect(migrated_engine).get_columns("runpod_jobs")}
    assert "project_id" not in cols


def test_members_name_unique(migrated_engine):
    insp = inspect(migrated_engine)
    uniques = insp.get_unique_constraints("members") + [
        i for i in insp.get_indexes("members") if i.get("unique")
    ]
    assert any("name" in (u.get("column_names") or []) for u in uniques)

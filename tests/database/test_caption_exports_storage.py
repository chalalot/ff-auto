"""
Task 5 tests: CaptionExportsStorage ported to SQLAlchemy/Postgres.
"""
import pytest

from backend.database.caption_exports_storage import CaptionExportsStorage

LEGACY_KEYS = {
    "id",
    "file_id",
    "filename",
    "public_url",
    "image_count",
    "exported_at",
}


@pytest.fixture
def storage(clean_tables):
    return CaptionExportsStorage()


def test_insert_returns_int_id(storage):
    row_id = storage.insert(
        file_id="drive-1",
        filename="captions_1.zip",
        public_url="https://drive/x1",
        image_count=7,
    )
    assert isinstance(row_id, int)


def test_list_exports_shape_and_content(storage):
    storage.insert(
        file_id="drive-1",
        filename="captions_1.zip",
        public_url="https://drive/x1",
        image_count=7,
    )
    rows = storage.list_exports()
    assert len(rows) == 1
    row = rows[0]
    assert set(row.keys()) == LEGACY_KEYS
    assert row["file_id"] == "drive-1"
    assert row["image_count"] == 7
    assert isinstance(row["exported_at"], str) and row["exported_at"]


def test_list_exports_order_and_limit(storage):
    for i in range(5):
        storage.insert(
            file_id=f"drive-{i}",
            filename=f"c{i}.zip",
            public_url=f"https://drive/{i}",
            image_count=i,
        )
    rows = storage.list_exports(limit=3)
    assert len(rows) == 3
    assert [r["file_id"] for r in rows] == ["drive-4", "drive-3", "drive-2"]


def test_constructor_still_accepts_db_path(clean_tables):
    storage = CaptionExportsStorage(db_path="ignored.db")
    assert storage.insert("f", "n.zip", "https://u", 0) >= 1

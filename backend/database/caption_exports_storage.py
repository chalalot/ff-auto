import sqlite3
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

DB_PATH = "image_logs.db"


class CaptionExportsStorage:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _conn(self):
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        conn = self._conn()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS caption_exports (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_id      TEXT NOT NULL,
                    filename     TEXT NOT NULL,
                    public_url   TEXT NOT NULL,
                    image_count  INTEGER NOT NULL DEFAULT 0,
                    exported_at  TEXT NOT NULL
                )
            """)
            conn.commit()
        finally:
            conn.close()

    def insert(
        self,
        file_id: str,
        filename: str,
        public_url: str,
        image_count: int,
    ) -> int:
        conn = self._conn()
        try:
            cur = conn.execute(
                """
                INSERT INTO caption_exports (file_id, filename, public_url, image_count, exported_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (file_id, filename, public_url, image_count, datetime.utcnow().isoformat()),
            )
            conn.commit()
            return cur.lastrowid
        except Exception as e:
            logger.error(f"[caption_exports] insert failed: {e}")
            raise
        finally:
            conn.close()

    def list_exports(self, limit: int = 50) -> list[dict]:
        conn = self._conn()
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                "SELECT * FROM caption_exports ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

import json
import sqlite3
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

DB_PATH = "image_logs.db"  # reuse the same SQLite file


class RunpodJobsStorage:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _conn(self):
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        conn = self._conn()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS runpod_jobs (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id      TEXT NOT NULL UNIQUE,
                    endpoint_id TEXT NOT NULL,
                    lora_name   TEXT NOT NULL,
                    submitted_at TEXT NOT NULL,
                    job_input   TEXT NOT NULL,
                    status      TEXT,
                    output      TEXT,
                    updated_at  TEXT
                )
            """)
            conn.commit()
        finally:
            conn.close()

    def insert(
        self,
        job_id: str,
        endpoint_id: str,
        lora_name: str,
        submitted_at: str,
        job_input: dict,
    ) -> None:
        conn = self._conn()
        try:
            conn.execute(
                """
                INSERT INTO runpod_jobs
                    (job_id, endpoint_id, lora_name, submitted_at, job_input, status, output, updated_at)
                VALUES (?, ?, ?, ?, ?, NULL, NULL, NULL)
                """,
                (job_id, endpoint_id, lora_name, submitted_at, json.dumps(job_input)),
            )
            conn.commit()
        except Exception as e:
            logger.error(f"[runpod_jobs] insert failed: {e}")
            raise
        finally:
            conn.close()

    def update_status(
        self,
        job_id: str,
        status: str,
        output: Optional[dict] = None,
    ) -> None:
        conn = self._conn()
        try:
            conn.execute(
                """
                UPDATE runpod_jobs
                SET status = ?, output = ?, updated_at = ?
                WHERE job_id = ?
                """,
                (status, json.dumps(output) if output is not None else None, datetime.utcnow().isoformat(), job_id),
            )
            conn.commit()
        except Exception as e:
            logger.error(f"[runpod_jobs] update_status failed: {e}")
            raise
        finally:
            conn.close()

    def list_jobs(self, limit: int = 100) -> list[dict]:
        conn = self._conn()
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                "SELECT * FROM runpod_jobs ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
            result = []
            for row in rows:
                d = dict(row)
                d["job_input"] = json.loads(d["job_input"]) if d["job_input"] else {}
                d["output"] = json.loads(d["output"]) if d["output"] else None
                result.append(d)
            return result
        finally:
            conn.close()

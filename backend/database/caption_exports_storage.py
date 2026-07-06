import logging
from datetime import datetime

from sqlalchemy import select

from .engine import session_scope
from .models import CaptionExport

logger = logging.getLogger(__name__)


def _row_dict(row: CaptionExport) -> dict:
    return {
        "id": row.id,
        "file_id": row.file_id,
        "filename": row.filename,
        "public_url": row.public_url,
        "image_count": row.image_count,
        "exported_at": row.exported_at,
    }


class CaptionExportsStorage:
    def __init__(self):
        # Schema is owned by Alembic; nothing to initialize here.
        pass

    def insert(
        self,
        file_id: str,
        filename: str,
        public_url: str,
        image_count: int,
    ) -> int:
        try:
            with session_scope() as session:
                row = CaptionExport(
                    file_id=file_id,
                    filename=filename,
                    public_url=public_url,
                    image_count=image_count,
                    exported_at=datetime.utcnow().isoformat(),
                )
                session.add(row)
                session.flush()
                return row.id
        except Exception as e:
            logger.error(f"[caption_exports] insert failed: {e}")
            raise

    def list_exports(self, limit: int = 50) -> list[dict]:
        with session_scope() as session:
            rows = session.execute(
                select(CaptionExport).order_by(CaptionExport.id.desc()).limit(limit)
            ).scalars().all()
            return [_row_dict(row) for row in rows]

"""make generation_requests.source_image_path nullable (brief-only headless)

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-09

Enables brief-only generation (no reference image) to be queued through the
review queue. See spec 2026-07-09-skill-driven-prompt-agent (S13 / A15).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0004'
down_revision: Union[str, None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        'generation_requests', 'source_image_path',
        existing_type=sa.Text(), nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        'generation_requests', 'source_image_path',
        existing_type=sa.Text(), nullable=False,
    )

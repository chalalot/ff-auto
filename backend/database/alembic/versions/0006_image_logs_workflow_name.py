"""record which workflow file produced each image

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-31

The gallery shows a result's persona, seed and prompt but had no way to say
which workflow graph made it. Queue-dispatched images could be traced through
generation_requests.workflow_name, but direct runs (upscaler, multiangle) never
pass through that table — so the name is recorded on the image row itself.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0006'
down_revision: Union[str, None] = '0005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('image_logs', sa.Column('workflow_name', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('image_logs', 'workflow_name')

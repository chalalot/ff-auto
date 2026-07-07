"""generation_requests review queue

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0002'
down_revision: Union[str, None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'generation_requests',
        sa.Column('id', sa.Text(), nullable=False),
        sa.Column('batch_id', sa.Text(), nullable=False),
        sa.Column('source_image_path', sa.Text(), nullable=False),
        sa.Column('original_prompt', sa.Text(), nullable=False),
        sa.Column('prompt', sa.Text(), nullable=False),
        sa.Column('provider', sa.Text(), nullable=False),
        sa.Column('workflow_name', sa.Text(), nullable=True),
        sa.Column('settings', postgresql.JSONB(astext_type=sa.Text()),
                  server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('status', sa.Text(), server_default='pending_review', nullable=False),
        sa.Column('execution_id', sa.Text(), nullable=True),
        sa.Column('result_path', sa.Text(), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True),
                  server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True),
                  server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_generation_requests_status', 'generation_requests', ['status'])
    op.create_index('idx_generation_requests_batch_id', 'generation_requests', ['batch_id'])
    op.create_index('idx_generation_requests_execution_id', 'generation_requests', ['execution_id'])


def downgrade() -> None:
    op.drop_table('generation_requests')

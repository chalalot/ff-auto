"""projects, members, uploads, scoping columns

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-08

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '0003'
down_revision: Union[str, None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCOPED_TABLES = (
    'generation_requests', 'image_logs', 'video_logs', 'evaluations',
    'runs', 'posts', 'caption_exports',
)


def upgrade() -> None:
    op.create_table(
        'members',
        sa.Column('id', sa.Text(), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True),
                  server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name', name='uq_members_name'),
    )
    op.create_table(
        'projects',
        sa.Column('id', sa.Text(), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('owner_member_id', sa.Text(), nullable=True),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True),
                  server_default=sa.text('now()'), nullable=True),
        sa.Column('archived_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['owner_member_id'], ['members.id'],
                                ondelete='SET NULL'),
    )
    op.create_table(
        'project_members',
        sa.Column('project_id', sa.Text(), nullable=False),
        sa.Column('member_id', sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint('project_id', 'member_id'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['member_id'], ['members.id'], ondelete='CASCADE'),
    )
    op.create_table(
        'uploads',
        sa.Column('id', sa.Text(), nullable=False),
        sa.Column('filename', sa.Text(), nullable=False),
        sa.Column('path', sa.Text(), nullable=False),
        sa.Column('kind', sa.Text(), nullable=False),
        sa.Column('project_id', sa.Text(), nullable=True),
        sa.Column('created_by_member_id', sa.Text(), nullable=True),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True),
                  server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['created_by_member_id'], ['members.id'],
                                ondelete='SET NULL'),
    )
    op.create_index('idx_uploads_project_id', 'uploads', ['project_id'])

    for table in SCOPED_TABLES:
        op.add_column(table, sa.Column('project_id', sa.Text(), nullable=True))
        op.add_column(table, sa.Column('created_by_member_id', sa.Text(), nullable=True))
        op.create_foreign_key(
            f'fk_{table}_project_id', table, 'projects',
            ['project_id'], ['id'], ondelete='SET NULL')
        op.create_foreign_key(
            f'fk_{table}_created_by_member_id', table, 'members',
            ['created_by_member_id'], ['id'], ondelete='SET NULL')
        op.create_index(f'idx_{table}_project_id', table, ['project_id'])


def downgrade() -> None:
    for table in SCOPED_TABLES:
        op.drop_index(f'idx_{table}_project_id', table_name=table)
        op.drop_constraint(f'fk_{table}_created_by_member_id', table, type_='foreignkey')
        op.drop_constraint(f'fk_{table}_project_id', table, type_='foreignkey')
        op.drop_column(table, 'created_by_member_id')
        op.drop_column(table, 'project_id')
    op.drop_table('uploads')
    op.drop_table('project_members')
    op.drop_table('projects')
    op.drop_table('members')

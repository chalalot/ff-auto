"""baseline: seven core tables

Revision ID: 0001
Revises: 
Create Date: 2026-07-06 15:44:13.164390

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Adoption-aware baseline: the five sqlite-era tables are always new, but
    # runs/posts may already exist in a legacy Postgres (the old psycopg2
    # RunsPostsStorage created them outside Alembic). Skip creating whatever
    # already exists so `alembic upgrade head` can adopt that database
    # instead of aborting with DuplicateTable.
    inspector = sa.inspect(op.get_bind())
    existing = set(inspector.get_table_names())

    def _table_absent(name: str) -> bool:
        return name not in existing

    if _table_absent('caption_exports'):
        op.create_table('caption_exports',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('file_id', sa.Text(), nullable=False),
    sa.Column('filename', sa.Text(), nullable=False),
    sa.Column('public_url', sa.Text(), nullable=False),
    sa.Column('image_count', sa.Integer(), server_default='0', nullable=False),
    sa.Column('exported_at', sa.Text(), nullable=False),
    sa.PrimaryKeyConstraint('id')
        )
    if _table_absent('evaluations'):
        op.create_table('evaluations',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('media_type', sa.Text(), nullable=False),
    sa.Column('media_path', sa.Text(), nullable=False),
    sa.Column('prompt', sa.Text(), nullable=True),
    sa.Column('model', sa.Text(), nullable=False),
    sa.Column('rubric_version', sa.Text(), nullable=False),
    sa.Column('status', sa.Text(), server_default='pending', nullable=False),
    sa.Column('scores_json', sa.Text(), server_default='[]', nullable=False),
    sa.Column('overall_score', sa.Float(), nullable=True),
    sa.Column('summary', sa.Text(), nullable=True),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.Column('raw_response', sa.Text(), nullable=True),
    sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.Column('completed_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id')
        )
    if _table_absent('image_logs'):
        op.create_table('image_logs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('execution_id', sa.Text(), nullable=False),
    sa.Column('prompt', sa.Text(), nullable=False),
    sa.Column('persona', sa.Text(), nullable=True),
    sa.Column('image_ref_path', sa.Text(), nullable=True),
    sa.Column('result_image_path', sa.Text(), nullable=True),
    sa.Column('status', sa.Text(), server_default='pending', nullable=True),
    sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.PrimaryKeyConstraint('id')
        )
    if _table_absent('runpod_jobs'):
        op.create_table('runpod_jobs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('job_id', sa.Text(), nullable=False),
    sa.Column('endpoint_id', sa.Text(), nullable=False),
    sa.Column('lora_name', sa.Text(), nullable=False),
    sa.Column('submitted_at', sa.Text(), nullable=False),
    sa.Column('job_input', sa.Text(), nullable=False),
    sa.Column('status', sa.Text(), nullable=True),
    sa.Column('output', sa.Text(), nullable=True),
    sa.Column('updated_at', sa.Text(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('job_id', name='uq_runpod_jobs_job_id')
        )
    if _table_absent('runs'):
        op.create_table('runs',
    sa.Column('id', sa.Text(), nullable=False),
    sa.Column('persona_name', sa.Text(), nullable=False),
    sa.Column('trend_text', sa.Text(), nullable=False),
    sa.Column('num_posts', sa.Integer(), nullable=False),
    sa.Column('adapted_idea', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('trend_profile', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('created_at', sa.BigInteger(), nullable=False),
    sa.Column('updated_at', sa.BigInteger(), nullable=False),
    sa.PrimaryKeyConstraint('id')
        )
        op.create_index('idx_runs_created_at', 'runs', ['created_at'], unique=False)
    if _table_absent('video_logs'):
        op.create_table('video_logs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('batch_id', sa.Text(), nullable=True),
    sa.Column('execution_id', sa.Text(), nullable=False),
    sa.Column('prompt', sa.Text(), nullable=False),
    sa.Column('source_image_path', sa.Text(), nullable=True),
    sa.Column('video_output_path', sa.Text(), nullable=True),
    sa.Column('status', sa.Text(), server_default='pending', nullable=True),
    sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.Column('filename_id', sa.Text(), nullable=True),
    sa.PrimaryKeyConstraint('id')
        )
    if _table_absent('posts'):
        op.create_table('posts',
    sa.Column('id', sa.Text(), nullable=False),
    sa.Column('run_id', sa.Text(), nullable=False),
    sa.Column('post_index', sa.Integer(), nullable=False),
    sa.Column('caption', sa.Text(), nullable=True),
    sa.Column('hashtags', postgresql.ARRAY(sa.Text()), nullable=True),
    sa.Column('cta', sa.Text(), nullable=True),
    sa.Column('image_url', sa.Text(), nullable=True),
    sa.Column('image_prompt', sa.Text(), nullable=True),
    sa.Column('positive_prompt', sa.Text(), nullable=True),
    sa.Column('negative_prompt', sa.Text(), nullable=True),
    sa.Column('visual_plan', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('content_seed', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('versions', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('current_version', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.BigInteger(), nullable=False),
    sa.Column('updated_at', sa.BigInteger(), nullable=False),
    sa.ForeignKeyConstraint(['run_id'], ['runs.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
        )
        op.create_index('idx_posts_run_id', 'posts', ['run_id'], unique=False)
    else:
        # Adopting a pre-existing posts table: the legacy DDL lacked the two
        # version columns that save_post_version/get_post_versions require
        # (older live DBs may not have gained them yet) — add if missing.
        post_columns = {c['name'] for c in inspector.get_columns('posts')}
        if 'versions' not in post_columns:
            op.add_column(
                'posts',
                sa.Column('versions', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            )
        if 'current_version' not in post_columns:
            op.add_column(
                'posts',
                sa.Column('current_version', sa.Integer(), nullable=True),
            )


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index('idx_posts_run_id', table_name='posts')
    op.drop_table('posts')
    op.drop_table('video_logs')
    op.drop_index('idx_runs_created_at', table_name='runs')
    op.drop_table('runs')
    op.drop_table('runpod_jobs')
    op.drop_table('image_logs')
    op.drop_table('evaluations')
    op.drop_table('caption_exports')
    # ### end Alembic commands ###

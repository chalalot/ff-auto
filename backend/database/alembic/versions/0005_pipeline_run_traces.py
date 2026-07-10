"""add pipeline run and step traces

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-10
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "pipeline_runs",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("pipeline_name", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default="queued", nullable=False),
        sa.Column("input_payload", postgresql.JSONB(), nullable=True),
        sa.Column("final_output", postgresql.JSONB(), nullable=True),
        sa.Column("error", postgresql.JSONB(), nullable=True),
        sa.Column("started_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("finished_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column("project_id", sa.Text(), nullable=True),
        sa.Column("created_by_member_id", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["created_by_member_id"], ["members.id"], ondelete="SET NULL"
        ),
    )
    op.create_index(
        "idx_pipeline_runs_status_updated_at",
        "pipeline_runs",
        ["status", "updated_at"],
    )
    op.create_index(
        "idx_pipeline_runs_project_id", "pipeline_runs", ["project_id"]
    )

    op.create_table(
        "pipeline_steps",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("run_id", sa.Text(), nullable=False),
        sa.Column("step_key", sa.Text(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("status", sa.Text(), server_default="queued", nullable=False),
        sa.Column("input_payload", postgresql.JSONB(), nullable=True),
        sa.Column("system_prompt", sa.Text(), nullable=True),
        sa.Column("rendered_context", postgresql.JSONB(), nullable=True),
        sa.Column("output_payload", postgresql.JSONB(), nullable=True),
        sa.Column("usage", postgresql.JSONB(), nullable=True),
        sa.Column("partial_output", postgresql.JSONB(), nullable=True),
        sa.Column("error", postgresql.JSONB(), nullable=True),
        sa.Column("model_name", sa.Text(), nullable=True),
        sa.Column("started_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("finished_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["run_id"], ["pipeline_runs.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint("run_id", "step_key", name="uq_pipeline_steps_run_key"),
    )
    op.create_index(
        "idx_pipeline_steps_run_sequence",
        "pipeline_steps",
        ["run_id", "sequence"],
    )
    op.create_index(
        "idx_pipeline_steps_status_updated_at",
        "pipeline_steps",
        ["status", "updated_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_pipeline_steps_status_updated_at", table_name="pipeline_steps")
    op.drop_index("idx_pipeline_steps_run_sequence", table_name="pipeline_steps")
    op.drop_table("pipeline_steps")
    op.drop_index("idx_pipeline_runs_project_id", table_name="pipeline_runs")
    op.drop_index("idx_pipeline_runs_status_updated_at", table_name="pipeline_runs")
    op.drop_table("pipeline_runs")

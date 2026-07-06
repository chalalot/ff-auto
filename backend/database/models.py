"""
SQLAlchemy 2.0 declarative models for all ff-auto tables.

These mirror the legacy DDL exactly (see the CREATE TABLE strings that used to
live in the six storage modules). Schema changes are made ONLY through Alembic
migrations — there is no create-if-missing code anywhere in the app.

Type-mapping rules (from the phase 1 plan):
- sqlite ``INTEGER PRIMARY KEY AUTOINCREMENT``  -> ``Integer`` identity PK
- ``TIMESTAMP DEFAULT CURRENT_TIMESTAMP``       -> ``DateTime(timezone=True)``
                                                   with ``server_default=func.now()``
- text-JSON columns (e.g. ``evaluations.scores_json``) stay ``Text`` — JSONB
  conversion is out of scope this phase (return-shape compatibility).
- ``runs``/``posts`` keep their existing JSONB / TEXT[] / FK CASCADE shape.
"""
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Float,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TIMESTAMP
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from datetime import datetime


class Base(DeclarativeBase):
    pass


class Evaluation(Base):
    """Media evaluation attempts (legacy: evaluations.db / evaluations table)."""

    __tablename__ = "evaluations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    media_type: Mapped[str] = mapped_column(Text, nullable=False)
    media_path: Mapped[str] = mapped_column(Text, nullable=False)
    prompt: Mapped[Optional[str]] = mapped_column(Text)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    rubric_version: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="pending"
    )
    scores_json: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="[]"
    )
    overall_score: Mapped[Optional[float]] = mapped_column(Float)
    summary: Mapped[Optional[str]] = mapped_column(Text)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    raw_response: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True)
    )


class ImageLog(Base):
    """Image generation logs (legacy: image_logs.db / image_logs table)."""

    __tablename__ = "image_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    execution_id: Mapped[str] = mapped_column(Text, nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    persona: Mapped[Optional[str]] = mapped_column(Text)
    image_ref_path: Mapped[Optional[str]] = mapped_column(Text)
    result_image_path: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[Optional[str]] = mapped_column(Text, server_default="pending")
    created_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )


class VideoLog(Base):
    """Video generation logs (legacy: video_logs.db / video_logs table)."""

    __tablename__ = "video_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    batch_id: Mapped[Optional[str]] = mapped_column(Text)
    execution_id: Mapped[str] = mapped_column(Text, nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    source_image_path: Mapped[Optional[str]] = mapped_column(Text)
    video_output_path: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[Optional[str]] = mapped_column(Text, server_default="pending")
    created_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
    filename_id: Mapped[Optional[str]] = mapped_column(Text)


class RunpodJob(Base):
    """Runpod training jobs (legacy: image_logs.db / runpod_jobs table)."""

    __tablename__ = "runpod_jobs"
    __table_args__ = (UniqueConstraint("job_id", name="uq_runpod_jobs_job_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[str] = mapped_column(Text, nullable=False)
    endpoint_id: Mapped[str] = mapped_column(Text, nullable=False)
    lora_name: Mapped[str] = mapped_column(Text, nullable=False)
    submitted_at: Mapped[str] = mapped_column(Text, nullable=False)
    job_input: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[Optional[str]] = mapped_column(Text)
    output: Mapped[Optional[str]] = mapped_column(Text)
    updated_at: Mapped[Optional[str]] = mapped_column(Text)


class CaptionExport(Base):
    """Caption sheet exports (legacy: image_logs.db / caption_exports table)."""

    __tablename__ = "caption_exports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    file_id: Mapped[str] = mapped_column(Text, nullable=False)
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    public_url: Mapped[str] = mapped_column(Text, nullable=False)
    image_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    exported_at: Mapped[str] = mapped_column(Text, nullable=False)


class Run(Base):
    """Campaign runs (already Postgres; legacy DDL in runs_posts_storage)."""

    __tablename__ = "runs"
    __table_args__ = (Index("idx_runs_created_at", "created_at"),)

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    persona_name: Mapped[str] = mapped_column(Text, nullable=False)
    trend_text: Mapped[str] = mapped_column(Text, nullable=False)
    num_posts: Mapped[int] = mapped_column(Integer, nullable=False)
    adapted_idea: Mapped[Optional[dict]] = mapped_column(JSONB)
    trend_profile: Mapped[Optional[dict]] = mapped_column(JSONB)
    # "metadata" is reserved on declarative classes; column name is preserved.
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB)
    created_at: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_at: Mapped[int] = mapped_column(BigInteger, nullable=False)


class Post(Base):
    """Campaign posts (already Postgres; legacy DDL in runs_posts_storage).

    ``versions``/``current_version`` are referenced by the storage layer's
    versioning methods (save_post_version & co.) even though the legacy
    create_tables DDL omitted them — they existed only in the live DB. The
    Alembic baseline makes them part of the owned schema.
    """

    __tablename__ = "posts"
    __table_args__ = (Index("idx_posts_run_id", "run_id"),)

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    run_id: Mapped[str] = mapped_column(
        Text, ForeignKey("runs.id", ondelete="CASCADE"), nullable=False
    )
    post_index: Mapped[int] = mapped_column(Integer, nullable=False)
    caption: Mapped[Optional[str]] = mapped_column(Text)
    hashtags: Mapped[Optional[list]] = mapped_column(ARRAY(Text))
    cta: Mapped[Optional[str]] = mapped_column(Text)
    image_url: Mapped[Optional[str]] = mapped_column(Text)
    image_prompt: Mapped[Optional[str]] = mapped_column(Text)
    positive_prompt: Mapped[Optional[str]] = mapped_column(Text)
    negative_prompt: Mapped[Optional[str]] = mapped_column(Text)
    visual_plan: Mapped[Optional[dict]] = mapped_column(JSONB)
    content_seed: Mapped[Optional[dict]] = mapped_column(JSONB)
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB)
    versions: Mapped[Optional[list]] = mapped_column(JSONB)
    current_version: Mapped[Optional[int]] = mapped_column(Integer)
    created_at: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_at: Mapped[int] = mapped_column(BigInteger, nullable=False)

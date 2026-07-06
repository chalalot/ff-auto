"""
Shared SQLAlchemy engine/session layer for FastAPI and Celery.

- ``get_engine()``     lazy singleton, pooled; never connects at import time
                       (Celery forks — each process builds its own engine on
                       first use).
- ``SessionLocal``     session factory bound lazily to the singleton engine.
- ``get_db()``         FastAPI dependency: yields a session, always closes.
- ``session_scope()``  context manager for Celery tasks and scripts: commits
                       on success, rolls back on exception, always closes.

The connection URL comes exclusively from
``db_utils.get_postgres_connection_string()`` (DATABASE_URL priority chain).
There is no sqlite fallback.
"""
from contextlib import contextmanager
from typing import Generator, Iterator, Optional

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from .db_utils import get_postgres_connection_string

_engine: Optional[Engine] = None

SessionLocal = sessionmaker(autoflush=False, expire_on_commit=False)


def get_engine() -> Engine:
    """Return the process-wide engine, creating it on first use."""
    global _engine
    if _engine is None:
        _engine = create_engine(
            get_postgres_connection_string(),
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
        )
        SessionLocal.configure(bind=_engine)
    return _engine


def dispose_engine() -> None:
    """Dispose the singleton engine (tests / post-fork hooks)."""
    global _engine
    if _engine is not None:
        _engine.dispose()
        _engine = None


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a request-scoped session."""
    get_engine()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transactional scope for Celery tasks and scripts."""
    get_engine()
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

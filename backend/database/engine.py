"""
Shared SQLAlchemy engine/session layer for FastAPI and Celery.

- ``get_engine()``     lazy singleton, pooled; never connects at import time
                       (Celery forks — each process builds its own engine on
                       first use).
- ``SessionLocal``     session factory bound lazily to the singleton engine.
- ``session_scope()``  context manager for Celery tasks and scripts: commits
                       on success, rolls back on exception, always closes.

The connection URL comes exclusively from
``db_utils.get_postgres_connection_string()`` (DATABASE_URL priority chain).
There is no sqlite fallback.
"""
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

from sqlalchemy import Engine, create_engine, text
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


def _alembic_head() -> str:
    """The newest revision shipped with this code (no alembic.ini needed)."""
    from alembic.script import ScriptDirectory

    script_location = Path(__file__).resolve().parent / "alembic"
    return ScriptDirectory(str(script_location)).get_current_head()


def assert_database_ready(database_url: Optional[str] = None) -> None:
    """Fail-fast startup check for the API and Celery workers.

    Verifies the database is reachable AND `alembic current == head`.
    Raises RuntimeError with a one-line actionable message otherwise.
    Never migrates — migrations are run explicitly (`alembic upgrade head`).
    """
    url = database_url or get_postgres_connection_string()
    masked = get_postgres_connection_string(url, mask_password=True)
    probe = create_engine(url, pool_pre_ping=True)
    try:
        try:
            with probe.connect() as conn:
                try:
                    current = conn.execute(
                        text("SELECT version_num FROM alembic_version")
                    ).scalar()
                except Exception:
                    raise RuntimeError(
                        f"Database at {masked} has no alembic_version table — "
                        "run `alembic upgrade head` before starting the app."
                    )
        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError(
                f"Cannot reach database at {masked} — check DATABASE_URL "
                f"({exc.__class__.__name__})."
            )
    finally:
        probe.dispose()

    head = _alembic_head()
    if current != head:
        raise RuntimeError(
            f"Database schema at revision {current!r} but code expects {head!r} — "
            "run `alembic upgrade head` before starting the app."
        )

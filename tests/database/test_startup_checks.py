"""
Task 7 tests: fail-fast startup checks.

API (lifespan) and Celery (worker_init) must refuse to start when the
database is unreachable or migrations are not at alembic head, with a
one-line actionable error naming DATABASE_URL / `alembic upgrade head`.
The app process never auto-migrates.
"""
import pytest
from sqlalchemy import create_engine, text


def test_ready_on_migrated_db(migrated_engine):
    from backend.database.engine import assert_database_ready

    assert_database_ready()  # must not raise


def test_unreachable_db_raises_actionable_error(migrated_engine):
    from backend.database.engine import assert_database_ready

    bad_url = "postgresql://nobody:nope@127.0.0.1:1/nodb"
    with pytest.raises(RuntimeError) as exc:
        assert_database_ready(database_url=bad_url)
    assert "DATABASE_URL" in str(exc.value)


def test_head_mismatch_raises_actionable_error(migrated_engine, database_url):
    from backend.database.engine import assert_database_ready

    admin = create_engine(database_url)
    with admin.begin() as conn:
        current = conn.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one()
        conn.execute(
            text("UPDATE alembic_version SET version_num = 'deadbeef'")
        )
    try:
        with pytest.raises(RuntimeError) as exc:
            assert_database_ready()
        assert "alembic upgrade head" in str(exc.value)
    finally:
        with admin.begin() as conn:
            conn.execute(
                text("UPDATE alembic_version SET version_num = :v"),
                {"v": current},
            )
        admin.dispose()


def test_missing_alembic_version_table_raises(migrated_engine, database_url):
    from backend.database.engine import assert_database_ready

    admin = create_engine(database_url)
    with admin.begin() as conn:
        conn.execute(text("ALTER TABLE alembic_version RENAME TO alembic_version_bak"))
    try:
        with pytest.raises(RuntimeError) as exc:
            assert_database_ready()
        assert "alembic upgrade head" in str(exc.value)
    finally:
        with admin.begin() as conn:
            conn.execute(
                text("ALTER TABLE alembic_version_bak RENAME TO alembic_version")
            )
        admin.dispose()


def test_api_lifespan_runs_the_check(migrated_engine, monkeypatch):
    """FastAPI startup must invoke assert_database_ready and abort on failure."""
    from fastapi.testclient import TestClient

    import backend.main as main_module

    calls = []
    monkeypatch.setattr(
        main_module, "assert_database_ready", lambda: calls.append(True)
    )
    with TestClient(main_module.app):
        pass
    assert calls == [True]

    def boom():
        raise RuntimeError("Database not ready")

    monkeypatch.setattr(main_module, "assert_database_ready", boom)
    with pytest.raises(RuntimeError, match="Database not ready"):
        with TestClient(main_module.app):
            pass


def test_celery_worker_init_is_wired(migrated_engine):
    """celery_app registers a worker_init hook that runs the readiness check."""
    from celery.signals import worker_init

    import backend.celery_app as celery_module

    receivers = [
        getattr(r[1], "__name__", "")
        for r in worker_init.receivers
    ]
    assert any("database" in name or "db" in name for name in receivers), (
        f"no db readiness receiver on worker_init: {receivers}"
    )

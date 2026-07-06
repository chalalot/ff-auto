"""
One-off, idempotent data migration into the phase-1 Postgres.

Usage:
    python -m scripts.migrate_sqlite_to_pg --sqlite-dir <dir> \
        [--source-database-url <url>] [--dry-run]

Two data sources are migrated:

1. Legacy sqlite files found in --sqlite-dir (evaluations.db, image_logs.db,
   video_logs.db — image_logs.db historically also carries the runpod_jobs
   and caption_exports tables, and standalone runpod/caption dbs are picked
   up too). Every known table in EVERY file is copied; if the same table
   appears in more than one file, all files' rows are merged (a loud warning
   is printed, and primary-key collisions keep the earlier file's row).

2. The legacy runs/posts Postgres (the DB the old psycopg2 RunsPostsStorage
   wrote to, configured via DB_HOST/DB_USER/... env vars). Pass it as
   --source-database-url to copy runs and posts into the new target.
   Without it, runs/posts are NOT migrated and the script says so loudly.

Mechanics:

- bulk INSERT via SQLAlchemy Core with ON CONFLICT DO NOTHING keyed on the
  primary key (job_id conflicts are likewise skipped for runpod_jobs), so
  re-running the script never duplicates or overwrites rows;
- original IDs are preserved; after copying explicit integer PKs, each
  table's identity sequence is bumped to max(id) (classic gotcha);
- legacy sqlite CURRENT_TIMESTAMP strings ('YYYY-MM-DD HH:MM:SS', assumed
  UTC) are parsed into aware datetimes;
- a missing file is a warning, not an error.

Prints per-table: source rows / pg rows before / pg rows after.
"""
import argparse
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from sqlalchemy import Table, create_engine, func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import make_url

from backend.database.db_utils import get_postgres_connection_string
from backend.database.models import (
    CaptionExport,
    Evaluation,
    ImageLog,
    Post,
    Run,
    RunpodJob,
    VideoLog,
)

# Known legacy sqlite files. image_logs.db carries three tables in
# production; standalone runpod/caption dbs (custom db_path deployments) are
# also scanned for the same tables.
SQLITE_FILES = [
    "evaluations.db",
    "image_logs.db",
    "video_logs.db",
    "runpod_jobs.db",
    "caption_exports.db",
]

# table name -> (model, timestamp columns to parse)
TABLES = {
    "evaluations": (Evaluation, ("created_at", "completed_at")),
    "image_logs": (ImageLog, ("created_at",)),
    "video_logs": (VideoLog, ("created_at",)),
    "runpod_jobs": (RunpodJob, ()),
    "caption_exports": (CaptionExport, ()),
}

_BATCH_SIZE = 1000

_TS_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M:%S.%f",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%S.%f",
)


def _parse_ts(value) -> Optional[datetime]:
    """Parse a legacy sqlite timestamp string into an aware UTC datetime."""
    if value is None or isinstance(value, datetime):
        return value
    value = str(value).strip()
    if not value:
        return None
    for fmt in _TS_FORMATS:
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    raise ValueError(f"Unparseable legacy timestamp: {value!r}")


def _sqlite_tables(conn: sqlite3.Connection) -> List[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'"
    ).fetchall()
    return [r[0] for r in rows]


def _count(connection, table: Table) -> int:
    return connection.execute(select(func.count()).select_from(table)).scalar_one()


def _copy_table(
    connection,
    sqlite_conn: sqlite3.Connection,
    table_name: str,
    dry_run: bool,
) -> Dict[str, int]:
    model, ts_columns = TABLES[table_name]
    table: Table = model.__table__

    sqlite_conn.row_factory = sqlite3.Row
    sqlite_rows = sqlite_conn.execute(f"SELECT * FROM {table_name}").fetchall()

    pg_before = _count(connection, table)

    if sqlite_rows and not dry_run:
        # Only copy columns both sides know about; anything else keeps its
        # Postgres server default.
        sqlite_cols = set(sqlite_rows[0].keys())
        shared_cols = [c.name for c in table.columns if c.name in sqlite_cols]

        payload = []
        for row in sqlite_rows:
            item = {}
            for col in shared_cols:
                value = row[col]
                if col in ts_columns:
                    value = _parse_ts(value)
                item[col] = value
            payload.append(item)

        for start in range(0, len(payload), _BATCH_SIZE):
            batch = payload[start : start + _BATCH_SIZE]
            connection.execute(
                pg_insert(table).on_conflict_do_nothing(), batch
            )

        # Bump the identity sequence past the copied explicit ids.
        connection.execute(
            text(
                "SELECT setval(pg_get_serial_sequence(:table, 'id'),"
                " (SELECT COALESCE(MAX(id), 1) FROM " + table_name + "))"
            ),
            {"table": table_name},
        )

    pg_after = _count(connection, table)
    return {
        "sqlite_rows": len(sqlite_rows),
        "pg_before": pg_before,
        "pg_after": pg_after,
    }


def _copy_pg_table(
    target_connection,
    source_connection,
    model,
    dry_run: bool,
) -> Dict[str, int]:
    """Copy one table postgres -> postgres with ON CONFLICT DO NOTHING.

    Only columns present on BOTH sides are copied (an older source posts
    table may lack versions/current_version — those keep their defaults).
    """
    table: Table = model.__table__

    source_cols = {
        row[0]
        for row in source_connection.execute(
            text(
                "SELECT column_name FROM information_schema.columns"
                " WHERE table_name = :t"
            ),
            {"t": table.name},
        )
    }
    shared = [c for c in table.columns if c.name in source_cols]
    col_list = ", ".join(f'"{c.name}"' for c in shared)

    source_rows = source_connection.execute(
        text(f'SELECT {col_list} FROM "{table.name}"')  # noqa: S608 — model-derived names
    ).mappings().all()

    pg_before = _count(target_connection, table)
    if source_rows and not dry_run:
        payload = [dict(r) for r in source_rows]
        for start in range(0, len(payload), _BATCH_SIZE):
            target_connection.execute(
                pg_insert(table).on_conflict_do_nothing(),
                payload[start : start + _BATCH_SIZE],
            )
    pg_after = _count(target_connection, table)
    return {
        "sqlite_rows": len(source_rows),  # key kept for uniform reporting
        "pg_before": pg_before,
        "pg_after": pg_after,
    }


def migrate(
    sqlite_dir: str,
    database_url: Optional[str] = None,
    source_database_url: Optional[str] = None,
    dry_run: bool = False,
) -> Dict[str, Dict[str, int]]:
    """Copy every known table from the sqlite files in ``sqlite_dir`` — and,
    when ``source_database_url`` is given, runs/posts from the legacy
    Postgres — into the target Postgres.
    Returns {table: {sqlite_rows, pg_before, pg_after}} (cumulative when a
    table spans several sqlite files)."""
    directory = Path(sqlite_dir)
    target_url = database_url or get_postgres_connection_string()
    engine = create_engine(target_url, pool_pre_ping=True)

    stats: Dict[str, Dict[str, int]] = {}
    table_sources: Dict[str, str] = {}
    try:
        with engine.begin() as connection:
            for filename in SQLITE_FILES:
                db_file = directory / filename
                if not db_file.exists():
                    print(f"[migrate] {filename}: not found — skipping")
                    continue

                sqlite_conn = sqlite3.connect(db_file)
                try:
                    for table_name in _sqlite_tables(sqlite_conn):
                        if table_name not in TABLES:
                            continue
                        if table_name in table_sources:
                            print(
                                f"[migrate] WARNING: table {table_name!r} appears in "
                                f"both {table_sources[table_name]} and {filename}; "
                                "merging rows from both (primary-key collisions "
                                "keep the earlier file's row — verify counts!)"
                            )
                        result = _copy_table(
                            connection, sqlite_conn, table_name, dry_run
                        )
                        if table_name in stats:
                            prior = stats[table_name]
                            result = {
                                "sqlite_rows": prior["sqlite_rows"] + result["sqlite_rows"],
                                "pg_before": prior["pg_before"],
                                "pg_after": result["pg_after"],
                            }
                        stats[table_name] = result
                        table_sources.setdefault(table_name, filename)
                        print(
                            f"[migrate] {table_name} (from {filename}): "
                            f"sqlite rows={result['sqlite_rows']} "
                            f"pg before={result['pg_before']} "
                            f"pg after={result['pg_after']}"
                            + (" [dry-run]" if dry_run else "")
                        )
                finally:
                    sqlite_conn.close()

            # --- legacy runs/posts Postgres -> target Postgres ---
            if source_database_url:
                src = make_url(source_database_url)
                tgt = make_url(target_url)
                if (src.host, src.port, src.database) == (
                    tgt.host,
                    tgt.port,
                    tgt.database,
                ):
                    print(
                        "[migrate] source and target Postgres are the same DB — "
                        "skipping runs/posts copy (nothing to move)"
                    )
                else:
                    source_engine = create_engine(
                        source_database_url, pool_pre_ping=True
                    )
                    try:
                        with source_engine.connect() as source_connection:
                            # runs first: posts.run_id FK references runs.id
                            for model in (Run, Post):
                                name = model.__table__.name
                                result = _copy_pg_table(
                                    connection, source_connection, model, dry_run
                                )
                                stats[name] = result
                                print(
                                    f"[migrate] {name} (from legacy postgres): "
                                    f"source rows={result['sqlite_rows']} "
                                    f"pg before={result['pg_before']} "
                                    f"pg after={result['pg_after']}"
                                    + (" [dry-run]" if dry_run else "")
                                )
                    finally:
                        source_engine.dispose()
            else:
                print(
                    "[migrate] NOTE: --source-database-url not given — the legacy "
                    "runs/posts Postgres data was NOT migrated. If the old "
                    "deployment used RunsPostsStorage (DB_HOST/DB_USER env "
                    "config), pass that DB's URL or its history will be missing."
                )
    finally:
        engine.dispose()

    if not stats:
        print(f"[migrate] no known sqlite files found in {directory} — nothing to do")
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Migrate legacy sqlite data into Postgres (idempotent)."
    )
    parser.add_argument(
        "--sqlite-dir",
        required=True,
        help="Directory containing the legacy .db files (e.g. ./sqlite-backup)",
    )
    parser.add_argument(
        "--source-database-url",
        help=(
            "URL of the LEGACY Postgres holding runs/posts (the DB the old "
            "DB_HOST/DB_USER env config pointed at). When given, runs and "
            "posts are copied into the target as well."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Read and report row counts without writing to Postgres",
    )
    args = parser.parse_args()
    migrate(
        args.sqlite_dir,
        source_database_url=args.source_database_url,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()

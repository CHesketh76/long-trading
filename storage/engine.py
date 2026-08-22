"""Storage layer for Macroscope (T-001).

Side-agnostic storage: Postgres is primary; a Parquet seam on object storage is
reserved for price/series history. For local dev without a Postgres server, the
same schema runs on SQLite via `engine.py` — see README for how to switch modes.
"""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine, text


def get_database_url() -> str:
    """Resolve the DB URL from env.

    POSTGRES_URL (or individual PG_* vars) → Postgres primary path.
    Otherwise → SQLite dev mode at ./.dev/macroscope_dev.sqlite.
    """
    url = os.environ.get("POSTGRES_URL")
    if url:
        return url
    dev_db = Path(__file__).resolve().parent.parent / ".dev" / "macroscope_dev.sqlite"
    dev_db.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{dev_db}"


def create_engine_from_env() -> None:  # noqa: F811 (redefine for env resolution)
    """Create and expose a module-level engine bound to the resolved URL."""
    global engine
    url = get_database_url()
    connect_args = {}
    if url.startswith("sqlite"):
        connect_args = {"check_same_thread": False}
    engine = create_engine(url, connect_args=connect_args, future=True)


def init_db(engine) -> None:
    """Create all tables + indexes from the schema module."""
    from .schema import SCHEMA_DDL_STATEMENTS, SCHEMA_INDEX_STATEMENTS

    with engine.begin() as conn:
        for stmt in SCHEMA_DDL_STATEMENTS:
            conn.execute(text(stmt))
        for idx in SCHEMA_INDEX_STATEMENTS:
            conn.execute(text(idx))


def reset_dev_db(engine) -> None:
    """Drop and recreate all tables (dev convenience)."""
    from .schema import SCHEMA_DDL_STATEMENTS, SCHEMA_INDEX_STATEMENTS

    with engine.begin() as conn:
        for tbl in ("source_registry", "decisions", "theses", "event_revisions", "events"):
            conn.execute(text(f"DROP TABLE IF EXISTS {tbl}"))
        for stmt in SCHEMA_DDL_STATEMENTS:
            conn.execute(text(stmt))
        for idx in SCHEMA_INDEX_STATEMENTS:
            conn.execute(text(idx))


# Lazy engine, resolved on first use so env vars are read at call time.
engine = None

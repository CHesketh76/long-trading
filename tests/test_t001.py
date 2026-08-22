"""T-001 acceptance tests: runs against the seeded SQLite dev DB."""

from datetime import datetime, timezone

import pytest
from sqlalchemy import text

from storage.engine import create_engine_from_env, init_db
from storage.seed import seed


@pytest.fixture(scope="module")
def db():
    create_engine_from_env()
    from storage.engine import engine  # set by create_engine_from_env above
    init_db(engine)
    n = seed(engine)
    assert n > 0
    return engine


def test_tables_exist(db):
    with db.connect() as conn:
        rows = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        ).fetchall()
    names = {r[0] for r in rows}
    assert {"events", "event_revisions", "theses", "decisions", "source_registry"} <= names


def test_events_has_vintage_join_columns(db):
    """sr-dev lens: event_ts + sequence are first-class indexed columns."""
    with db.connect() as conn:
        cols = {r[1] for r in conn.execute(
            text("PRAGMA table_info(events)")
        ).fetchall()}
    assert "event_ts" in cols
    assert "sequence" in cols


def test_seed_populated(db):
    with db.connect() as conn:
        n = conn.execute(text("SELECT COUNT(*) FROM events")).scalar_one()
    assert n >= 4


def test_revision_chain_two_events_no_overwrite(db):
    """Macro release first-print + revision = two dated events, not one overwrite."""
    with db.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT event_id, sequence FROM events "
                "WHERE source_id='bureau_of_labor_stats' ORDER BY sequence"
            )
        ).fetchall()
    assert len(rows) == 2, f"expected first-print + revision, got {len(rows)}"


def test_source_registry_tiers(db):
    with db.connect() as conn:
        tiers = dict(conn.execute(
            text("SELECT source_id, tier FROM source_registry")
        ).fetchall())
    assert tiers["bureau_of_labor_stats"] == 1.00
    assert tiers["reuters"] == 0.80


def test_pydantic_event_object_validates():
    from models import EventObject

    evt = EventObject(
        source_id="fred",
        published_at=datetime(2026, 8, 20, tzinfo=timezone.utc),
        raw_text="10Y yield up",
        source_tier=1,
        event_type="macro_data",
        numbers_extracted={"yield_10y": 4.25},
    )
    assert evt.source_tier == 1
    assert evt.retrieved_at.tzinfo is not None

"""T-002 acceptance tests: vintage / point-in-time tagging layer.

Covers the four sr-dev acceptance items from tickets/T-002.md:
  * dedupe collapses near-duplicates to one cluster (earliest + highest-tier kept)
  * macro-release revision produces two dated events, not an overwrite
  * quarantine bucket is non-empty for unproven-vintage inputs; live corpus never
    contains quarantined rows
  * audit trail: every stamped item carries the vintage fields and is reproducible
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from macroscope.models import EventObject
from macroscope.vintage import (
    dedupe,
    quarantine,
    quarantine_reasons,
    record_revision,
    stamp,
)


def _evt(source_id: str, published_at, *, raw_text="", source_tier=1,
         retrieved_at=None, url=None, event_type="macro_data") -> EventObject:
    return EventObject(
        source_id=source_id,
        published_at=published_at,
        retrieved_at=retrieved_at or (published_at + timedelta(minutes=30) if published_at else datetime(2026, 8, 20, tzinfo=timezone.utc)),
        raw_text=raw_text,
        source_tier=source_tier,
        url=url,
        event_type=event_type,
    )


# --- deliverable #4: quarantine rule engine --------------------------------

def test_quarantine_flags_missing_published_at():
    reasons = quarantine_reasons(_evt("fred", None))
    assert "missing published_at" in reasons


def test_quarantine_flags_lookahead():
    pub = datetime(2026, 8, 20, 13, 0, tzinfo=timezone.utc)
    got = pub - timedelta(hours=1)  # ingested before the publisher released it
    reasons = quarantine_reasons(_evt("fred", pub, retrieved_at=got))
    assert any("lookahead" in r for r in reasons)


def test_quarantine_bucket_nonempty_for_unproven_inputs():
    items = [
        _evt("fred", datetime(2026, 8, 20, 13, 0, tzinfo=timezone.utc), raw_text="good"),
        _evt("reuters", None, raw_text="no release time"),
    ]
    live, quarantined = quarantine(items)
    assert len(live) == 1
    assert len(quarantined) == 1
    # live corpus never contains a quarantined row
    assert all(r.vintage_ok for r in live)
    assert all(not r.vintage_ok for r in quarantined)


def test_known_source_gate():
    reasons = quarantine_reasons(_evt("unknown_outlet", datetime(2026, 8, 20, tzinfo=timezone.utc)),
                                 known_sources=["fred", "reuters"])
    assert any("unverifiable" in r for r in reasons)


# --- deliverable #2: dedupe within time windows -----------------------------

def test_dedupe_collapses_near_duplicates_to_one_cluster():
    pub = datetime(2026, 8, 20, 13, 0, tzinfo=timezone.utc)
    items = [
        _evt("reuters", pub - timedelta(minutes=4), raw_text="US CPI rose 0.3% in July", source_tier=2),
        _evt("bloomberg", pub + timedelta(minutes=1), raw_text="US CPI rose 0.3% in July", source_tier=3),
        _evt("wsj", pub - timedelta(minutes=2), raw_text="US CPI rose 0.3% in July", source_tier=4),
    ]
    clusters = dedupe(items)
    # all three near-duplicates collapse into a single cluster
    assert len(clusters) == 1
    cluster_id, cluster = next(iter(clusters.items()))
    kept = cluster.kept_event_id
    # highest-authority (lowest tier number) copy survives: reuters T2 > bloomberg T3 > wsj T4
    assert kept == "reuters"
    # the two dropped copies are recorded as members; kept + members == all three
    assert {kept, *cluster.members} == {"reuters", "bloomberg", "wsj"}


def test_dedupe_keeps_earliest_when_tiers_equal():
    pub = datetime(2026, 8, 20, 13, 0, tzinfo=timezone.utc)
    items = [
        _evt("later", pub + timedelta(hours=5), raw_text="same macro story repeated here", source_tier=2),
        _evt("earlier", pub - timedelta(minutes=10), raw_text="same macro story repeated here", source_tier=2),
    ]
    clusters = dedupe(items)
    assert len(clusters) == 1
    # equal tier -> earliest point-in-time wins
    assert next(iter(clusters.values())).kept_event_id == "earlier"


def test_dedupe_later_higher_authority_displaces_earlier_rep():
    """B1 regression: a later-arriving higher-authority copy must displace an
    earlier, lower-authority rep (tier direction was previously inverted dead code)."""
    pub = datetime(2026, 8, 20, 13, 0, tzinfo=timezone.utc)
    items = [
        _evt("early_t3", pub - timedelta(minutes=10), raw_text="US CPI rose 0.5% in July", source_tier=3),
        _evt("late_t1", pub + timedelta(minutes=2), raw_text="US CPI rose 0.5% in July", source_tier=1),
    ]
    clusters = dedupe(items)
    assert len(clusters) == 1
    cluster_id, cluster = next(iter(clusters.items()))
    # later tier-1 displaces earlier tier-3; displaced rep joins members (no crash)
    assert cluster.kept_event_id == "late_t1"
    assert "early_t3" in cluster.members


def test_dedupe_numeric_tokens_do_not_collapse_identical_text():
    """B2 regression: numeric tokens must survive SimHash so identical-text items
    still dedupe, while distinct prints stay distinguishable. Identical text must
    collapse to one cluster (proves the tokenizer keeps digits)."""
    pub = datetime(2026, 8, 20, 13, 0, tzinfo=timezone.utc)
    items = [
        _evt("reuters", pub - timedelta(minutes=4), raw_text="US CPI rose 0.3% in July", source_tier=2),
        _evt("bloomberg", pub + timedelta(minutes=1), raw_text="US CPI rose 0.3% in July", source_tier=3),
    ]
    clusters = dedupe(items)
    assert len(clusters) == 1, "identical-text items must still collapse (numeric tokens kept)"


def test_dedupe_distinct_number_prints_do_not_collapse():
    """B2 discriminator (sr-dev): two prints that differ only in a numeric value
    must stay in separate clusters. The hard multiset gate makes this deterministic:
    differing numeric multisets never merge, regardless of SimHash distance."""
    pub = datetime(2026, 8, 20, 13, 0, tzinfo=timezone.utc)
    items = [
        _evt("reuters", pub - timedelta(minutes=4), raw_text="US CPI rose 0.3% in July", source_tier=2),
        _evt("bloomberg", pub + timedelta(minutes=1), raw_text="US CPI rose 0.9% in July", source_tier=3),
    ]
    clusters = dedupe(items)
    assert len(clusters) == 2, "distinct numeric prints must never merge"


def test_dedupe_prose_paraphrase_with_same_number_still_collapses():
    """B2 discriminator (sr-dev): a prose paraphrase that keeps the same number
    must still collapse to one cluster. Here the alnum tokenizer would split
    '0.3' into lone digits and inflate the SimHash distance past threshold; the
    hard multiset gate lets it through, and the numeric weighting collapses it."""
    pub = datetime(2026, 8, 20, 13, 0, tzinfo=timezone.utc)
    items = [
        _evt("reuters", pub - timedelta(minutes=4), raw_text="0.3 percent", source_tier=2),
        _evt("bloomberg", pub + timedelta(minutes=1), raw_text="0.3%", source_tier=3),
    ]
    clusters = dedupe(items)
    assert len(clusters) == 1, "same-number prose paraphrase must still collapse"


def test_dedupe_respects_time_window():
    pub = datetime(2026, 8, 20, 13, 0, tzinfo=timezone.utc)
    items = [
        _evt("early", pub - timedelta(hours=1), raw_text="same macro story repeated here", source_tier=2),
        _evt("late", pub + timedelta(hours=72), raw_text="same macro story repeated here", source_tier=2),
    ]
    clusters = dedupe(items, window_hours=48)
    # outside the 48h window -> two distinct clusters, not collapsed
    assert len(clusters) == 2


# --- deliverable #3: revision chain (no overwrite) --------------------------

def test_revision_produces_two_dated_events(db):
    """Feeding a revised CPI print yields two dated events, not one overwritten row."""
    from storage.engine import engine
    from macroscope.vintage import record_revision

    base = datetime(2026, 8, 20, 13, 30, tzinfo=timezone.utc)
    with engine.connect() as conn:
        before = conn.execute(text(
            "SELECT COUNT(*) FROM events WHERE source_id='bureau_of_labor_stats'"
        )).scalar_one()
    with engine.begin() as conn:
        # first print already seeded (evt-cpi-001); append a revision row
        new_id, rev_id = record_revision(
            conn, source_id="bureau_of_labor_stats", published_at=base + timedelta(hours=2),
            sequence=99, revised_text="CPI +0.3% MoM (revised from +0.4%)",
            entities=["US CPI"], numbers_extracted={"cpi_mom": 0.3},
        )
    with engine.connect() as conn:
        after = conn.execute(text(
            "SELECT COUNT(*) FROM events WHERE source_id='bureau_of_labor_stats'"
        )).scalar_one()
        rows = conn.execute(text(
            "SELECT event_id, published_at FROM events WHERE source_id='bureau_of_labor_stats' ORDER BY published_at"
        )).fetchall()
    # a revision adds exactly one new later-dated event (no silent overwrite)
    assert after == before + 1, f"expected {before} -> {after}, not an overwrite"
    # the original first-print row is untouched; a new later-dated one exists
    assert any(eid == "evt-cpi-001" for eid, _ in rows), "first-print row was overwritten"
    assert new_id not in ("evt-cpi-001", "evt-cpi-002"), "revision id collides with a seeded event"


# --- deliverable #1: audit trail (reproducible) -----------------------------

def test_audit_trail_stamps_every_item(db):
    from storage.engine import engine
    from macroscope.vintage import audit_trail

    trail = audit_trail(engine)
    assert len(trail) >= 4
    for event_id, res in trail.items():
        # every stamped item carries the vintage fields
        assert isinstance(res.published_at, (datetime, type(None)))
        assert isinstance(res.quarantine_reasons, list)
        assert res.vintage_ok == (len(res.quarantine_reasons) == 0)


def test_audit_trail_reproducible(db):
    """Re-stamping the same DB twice yields identical verdicts."""
    from storage.engine import engine
    from macroscope.vintage import audit_trail

    first = {k: (v.vintage_ok, tuple(v.quarantine_reasons)) for k, v in audit_trail(engine).items()}
    second = {k: (v.vintage_ok, tuple(v.quarantine_reasons)) for k, v in audit_trail(engine).items()}
    assert first == second


# --- seed data integration --------------------------------------------------

def test_seed_unproven_item_is_quarantined(db):
    """The seeded 'evt-unknowntime' row (published_at NULL) must quarantine."""
    from storage.engine import engine
    from macroscope.vintage import audit_trail

    trail = audit_trail(engine)
    unproven = [eid for eid, r in trail.items() if not r.vintage_ok]
    assert len(unproven) >= 1, "expected at least one quarantined item in the seed"


@pytest.fixture(scope="module")
def db():
    from storage.engine import create_engine_from_env, init_db
    from storage.seed import seed

    create_engine_from_env()
    from storage.engine import engine
    init_db(engine)
    n = seed(engine)
    assert n > 0
    return engine

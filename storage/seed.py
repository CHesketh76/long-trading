"""SQLite-backed dev seed so tests run without Postgres (T-001).

Populates a small but representative dataset covering every table, including the
vintage-relevant cases T-002 needs to exercise:
  * a macro-release first-print + revision chain (two dated events, no overwrite)
  * near-duplicate items across outlets for dedupe testing
  * an unproven-vintage item that should land in quarantine
  * a source_registry with T1/T2 tiers baked in

Run via: python -m storage.seed
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, text


def _sha(text_: str) -> str:
    return hashlib.sha256(text_.encode()).hexdigest()[:16]


SEED_SQL = [
    # --- source_registry (T1 authoritative, T2 lower weight) ---
    """INSERT INTO source_registry (source_id, name, type, cadence, tier, url_template, config)
       VALUES ('reuters', 'Reuters', 'news', 'continuous', 0.80, NULL, '{"auth": "env:REUTERS_KEY"}')""",
    """INSERT INTO source_registry (source_id, name, type, cadence, tier, url_template, config)
       VALUES ('bureau_of_labor_stats', 'BLS', 'official', 'scheduled', 1.00, NULL, '{}')""",
    """INSERT INTO source_registry (source_id, name, type, cadence, tier, url_template, config)
       VALUES ('fomc', 'Federal Reserve FOMC', 'official', '~8wks', 1.00, NULL, '{}')""",
    """INSERT INTO source_registry (source_id, name, type, cadence, tier, url_template, config)
       VALUES ('fred', 'FRED / Treasury', 'structured', 'daily', 1.00, NULL, '{}')""",
]


def seed(engine) -> int:
    """Populate a fresh dev DB with the sample dataset. Returns row count."""
    from .engine import reset_dev_db

    reset_dev_db(engine)
    base = datetime(2026, 8, 20, 13, 30, tzinfo=timezone.utc)

    with engine.begin() as conn:
        for stmt in SEED_SQL:
            conn.execute(text(stmt))

        # --- events: vintage-relevant rows ---
        # Each dict is keyed by column so layout can't drift. retrieved_at is
        # the Macroscope ingest time (UTC); here it's "now" for all seeded rows.
        now = datetime(2026, 8, 20, 14, 0, tzinfo=timezone.utc)
        events = [
            dict(
                event_id="evt-cpi-001",
                event_ts=base,                       # first-print (CPI), T1 source
                sequence=1,
                source_id="bureau_of_labor_stats",
                published_at=base - timedelta(minutes=5),
                retrieved_at=now,
                url="https://www.bls.gov/cpi/2026-08.json",
                raw_text="CPI +0.3% MoM, +3.1% YoY",
                language="en",
                source_tier=1,
                event_type="macro_data",
                entities=["US CPI"],
                novelty_score=0.92,
                extractor_confidence=0.97,
                prompt_hash=_sha("bls-cpi-prompt"),
            ),
            dict(
                # Same CPI revised two hours later — a SEPARATE later-dated event.
                event_id="evt-cpi-002",
                event_ts=base + timedelta(hours=2),
                sequence=2,
                source_id="bureau_of_labor_stats",
                published_at=base + timedelta(hours=2),
                retrieved_at=now,
                url="https://www.bls.gov/cpi/2026-08.json",
                raw_text="CPI +0.3% MoM (revised from +0.4%), +3.1% YoY",
                language="en",
                source_tier=1,
                event_type="macro_data",
                entities=["US CPI"],
                novelty_score=0.95,
                extractor_confidence=0.97,
                prompt_hash=_sha("bls-cpi-prompt"),
            ),
            dict(
                # Near-duplicate of the first print from a T2 outlet (dedupe target).
                event_id="evt-cpi-003",
                event_ts=base + timedelta(minutes=1),
                sequence=1,
                source_id="reuters",
                published_at=base - timedelta(minutes=4),
                retrieved_at=now,
                url="https://www.reuters.com/markets/cpi-2026",
                raw_text="US CPI rose 0.3% in July",
                language="en",
                source_tier=2,
                event_type="macro_data",
                entities=["US CPI"],
                novelty_score=0.70,
                extractor_confidence=0.85,
                prompt_hash=None,
            ),
            dict(
                # Unproven vintage: published_at missing → quarantine candidate.
                event_id="evt-unknowntime",
                event_ts=base + timedelta(hours=1),
                sequence=3,
                source_id="reuters",
                published_at=None,
                retrieved_at=now,
                url="https://www.reuters.com/markets/unknown",
                raw_text="Some market move with no stated release time",
                language="en",
                source_tier=2,
                event_type="market_move",
                entities=[],
                novelty_score=None,
                extractor_confidence=None,
                prompt_hash=None,
            ),
        ]

        for e in events:
            conn.execute(text("""INSERT INTO events (
                event_id, event_ts, sequence, source_id, published_at, retrieved_at,
                url, raw_text, language, source_tier, event_type, entities,
                direction_assertions, numbers_extracted, novelty_score,
                extractor_confidence, prompt_hash
            ) VALUES (:event_id, :event_ts, :sequence, :source_id, :published_at,
                      :retrieved_at, :url, :raw_text, :language, :source_tier,
                      :event_type, :entities, :direction_assertions,
                      :numbers_extracted, :novelty_score, :extractor_confidence,
                      :prompt_hash)"""), {
                **e,
                "direction_assertions": json.dumps(e.get("direction_assertions", [])),
                "numbers_extracted": json.dumps(e.get("numbers_extracted", {})),
                "entities": json.dumps(e.get("entities", [])),
            })

        # --- event_revisions: first-print + revision chain (no overwrite) ---
        conn.execute(text("""INSERT INTO event_revisions
            (event_id, revision_at, first_print, revision_jsonb)
            VALUES (:eid, :rev, :fp, :json)"""), [
            dict(eid="evt-cpi-001", rev=base.isoformat(), fp=True,
                 json='{"is_revision": false, "diff": null}'),
            dict(eid="evt-cpi-002", rev=(base + timedelta(hours=2)).isoformat(),
                 fp=False,
                 json='{"is_revision": true, "diff": {"numbers_extracted.cpi_mom": "+0.4 -> +0.3"}}'),
        ])

        # --- theses ---
        conn.execute(text("""INSERT INTO theses (thesis_id, ticker, action, conviction,
            projected_hold_days, status, created_at, updated_at)
            VALUES (:id, :ticker, :action, :conviction, :hold, :status, :created, :updated)"""),
            dict(thesis_id="ths-001", ticker="GC", action="long", conviction=0.78,
                 projected_hold_days=63, status="under_review",
                 created=base.isoformat(), updated=base.isoformat()))

        # --- decisions ---
        conn.execute(text("""INSERT INTO decisions (decision_id, thesis_id, human_decision,
            reason, edited_params, at) VALUES (:id, :tid, :dec, :reason, :params, :at)"""),
            dict(decision_id="dec-001", thesis_id="ths-001", human_decision="modify",
                 reason="Trim conviction to 0.70; hold 42d given regime gate.",
                 edited_params={"conviction": 0.70, "projected_hold_days": 42},
                 at=base.isoformat()))

    return len(events) + 1


def main() -> None:
    from .engine import create_engine_from_env, init_db

    create_engine_from_env()
    from .engine import engine  # set by create_engine_from_env above

    init_db(engine)
    n = seed(engine)
    print(f"Seeded dev DB with {n} events (+ revisions, theses, decisions).")


if __name__ == "__main__":
    main()

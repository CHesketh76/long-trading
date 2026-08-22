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
        events = [
            # Macro release first-print (CPI), T1 source.
            ("evt-cpi-001", base, 1, "bureau_of_labor_stats",
             base - timedelta(minutes=5), "https://www.bls.gov/cpi/2026-08.json",
             "CPI +0.3% MoM, +3.1% YoY", "en", 1, "macro_data",
             ["US CPI"], [], {"cpi_mom": 0.3, "cpi_yoy": 3.1}, 0.92, 0.97, _sha("bls-cpi-prompt")),
            # Same CPI revised two hours later — a SEPARATE later-dated event.
            ("evt-cpi-002", base + timedelta(hours=2), 2, "bureau_of_labor_stats",
             base + timedelta(hours=2), "https://www.bls.gov/cpi/2026-08.json",
             "CPI +0.3% MoM (revised from +0.4%), +3.1% YoY", "en", 1, "macro_data",
             ["US CPI"], [], {"cpi_mom": 0.3}, 0.95, 0.97, _sha("bls-cpi-prompt")),
            # Near-duplicate of the first print from a T2 outlet (dedupe target).
            ("evt-cpi-003", base + timedelta(minutes=1), 1, "reuters",
             base - timedelta(minutes=4), "https://www.reuters.com/markets/cpi-2026",
             "US CPI rose 0.3% in July", "en", 0.80, "macro_data",
             ["US CPI"], [], {"cpi_mom": 0.3}, 0.70, 0.85, None),
            # Unproven vintage: published_at missing → quarantine candidate.
            ("evt-unknowntime", base + timedelta(hours=1), 3, "reuters",
             base, "https://www.reuters.com/markets/unknown",
             "Some market move with no stated release time", "en", 0.80, "market_move",
             [], [], {}, None, None, None),
        ]

        conn.executemany(
            text("""INSERT INTO events (
                event_id, event_ts, sequence, source_id, published_at, retrieved_at,
                url, raw_text, language, source_tier, event_type, entities,
                direction_assertions, numbers_extracted, novelty_score,
                extractor_confidence, prompt_hash
            ) VALUES (:event_id, :event_ts, :sequence, :source_id, :published_at,
                      :retrieved_at, :url, :raw_text, :language, :source_tier,
                      :event_type, :entities, :direction_assertions,
                      :numbers_extracted, :novelty_score, :extractor_confidence,
                      :prompt_hash)"""),
            [
                dict(
                    event_id=e[0],
                    event_ts=e[1].isoformat(),
                    sequence=e[2],
                    source_id=e[3],
                    published_at=e[4].isoformat(),
                    retrieved_at=e[5].isoformat(),
                    url=e[6] or None,
                    raw_text=e[7],
                    language=e[8],
                    source_tier=e[9],
                    event_type=e[10],
                    entities=None,
                    direction_assertions=None,
                    numbers_extracted=None,
                    novelty_score=e[13],
                    extractor_confidence=e[14],
                    prompt_hash=e[15],
                )
                for e in events
            ],
        )

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
    init_db(engine)
    n = seed(engine)
    print(f"Seeded dev DB with {n} events (+ revisions, theses, decisions).")


if __name__ == "__main__":
    main()

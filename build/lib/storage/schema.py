"""Storage schema for Macroscope (T-001).

Postgres tables with a Parquet seam on object storage for price/series history.
The vintage layer (T-002) joins on the `event_ts` + `sequence` columns, so those
are first-class, indexed, and explicitly documented here rather than bolted on.

Tables:
  events            — extracted event objects (one row per first-print / revision)
  event_revisions   — provenance chain for macro releases (first-print + revisions)
  theses            — macro thesis objects
  decisions         — human decisions on theses
  source_registry   — ingestion source catalog with tier weights

Vintage discipline baked in:
  * `event_ts` is the point-in-time key every vintage query joins on.
  * `sequence` is a monotonically increasing per-source ordering counter so that
    revisions and same-day events can be reconstructed in true chronological order.
  * Macro releases are stored as first-print + revision chain — no silent overwrite.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Postgres DDL (authoritative). Mirrored by SQLAlchemy Core metadata in
# engine.py so the same schema works on SQLite for local dev without a server.
# ---------------------------------------------------------------------------

EVENTS_COLUMNS = [
    ("event_id", "TEXT PRIMARY KEY"),
    # --- vintage join columns (T-002) ---
    ("event_ts", "TIMESTAMPTZ NOT NULL"),          # point-in-time key; vintage joins here
    ("sequence", "BIGINT NOT NULL"),               # per-source monotonic order counter
    ("source_id", "TEXT NOT NULL"),                # source_registry.source_id FK (logical)
    # --- provenance ---
    ("published_at", "TIMESTAMPTZ NOT NULL"),      # publisher-stated release time (UTC)
    ("retrieved_at", "TIMESTAMPTZ NOT NULL"),      # Macroscope ingest time (UTC)
    # --- content ---
    ("url", "TEXT"),
    ("raw_text", "TEXT"),
    ("language", "CHAR(2) DEFAULT 'en'"),
    # --- structured fields ---
    ("source_tier", "INTEGER NOT NULL CHECK (source_tier BETWEEN 1 AND 5)"),
    ("event_type", "TEXT NOT NULL"),
    ("entities", "JSONB"),
    ("direction_assertions", "JSONB"),
    ("numbers_extracted", "JSONB"),
    # --- quality ---
    ("novelty_score", "FLOAT8 CHECK (novelty_score BETWEEN 0 AND 1)"),
    ("extractor_confidence", "FLOAT8 CHECK (extractor_confidence BETWEEN 0 AND 1)"),
    # --- integrity ---
    ("prompt_hash", "TEXT"),
]

EVENT_REVISIONS_COLUMNS = [
    ("event_id", "TEXT NOT NULL REFERENCES events(event_id) ON DELETE CASCADE"),
    ("revision_at", "TIMESTAMPTZ NOT NULL"),        # when this revision was published (UTC)
    ("first_print", "BOOLEAN NOT NULL DEFAULT FALSE"),  # True for the original first print
    ("revision_jsonb", "JSONB"),                     # full diff / corrected fields
]

THESIS_COLUMNS = [
    ("thesis_id", "TEXT PRIMARY KEY"),
    ("ticker", "TEXT NOT NULL"),
    ("action", "TEXT NOT NULL"),
    ("conviction", "FLOAT8 NOT NULL CHECK (conviction BETWEEN 0 AND 1)"),
    ("projected_hold_days", "INTEGER NOT NULL CHECK (projected_hold_days > 0)"),
    ("status", "TEXT NOT NULL DEFAULT 'draft'"),
    ("created_at", "TIMESTAMPTZ NOT NULL"),
    ("updated_at", "TIMESTAMPTZ NOT NULL"),
]

DECISION_COLUMNS = [
    ("decision_id", "TEXT PRIMARY KEY"),
    ("thesis_id", "TEXT NOT NULL REFERENCES theses(thesis_id) ON DELETE CASCADE"),
    ("human_decision", "TEXT NOT NULL"),
    ("reason", "TEXT"),
    ("edited_params", "JSONB"),
    ("at", "TIMESTAMPTZ NOT NULL"),
]

SOURCE_REGISTRY_COLUMNS = [
    ("source_id", "TEXT PRIMARY KEY"),
    ("name", "TEXT NOT NULL"),
    ("type", "TEXT NOT NULL"),
    ("cadence", "TEXT"),
    ("tier", "FLOAT8 NOT NULL CHECK (tier BETWEEN 0 AND 1)"),
    ("url_template", "TEXT"),
    ("config", "JSONB"),
]


# Indexes that make the vintage join fast. These are what T-002 relies on for
# point-in-time reconstruction — documented explicitly, not an afterthought.
EVENTS_INDEXES = [
    # The primary vintage join key: everything reconstructs by event_ts.
    "CREATE INDEX idx_events_event_ts ON events (event_ts)",
    # Per-source ordering so revisions / same-day events sort correctly.
    "CREATE INDEX idx_events_source_seq ON events (source_id, sequence)",
    # Vintage quarantine lookups: items missing published_at are unprovable.
    "CREATE INDEX idx_events_published_at ON events (published_at) WHERE published_at IS NOT NULL",
    # Dedupe cluster + idempotency support for T-003 adapters.
    "CREATE UNIQUE INDEX idx_events_idempotent ON events (source_id, published_at, url) WHERE url IS NOT NULL",
]

EVENT_REVISIONS_INDEXES = [
    "CREATE INDEX idx_event_revisions_event ON event_revisions (event_id)",
    "CREATE INDEX idx_event_revisions_rev_at ON event_revisions (revision_at)",
]


def _render_table(name: str, columns) -> str:
    header = f"CREATE TABLE IF NOT EXISTS {name} ("
    body = ",\n        ".join(f"{c} {t}" for c, t in columns)
    return f"{header}\n        {body}\n    )"


SCHEMA_DDL_STATEMENTS = [
    _render_table("events", EVENTS_COLUMNS),
    _render_table("event_revisions", EVENT_REVISIONS_COLUMNS),
    _render_table("theses", THESIS_COLUMNS),
    _render_table("decisions", DECISION_COLUMNS),
    _render_table("source_registry", SOURCE_REGISTRY_COLUMNS),
]

SCHEMA_INDEX_STATEMENTS = EVENTS_INDEXES + EVENT_REVISIONS_INDEXES


def events_table_ddl() -> str:
    """Return the CREATE TABLE statement for `events` (with rationale comments)."""
    lines = ["CREATE TABLE IF NOT EXISTS events ("]
    last = len(EVENTS_COLUMNS) - 1
    for i, (col, typ) in enumerate(EVENTS_COLUMNS):
        comment = _event_col_comment(col)
        comma = "," if i < last else ""
        suffix = f"  -- {comment}" if comment else ""
        lines.append(f"    {col} {typ}{comma}{suffix}")
    lines.append(")")
    return "\n".join(lines)


def _event_col_comment(col: str) -> str:
    """Brief rationale for each events column (for DDL comments)."""
    return {
        "event_id": "primary key",
        "event_ts": "VINTAGE JOIN KEY — point-in-time reconstruction timestamp (UTC)",
        "sequence": "per-source monotonic order counter for revision ordering",
        "source_id": "FK to source_registry.source_id",
        "published_at": "publisher-stated release time (UTC); quarantine if missing",
        "retrieved_at": "Macroscope ingest time (UTC)",
        "url": "canonical source URL; part of idempotency key",
        "raw_text": "verbatim source text",
        "language": "ISO-639-1 language code",
        "source_tier": "1..5 tier weight (T1=1.0 authoritative)",
        "event_type": "coarse event bucket",
        "entities": "resolved entity list (JSONB)",
        "direction_assertions": "asset→direction mappings (JSONB)",
        "numbers_extracted": "structured numeric facts (JSONB)",
        "novelty_score": "0..1 novelty signal",
        "extractor_confidence": "0..1 extraction confidence",
        "prompt_hash": "SHA-256 of extraction prompt where LLM extraction applies",
    }.get(col, "")

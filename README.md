# Macroscope (`long-trading`)

Advisory macro thesis engine — design-doc **v0.1**. The engine writes reports; it
never places an order (design-doc §9, §10, §12, §13).

## Phase 0 Foundation

| Ticket | Owner | Status |
|--------|-------|--------|
| T-001 Repo scaffold + storage schema | coder / sr-dev | In Progress |
| T-002 Vintage / point-in-time tagging layer | coder / sr-dev | To Do |
| T-003 Source registry + ingestion adapters #1–7,13 | coder / sr-dev | To Do |

Board index: [`tickets/README.md`](tickets/README.md). Every card runs
**Coder → sr-dev gate** before it counts *Done*.

## Repo layout

```
macroscope/     core package (Pydantic models mirroring design-doc §5)
ingestion/      read-only source adapters (T-003)
storage/        schema + engine + dev seed (T-001)
signals/        versioned signal objects (§5.2)
reporting/      fixed 12-section memo generator (§9)
tests/          acceptance tests
```

## Storage schema (T-001)

Postgres is primary; a Parquet seam on object storage is reserved for price/series
history. The same schema runs on SQLite for local dev without a server.

| Table | Purpose |
|-------|---------|
| `events` | One row per first-print or revision — **no silent overwrite** |
| `event_revisions` | Provenance chain: first-print + revision chain |
| `theses` | Macro thesis objects (ticker, action, conviction, hold days) |
| `decisions` | Human decisions on theses |
| `source_registry` | Ingestion source catalog with tier weights |

### Vintage join columns (`events`)

These are first-class, indexed, and explicitly documented — not bolted on. The
T-002 vintage layer joins on them for point-in-time reconstruction:

| Column | Type | Role |
|--------|------|------|
| `event_ts` | `TIMESTAMPTZ NOT NULL` | **Point-in-time key** every vintage query joins on |
| `sequence` | `BIGINT NOT NULL` | Per-source monotonic order counter for revision ordering |
| `published_at` | `TIMESTAMPTZ` (nullable) | Publisher-stated release time (UTC); **NULL = unprovable → quarantine** |
| `retrieved_at` | `TIMESTAMPTZ NOT NULL` | Macroscope ingest time (UTC) |

Macro releases are stored as first-print + revision chain — a revised CPI print
produces two dated events, never one overwritten row. See `storage/schema.py`.

## Setup

```bash
# Create and activate a venv (Python 3.12+)
python -m venv .venv && source .venv/bin/activate

# Install deps + dev tools
pip install -e ".[dev]"
```

### Point at Postgres (production)

```bash
export POSTGRES_URL="postgresql+psycopg2://user:pass@host:5432/macroscope"
python -m storage.seed   # seed the dev dataset
pytest                   # run acceptance tests against it
```

### SQLite dev mode (default, no server needed)

Just unset `POSTGRES_URL` and run — a local `.dev/macroscope_dev.sqlite` is used:

```bash
unset POSTGRES_URL
python -m storage.seed
pytest
```

## Tests

```bash
pytest            # T-001 acceptance tests against seeded SQLite dev DB
```

Covers: table existence, vintage join columns present (`event_ts`, `sequence`),
revision chain (two dated events, no overwrite), source-tier weights, and Pydantic
validation of the EventObject model.

## Conventions

- No hardcoded secrets — `.env` only (gitignored). Config via env / registry table.
- Numeric fields typed; no free-form blobs where structured types exist.
- Vintage discipline baked into schema: revisions present, no silent overwrite.
- Read-only ingestion; adapters return EventObject-shaped rows with tier metadata.

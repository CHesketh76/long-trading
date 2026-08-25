# Board — Macroscope (long-trading)

Epic = design-doc phase. Every feature card runs **Coder → sr-dev gate** before it counts *Done*.
Nothing ships raw from Coder; sr-dev signs off on architecture/security/scalability first.

## Columns
`To Do` → `In Progress` → `SR-Dev Review` → `Done`

## Ticket index
| ID | Epic (phase) | Card | Owner | Status |
|----|--------------|------|-------|--------|
|| T-001 | Phase 0 — Foundation | Repo scaffold + storage schema | coder / sr-dev | Done |
|| T-002 | Phase 0 — Foundation | Vintage / point-in-time tagging layer | coder / sr-dev | Done (B1/B2 gate cleared @sr-dev) |
|| T-003 | Phase 0 — Foundation | Source registry + ingestion adapters #1–7,13 | coder / sr-dev | In Progress (coder pulling; unlocked by T-002) |

### Epic: Backtesting & Monte Carlo (user-prioritized)
| ID | Epic | Card | Owner | Status |
|----|------|------|-------|--------|
|| T-010 | Backtest | Engine core + walk-forward harness | coder / sr-dev | Done (shipped @ad0dcde) |
|| T-011 | Backtest | Baseline strategies (buy & hold, momentum, random) | coder / sr-dev | Done (shipped @ad0dcde) |
|| T-012 | Backtest | No-cheating / lookahead filter (INTEGRITY GATEKEEPER) | coder / sr-dev | Done (shipped @ad0dcde) |
|| T-013 | Backtest | Performance metrics + Buy/Hold/Sell verdict in reports | coder / sr-dev | Done (shipped @ad0dcde) |
|| T-014 | Backtest | Monte Carlo simulation engine | coder / sr-dev | To Do |

Full breakdown: `tickets/EPIC-backtest.md`. User's spec: 5y window (3y train / 2y test), buy & hold per-name baseline, no-cheating filter mandatory, final Buy/Hold/Sell verdict in reports.

Docs lane (tech-writer): one doc card per feature card that hits Done; nothing marked *Synced*
until code and docs are byte-aligned. `docs/architecture.md` (§3 Mermaid) already shipped.

# Macroscope — Dev Loop Report

**Generated:** 2026-08-24 (EDT) · **Repo:** `CHesketh76/long-trading` · **Remote sync:** `origin/main` = `74740bc` ✓

## Board state

| Ticket | Status | Notes |
|---|---|---|
| T-001 storage schema (point-in-time columns) | ✅ Done | `event_ts` primary vintage key; `published_at` nullable → quarantine; sr-dev gate cleared |
| T-002 vintage / point-in-time tagging layer | ✅ Done (gate cleared at `74740bc`) | SimHash dedupe + hard numeric-multiset gate; revision chain; quarantine bucket |
| T-003 ingestion adapters | 🔓 Unlocked (next up) | Gated on T-002, now clear |
| T-010→T-014 backtest epic | ⏸ Parked | Engine, baselines, no-cheat gatekeeper, metrics+verdict, Monte Carlo — post-Phase-0 |

## What shipped this loop

- **T-002 dedupe correctness (B1+B2).** B1: tier-aware keep-selection now compares against the current kept rep (dead self-comparison removed). B2: numeric tokens float-canonicalized (`0.3` ≡ `0.30`) and ×4-weighted in the SimHash register, plus a deterministic hard gate — differing numeric multisets never merge. `"US CPI rose 0.3%"` vs `"0.9%"` → 2 clusters; `"0.3 percent"` vs `"0.3%"` → 1 cluster.
- **Suite health:** 23/23 tests green (8 T-001 + 13 T-002 + 2 B2 discriminators), seed clean.
- **Repo hygiene:** scratch `_measure*`/`_repro*` files removed and gitignored (`238ac36`).

## Root cause of the stall (fixed, do not re-litigate)

Bots' shells get a **sandboxed HOME**, so `gh`/`git` can't see the keyring login that lives in the real user home. Fix is one line before any push:

```bash
export HOME=/home/garebear && gh auth setup-git && git push origin main
```

Credentials stay in the keyring — never signed out, never deleted.

## Next

1. T-003 ingestion adapters (coder) → sr-dev acceptance → push.
2. tech-writer mirrors the §11 report template once `reporting/` produces real output (T-013).
3. Backtest epic (T-010→T-014) scoping when the user is ready.

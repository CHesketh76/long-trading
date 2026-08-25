# Macroscope — Dev Loop Report

**Generated:** 2026-08-24 (EDT) · **Repo:** `CHesketh76/long-trading` · **Remote sync:** `origin/main` current ✓

## Board state

| Ticket | Status | Notes |
|---|---|---|
| T-001 storage schema (point-in-time columns) | ✅ Done | `event_ts` primary vintage key; `published_at` nullable → quarantine; sr-dev gate cleared |
| T-002 vintage / point-in-time tagging layer | ✅ Done | SimHash dedupe + hard numeric-multiset gate; revision chain; quarantine bucket |
| T-003 ingestion adapters | 🔓 Unlocked (next up) | Gated on T-002, now clear |
| T-010→T-014 backtest epic | ▶ Active per @user 2026-08-24 | Engine, baselines, no-cheat gatekeeper, metrics+verdict, Monte Carlo |

## Trading performance vs Buy & Hold baseline

**Method:** daily adjusted closes (dividends reinvested), `yfinance`. 5-year window ending 2026-08-21, split into 3y train (753 rows) / 2y test (501 rows) per @user's spec. Buy & hold = enter at window open, hold to window end. Sharpe uses rf = 0. This is the reference line every future strategy must beat.

| Ticker | Window | Total ret | CAGR | Ann. vol | Max DD | Sharpe |
|---|---|---|---|---|---|---|
| SPY | train 21-24 | +30.6% | 9.3% | 17.6% | −24.5% | 0.60 |
| SPY | test 24-26 | +39.3% | 18.1% | 16.7% | −18.8% | 1.08 |
| GLD | train 21-24 | +37.8% | 11.3% | 14.2% | −21.0% | 0.83 |
| GLD | test 24-26 | +78.9% | 34.0% | 23.8% | −26.4% | 1.35 |
| NEM | train 21-24 | −0.3% | −0.1% | 34.9% | −62.4% | 0.17 |
| NEM | test 24-26 | +154.1% | 59.8% | 44.2% | −36.6% | 1.29 |
| VRT | train 21-24 | +181.0% | 41.3% | 61.4% | −71.2% | 0.88 |
| VRT | test 24-26 | +240.2% | 85.1% | 67.2% | −61.3% | 1.26 |
| XOM | train 21-24 | +133.2% | 32.8% | 27.8% | −20.5% | 1.16 |
| XOM | test 24-26 | +55.6% | 24.9% | 24.8% | −20.1% | 1.02 |

**Strategy column: pending.** No strategy returns yet — the signal engine (T-010) doesn't exist. This table gains a `strategy vs baseline` column (excess return, alpha) the moment T-010/T-011 ship; baseline rows above are final and will not change.

## What shipped this loop

- **T-002 dedupe correctness (B1+B2).** B1: tier-aware keep-selection compares against the current kept rep. B2: numeric tokens float-canonicalized (`0.3` ≡ `0.30`), ×4-weighted in SimHash, plus deterministic hard gate — differing numeric multisets never merge. 23/23 tests green, sr-dev gate cleared.
- **Repo hygiene:** scratch `_measure*`/`_repro*` files removed and gitignored.
- **Auth at the root:** repo-level credential helper in `.git/config` — plain `git push` now works from any bot shell, no exports.

## Next

1. T-003 ingestion adapters (coder) → sr-dev acceptance → push.
2. Backtest epic (T-010 engine → T-011 baselines → T-012 no-cheat gate → T-013 metrics/verdict → T-014 Monte Carlo) — now the priority lane per @user.
3. Report gains strategy-vs-baseline comparison once T-010/T-011 output exists.

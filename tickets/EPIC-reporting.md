# Epic: Reporting & Portfolio Analytics

**Requested by @user:** "continue developing and building performance reports on our strategy vs buy&hold."

## Context
T-015 shipped with honest single-name numbers (GC=F edge −24.8%, NEM −107% vs buy & hold); the
trend-only filter doesn't beat buy & hold in this regime yet — that is a *signal* problem, separate
from reporting. This epic is the *reporting* half: make strategy-vs-buy&hold visible across the
whole pilot universe and at portfolio level, with walk-forward stability, so @user can judge the
strategy at a glance. Unblocked by the T-015 signal-direction fork.

## User requirements (authoritative)
- Strategy vs buy & hold for EVERY name in one view (not one run per symbol).
- Portfolio-level aggregate: our strategy as one series vs SPY buy & hold.
- Stability across regimes, not a single lucky 3y/2y split.
- Same no-cheating / point-in-time discipline as the backtest epic (T-012).

## Tickets
| ID | Card | Owner | Status |
|----|------|-------|--------|
| T-016 | Batch multi-name runner + cross-name table | coder / sr-dev | To Do |
| T-017 | Portfolio-level aggregate (strategy series vs SPY B&H) | coder / sr-dev | To Do |
| T-018 | Walk-forward multi-window stability (per-year edge, hit rate) | coder / sr-dev | To Do |

## Dependencies
- All depend on the shipped backtest epic (T-010/011/012/013/014).
- T-017 consumes T-016's per-name equity curves — keep output shape stable.
- Independent of the T-015 signal-direction fork; sequence in parallel with strategy work.

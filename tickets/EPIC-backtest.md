# Epic: Backtesting & Monte Carlo (user-prioritized)

**Requested by @user.** Design-doc §14, expanded with user's specific asks.

## User requirements (authoritative)
- **Horizon:** past 5 years total; recent 2 years = test set, earlier ~3y = train/walk-forward window.
- **Baseline for every name:** buy & hold on that stock/future — this is THE comparison point.
- **No-cheating filter (mandatory):** filtering logic so the algorithm cannot cheat — no lookahead, no survivorship bias, signals must be generated at decision time t using only info available at t.
- **Reports carry a final Buy/Hold/Sell verdict** at the end (drives model scoring).
- **Monte Carlo simulation** to judge performance robustness (confidence intervals on metrics).
- User expects MANY tickets for this — see breakdown below.

## Tickets
| ID | Card | Owner | Status |
|----|------|-------|--------|
| T-010 | Backtest engine core + walk-forward harness | coder / sr-dev | To Do |
| T-011 | Baseline strategies (buy & hold, momentum, random) | coder / sr-dev | To Do |
| T-012 | No-cheating / lookahead filter (the gating gatekeeper) | coder / sr-dev | To Do |
| T-013 | Performance metrics + Buy/Hold/Sell verdict in reports | coder / sr-dev | To Do |
| T-014 | Monte Carlo simulation engine | coder / sr-dev | To Do |

## Dependencies
- T-010 needs T-001 (schema) + price/series storage.
- T-012 is the integrity backbone — sr-dev treats it as a hard gate before any metric in T-013/T-014 is trusted.
- All depend on vintage discipline from T-002 where applicable.

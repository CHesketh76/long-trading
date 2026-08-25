# Macroscope Backtest Report — GC=F

**Generated:** 2026-08-25 14:33 UTC · **Data:** 1257 daily bars · **T-012 filter:** active (point-in-time, quarantine, survivorship)

## Verdict

**HOLD** — Mixed: positive or negative but no decisive edge vs the baseline — hold current positioning.

* Edge vs buy & hold: **-0.00%**
* Strategy total return (net, 10bps/side): **+85.79%**
* Buy & hold total return: **+85.79%**

## Performance vs buy & hold baseline

| Metric | Strategy (Momentum 12-1) | Buy & Hold |
|---|---|---|
| Total return (net) | +85.79% | +85.79% |
| CAGR | +36.39% | +36.39% |
| Sharpe (0% rf) | 1.43 | 1.43 |
| Sortino | 1.70 | 1.70 |
| Max drawdown | -25.06% | -25.06% |
| Annual vol | 23.89% | 23.89% |
| Exposure | 100% | 100% |
| Trades | 0 | 0 |
| Cost drag (10bps/side) | 0.00% | 0.00% |

## Baselines (same window, same costs)

| Strategy | Net total return | Sharpe | Max DD |
|---|---|---|---|
| **Buy & hold** | +85.79% | 1.43 | -25.06% |
| Random frequency (seed 42) | +1.40% | 0.14 | -32.50% |
| **Momentum 12-1** | +85.79% | 1.43 | -25.06% |

> Random-frequency is the sanity floor: a strategy that cannot beat a seeded
> coin flip on the same dates and costs is not adding value. Buy & hold is
> THE reference line per @user's requirement.

## Walk-forward split

* Train window: 2021-08-25 → 2024-08-25 (3y)
* Test window: 2024-08-25 → 2026-08-25 (2y)
* Execution: signal at close(t) → position held for bar t+1 (one-bar lag).
  No same-bar fill, no lookahead by construction (T-012).

## Equity curve

![Equity curve](equity_curve.svg)

## Integrity

* All metrics computed only on T-012-clean data (the engine's provider owns
  the no-lookahead cut; the cheat-detector suite in tests/test_backtest.py
  proves injected future rows are never visible).
* Cost model: 10 bps per side on turnover (design-doc §14 range 5–15).
* Time is never shuffled; walk-forward rolls yearly without overlap.

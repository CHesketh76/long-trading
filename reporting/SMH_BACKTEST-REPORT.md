# Macroscope Backtest Report — SMH

**Generated:** 2026-08-25 16:32 UTC · **Data:** 1255 daily bars · **T-012 filter:** active (point-in-time, quarantine, survivorship)

## Verdict

**HOLD** — Mixed: positive or negative but no decisive edge vs the baseline — hold current positioning.

* Edge vs buy & hold: **-4.75%**
* Strategy total return (net, 10bps/side): **+126.15%**
* Buy & hold total return: **+130.90%**

## Performance vs buy & hold baseline

| Metric | Strategy (Regime-aware (T-015)) | Buy & Hold |
|---|---|---|
| Total return (net) | +126.15% | +130.90% |
| CAGR | +50.75% | +52.33% |
| Sharpe (0% rf) | 1.38 | 1.25 |
| Sortino | 1.68 | 1.69 |
| Max drawdown | -24.62% | -32.65% |
| Annual vol | 32.90% | 38.92% |
| Exposure | 84% | 100% |
| Trades | 2 | 0 |
| Cost drag (10bps/side) | 0.20% | 0.00% |

## Baselines (same window, same costs)

| Strategy | Net total return | Sharpe | Max DD |
|---|---|---|---|
| **Buy & hold** | +130.90% | 1.25 | -32.65% |
| Random frequency (seed 42) | +126.15% | 1.38 | -24.62% |
| **Regime-aware (T-015)** | +72.45% | 0.94 | -24.62% |

> Random-frequency is the sanity floor: a strategy that cannot beat a seeded
> coin flip on the same dates and costs is not adding value. Buy & hold is
> THE reference line per @user's requirement.

## Monte Carlo (T-014) — confidence intervals

Bootstrap-resampled 1000 paths of the primary strategy's own daily net
returns (seed 42, 21-day block bootstrap: blocks preserve monthly serial
correlation, so the resampled paths stay representative of the real regime
sequence).

| Metric | P10 | P50 | P90 | Point est. (mean of paths) |
|---|---|---|---|---|
| Total return | +71.3% | +175.1% | +354.3% | +199.3% |
| CAGR | +65.21% | +94.43% | +136.65% | +98.42% |
| Sharpe | 0.99 | 1.75 | 2.58 | 1.77 |
| Max drawdown | -84.7% | -74.9% | -59.7% | -73.1% |

> P10/P50/P90 span the 10th–90th percentile across paths; point estimate is the
> mean of each distribution. A strategy that only wins in the P90 tail (not the
> median) is a lucky path, not an edge — @user's robustness requirement.
> Path drawdowns run deeper than the realized one by construction: the block
> bootstrap preserves monthly correlation but re-orders months, so a dip can
> land on a higher equity base. Read the Sharpe/return columns as the
> robustness signal; treat drawdown percentiles as an upper-bound, not a
> forecast.


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

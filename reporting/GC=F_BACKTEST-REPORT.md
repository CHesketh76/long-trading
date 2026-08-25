# Macroscope Backtest Report — GC=F

**Generated:** 2026-08-25 16:32 UTC · **Data:** 1257 daily bars · **T-012 filter:** active (point-in-time, quarantine, survivorship)

## Verdict

**HOLD** — Mixed: positive or negative but no decisive edge vs the baseline — hold current positioning.

* Edge vs buy & hold: **-25.05%**
* Strategy total return (net, 10bps/side): **+61.43%**
* Buy & hold total return: **+86.48%**

## Performance vs buy & hold baseline

| Metric | Strategy (Regime-aware (T-015)) | Buy & Hold |
|---|---|---|
| Total return (net) | +61.43% | +86.48% |
| CAGR | +27.11% | +36.64% |
| Sharpe (0% rf) | 1.16 | 1.44 |
| Sortino | 1.31 | 1.71 |
| Max drawdown | -24.97% | -25.06% |
| Annual vol | 23.10% | 23.90% |
| Exposure | 92% | 100% |
| Trades | 1 | 0 |
| Cost drag (10bps/side) | 0.10% | 0.00% |

## Baselines (same window, same costs)

| Strategy | Net total return | Sharpe | Max DD |
|---|---|---|---|
| **Buy & hold** | +86.48% | 1.44 | -25.06% |
| Random frequency (seed 42) | +61.43% | 1.16 | -24.97% |
| **Regime-aware (T-015)** | +86.48% | 1.44 | -25.06% |

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
| Total return | +12.0% | +62.0% | +129.2% | +67.4% |
| CAGR | +45.72% | +62.01% | +81.67% | +63.10% |
| Sharpe | 0.37 | 1.17 | 1.96 | 1.18 |
| Max drawdown | -71.2% | -57.1% | -39.8% | -56.1% |

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

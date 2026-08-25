# Macroscope Backtest Report — XOM

**Generated:** 2026-08-25 16:32 UTC · **Data:** 1255 daily bars · **T-012 filter:** active (point-in-time, quarantine, survivorship)

## Verdict

**HOLD** — Mixed: positive or negative but no decisive edge vs the baseline — hold current positioning.

* Edge vs buy & hold: **-28.22%**
* Strategy total return (net, 10bps/side): **+17.07%**
* Buy & hold total return: **+45.29%**

## Performance vs buy & hold baseline

| Metric | Strategy (Regime-aware (T-015)) | Buy & Hold |
|---|---|---|
| Total return (net) | +17.07% | +45.29% |
| CAGR | +8.25% | +20.67% |
| Sharpe (0% rf) | 0.52 | 0.93 |
| Sortino | 0.61 | 1.29 |
| Max drawdown | -27.70% | -20.11% |
| Annual vol | 22.14% | 24.78% |
| Exposure | 71% | 100% |
| Trades | 4 | 0 |
| Cost drag (10bps/side) | 0.40% | 0.00% |

## Baselines (same window, same costs)

| Strategy | Net total return | Sharpe | Max DD |
|---|---|---|---|
| **Buy & hold** | +45.29% | 0.93 | -20.11% |
| Random frequency (seed 42) | +17.07% | 0.52 | -27.70% |
| **Regime-aware (T-015)** | +40.90% | 0.98 | -20.11% |

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
| Total return | -34.4% | +5.9% | +69.9% | +13.2% |
| CAGR | +28.88% | +43.80% | +64.77% | +45.69% |
| Sharpe | -0.82 | 0.24 | 1.31 | 0.25 |
| Max drawdown | -78.8% | -67.1% | -50.5% | -65.5% |

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

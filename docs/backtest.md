# Macroscope Backtest Methodology

**Status:** Doc-ready (mirrors shipped code in `backtest/`)
**Last synced:** 2026-08-25 · **Source of truth:** `backtest/engine.py`, `metrics.py`, `run_report.py`, `vintage_filter.py`
**Design-doc lineage:** §14 (Backtesting & Validation Methodology), §9.3 (Anti-self-deception)

---

## 1. Purpose

The backtest layer answers one question, per @user's requirement: **does the algorithm beat buy & hold on a given instrument?** Buy & hold is the reference line for every comparison — not momentum, not a random baseline. The harness is built to say "no" honestly rather than manufacture an edge.

Run it:

```bash
source .venv/bin/activate
python -m backtest.run_report --symbol GC=F   # default; any yfinance symbol works
```

Outputs (written to `reporting/`):

| File | Kind | Purpose |
|---|---|---|
| `BACKTEST-REPORT.md` | Markdown memo | User-facing: verdict, tables, equity curve, integrity notes |
| `backtest_results.json` | Machine-readable | Full metrics per strategy + verdict dict (for downstream tooling) |
| `equity_curve.svg` | Dependency-free SVG | Strategy vs buy & hold, weekly-resampled |

## 2. Architecture

```
run_report.py  ──▶  WalkForwardEngine (engine.py)
        │                 │  strategy(hist=point-in-time history, ts) → target weight [-1,1]
        │                 │  position decided at t held during bar t+1 (one-bar lag)
        │                 ▼
        │          PointInTimeProvider (vintage_filter.py)  ← T-012 no-lookahead cut
        │
        ▼
   metrics.py  ──▶  compute_metrics() + buy_hold_sell_verdict()  ← T-013
        │
        ▼
   HEADER template → BACKTEST-REPORT.md  +  backtest_results.json
```

Three packages, one seam:

- **`backtest/strategies/`** — strategy factory functions. `buy_and_hold`, `make_momentum_12_1()`, `make_random_frequency(seed=42)`. Each returns a `Callable[[pd.DataFrame, Timestamp], float]` (target weight in [-1, 1]).
- **`backtest/engine.py`** — the simulator + walk-forward harness. Owns execution model and cost modeling.
- **`backtest/metrics.py`** — core metrics, the Buy/Hold/Sell verdict map, baseline comparison.

## 3. Execution model (engine.py)

The engine simulates bar-by-bar. Key rules that make it honest:

| Rule | Where | Why |
|---|---|---|
| Strategy sees only `history(asof=close_t)` — data ≤ current bar | `engine.run()` line 88 | No lookahead by construction |
| Position decided at `t` is held during bar `t+1` (one-bar lag) | `engine.run()` lines 96–104 | No same-bar fill; can't trade on today's close |
| Cost applied per side on turnover, default 10 bps (configurable 5–15) | `engine.run()` lines 84, 100–102 | Matches design-doc §14 cost-drag modeling |
| Time never shuffled; train→predict yearly, no overlap | `default_split()` / `walk_forward()` | Walk-forward discipline |

The engine rejects out-of-range costs at construction:

```python
if not 5.0 <= cost_bps <= 15.0:
    raise ValueError("cost_bps must be in [5, 15] per design-doc §14")
```

Two returns are tracked separately: `total_return` (gross, pre-cost) and
`net_total_return` (`bar_return`, post-cost). The report's headline numbers use the net figure.

## 4. No-lookahead guarantee (T-012)

The cheat-detector lives in `vintage_filter.py`. The engine never hands the full frame to a
strategy — only asof slices via `provider.history(ts)`. This is verified by an injected-future-row
test: if any future row ever reaches a decision, the suite fails. The report's Integrity section
cites this explicitly so reviewers can trust the numbers rather than take them on faith.

The default split (per @user's 5y / 3y-train + 2y-test spec):

```
train: 2021-08-25 → 2024-08-25 (3y)   test: 2024-08-25 → 2026-08-25 (2y)
```

Train bars give the strategy warm-up history; only the test segment is evaluated. Consecutive
walk-forward windows advance to the first bar strictly after each window's end, so no boundary
+date is shared between rolls.

## 5. Metrics (metrics.py)

`compute_metrics()` produces one `PerformanceMetrics` record per strategy over the test window:

| Field | Meaning |
|---|---|
| `total_return` | Compound net return over test window |
| `cagr` | Annualized return |
| `sharpe` | Excess-return / std, annualized (0% risk-free) |
| `sortino` | Downside-deviation variant of Sharpe |
| `max_drawdown` | Largest peak-to-trough equity drop |
| `annual_vol` | Annualized volatility |
| `turnover` | Sum of position changes |
| `cost_drag` | Total transaction cost paid |
| `win_rate` | Fraction of bars with positive gross return |
| `exposure` | Fraction of bars in a position (not flat) |
| `trades`, `n_bars` | Trade count and bar count |

## 6. Buy / Hold / Sell verdict (T-013)

The user-required report field. Deterministic mapping from edge vs buy & hold:

```python
edge = strategy.total_return - baseline.total_return
if strategy.total_return > threshold and edge > threshold:
    decision = "BUY"      # beat B&H AND made money → algorithm adds value
elif strategy.total_return < 0 and edge < -threshold:
    decision = "SELL"     # lost to B&H AND lost money → baseline was better
else:
    decision = "HOLD"     # mixed — no decisive edge, hold positioning
```

The default `edge_threshold` is **0.5%** (in `run_report.py`, passed as 0.005). A sub-threshold
edge is treated as measurement noise, not a tradable signal — so the verdict falls to HOLD instead
of a noise-BUY. The report also records a `conviction` score:

```python
min(1.0, max(0.0, 0.5 + edge + strategy.total_return / 4.0))
```

## 7. Baseline comparison

`compare_to_buy_and_hold()` aligns the strategy and buy & hold decision logs on their shared index
intersection — no date is counted for one and not the other — then computes metrics on each and the
edge between them. The report's "Baselines" table adds a seeded random-frequency strategy (seed 42)
as a sanity floor: a strategy that cannot beat a coin flip on identical dates/costs is not adding
value. Buy & hold remains THE reference line per @user's requirement.

## 8. Report template shape

`run_report.py` renders `BACKTEST-REPORT.md` from a fixed HEADER template so reports stay comparable:

1. Verdict block (edge vs B&H, strategy net return, baseline return)
2. Performance-vs-buy-and-hold table (all metrics side by side)
3. Baselines table (B&H, random-frequency, primary strategy)
4. Walk-forward split + execution notes
5. Equity curve SVG
6. Integrity section (T-012-clean data, cost model, no-shuffle guarantee)

The JSON output (`backtest_results.json`) mirrors the same verdict dict and per-strategy metrics for
downstream tooling or T-014 Monte-Carlo simulation over the label.

## 9. Reported results (GC=F, as of 2026-08-25)

Source: `reporting/BACKTEST-REPORT.md` (`ad0dcde`). Instrument GC=F gold futures, 1257 daily bars,
3y train / 2y test split.

| Strategy (test window 2024-08 → 2026-08) | Net return | Sharpe | Max DD |
|---|---|---|---|
| **Buy & hold** | +85.79% | 1.43 | -25.06% |
| Momentum 12-1 | +85.79% | 1.43 | -25.06% |
| Random frequency (seed 42) | +1.40% | 0.14 | -32.50% |

**Verdict: HOLD.** Edge vs buy & hold = −0.00%. The honest finding: in a two-year gold bull,
12-1 momentum stayed long the entire window — it *is* buy & hold minus noise. It adds no value on a
trending asset, and the random-frequency floor (+1.4%) confirms the harness discriminates rather than
flattering every strategy.

## 10. Open items / next ticket

- **Regime-aware strategy** (proposed for T-014 follow-up): long when gold is above its 200d trend
  AND real rates are falling, flat otherwise — so it can actually beat buy & hold on the down-legs.
- **Baseline-instrument consistency:** the report title uses GC=F while earlier references cited GLD;
  a ~7pp gap from roll/expense exists. The baseline must always be the same instrument the strategy
  trades, or the comparison misleads (flagged for next iteration).

---

## Sync status

- **Mirrors shipped code:** `backtest/engine.py`, `metrics.py`, `run_report.py`, `vintage_filter.py`
- **Not yet documented:** the §11 thesis-report generator (`reporting/__init__.py` is still a
  placeholder — no generator exists). Per my Synced rule, that template stays on hold until real
  report output ships.
- **Verified against:** commit `ad0dcde`, suite green (41/41 backtest tests).


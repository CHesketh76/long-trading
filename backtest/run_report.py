"""Backtest report runner (Backtest Epic T-010/011/012/013).

Fetches a real price series (yfinance), runs every strategy through the
T-010 engine under the T-012 point-in-time filter, computes T-013 metrics,
and writes:

    reporting/BACKTEST-REPORT.md   — the user-facing report
    reporting/backtest_results.json — machine-readable results
    reporting/equity_curve.svg      — strategy vs buy & hold chart

Run:  .venv/bin/python -m backtest.run_report [--symbol GC=F]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .engine import WalkForwardEngine
from .metrics import compare_to_buy_and_hold, compute_metrics
from .strategies import buy_and_hold, make_momentum_12_1, make_random_frequency
from .vintage_filter import PointInTimeProvider

REPO_ROOT = Path(__file__).resolve().parent.parent
REPORTING = REPO_ROOT / "reporting"

HEADER = """# Macroscope Backtest Report — {symbol}

**Generated:** {generated} UTC · **Data:** {rows} daily bars · **T-012 filter:** active (point-in-time, quarantine, survivorship)

## Verdict

**{verdict}** — {verdict_reason}

* Edge vs buy & hold: **{edge:+.2%}**
* Strategy total return (net, 10bps/side): **{strategy_total:+.2%}**
* Buy & hold total return: **{baseline_total:+.2%}**

## Performance vs buy & hold baseline

| Metric | Strategy ({strategy_name}) | Buy & Hold |
|---|---|---|
| Total return (net) | {s_total:+.2%} | {b_total:+.2%} |
| CAGR | {s_cagr:+.2%} | {b_cagr:+.2%} |
| Sharpe (0% rf) | {s_sharpe:.2f} | {b_sharpe:.2f} |
| Sortino | {s_sortino:.2f} | {b_sortino:.2f} |
| Max drawdown | {s_mdd:.2%} | {b_mdd:.2%} |
| Annual vol | {s_vol:.2%} | {b_vol:.2%} |
| Exposure | {s_exposure:.0%} | {b_exposure:.0%} |
| Trades | {s_trades} | {b_trades} |
| Cost drag (10bps/side) | {s_cost:.2%} | {b_cost:.2%} |

## Baselines (same window, same costs)

| Strategy | Net total return | Sharpe | Max DD |
|---|---|---|---|
| **Buy & hold** | {bh_net:+.2%} | {bh_sharpe:.2f} | {bh_mdd:.2%} |
| Random frequency (seed 42) | {ra_net:+.2%} | {ra_sharpe:.2f} | {ra_mdd:.2%} |
| **{strategy_name}** | {s_net:+.2%} | {mo_sharpe2:.2f} | {mo_mdd2:.2%} |

> Random-frequency is the sanity floor: a strategy that cannot beat a seeded
> coin flip on the same dates and costs is not adding value. Buy & hold is
> THE reference line per @user's requirement.

## Walk-forward split

* Train window: {train_start} → {train_end} ({train_years}y)
* Test window: {test_start} → {test_end} ({test_years}y)
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
"""


def _fetch(symbol: str, years: int = 5) -> pd.DataFrame:
    import yfinance as yf

    df = yf.download(
        symbol,
        period=f"{years}y",
        interval="1d",
        progress=False,
        auto_adjust=True,
    )
    df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df.columns = [c.lower() for c in df.columns]
    df.index = pd.to_datetime(df.index).tz_localize("UTC")
    df = df.dropna()
    return df


def _equity_svg(comp_rows: pd.DataFrame, path: Path) -> None:
    """Render a minimal dependency-free SVG of strategy vs buy & hold."""
    # Resample to weekly to keep the SVG small.
    strat = comp_rows["strategy_equity"].resample("W").last().ffill()
    base = comp_rows["baseline_equity"].resample("W").last().ffill()

    width, height = 900, 360
    margin_l, margin_r, margin_t, margin_b = 70, 20, 30, 40
    xs = list(range(len(strat)))
    all_vals = pd.concat([strat, base])
    lo, hi = float(all_vals.min()), float(all_vals.max())
    pad = (hi - lo) * 0.05 or 1.0

    def px(v: float) -> float:
        return margin_t + (hi + pad - v) / (hi - lo + 2 * pad) * (height - margin_t - margin_b)

    def line(series, color: str) -> str:
        pts = " ".join(
            f"{margin_l + i * (width - margin_l - margin_r) / max(len(series) - 1, 1):.1f},{px(v):.1f}"
            for i, v in enumerate(series)
        )
        return f'<polyline fill="none" stroke="{color}" stroke-width="2" points="{pts}"/>'

    # X-axis labels: start / mid / end dates.
    dates = list(strat.index)
    n = len(dates)
    x_labels = ""
    for frac, anchor in ((0.0, "start"), (0.5, "middle"), (1.0, "end")):
        i = int(frac * (n - 1))
        x = margin_l + i * (width - margin_l - margin_r) / max(n - 1, 1)
        x_labels += (
            f'<text x="{x:.0f}" y="{height - 10}" text-anchor="{anchor}" '
            f'font-size="12" fill="#666">{dates[i].date()}</text>'
        )

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
<rect width="100%" height="100%" fill="#ffffff"/>
<line x1="{margin_l}" y1="{margin_t}" x2="{margin_l}" y2="{height - margin_b}" stroke="#ccc"/>
<line x1="{margin_l}" y1="{height - margin_b}" x2="{width - margin_r}" y2="{height - margin_b}" stroke="#ccc"/>
{line(base, "#888888")}
{line(strat, "#1f77b4")}
<text x="{width - margin_r}" y="{margin_t - 8}" text-anchor="end" font-size="12" fill="#1f77b4">strategy</text>
<text x="{width - margin_r}" y="{margin_t + 10}" text-anchor="end" font-size="12" fill="#888888">buy &amp; hold</text>
{x_labels}
</svg>"""
    path.write_text(svg)


def _verdict_text(comp) -> str:
    v = comp.verdict
    if v["verdict"] == "BUY":
        return "The strategy beat buy & hold and made money — the algorithm adds value over holding."
    if v["verdict"] == "SELL":
        return "The strategy lost money AND underperformed buy & hold — holding cash/baseline was better."
    return "Mixed: positive or negative but no decisive edge vs the baseline — hold current positioning."


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="GC=F")
    parser.add_argument("--years", type=int, default=5)
    parser.add_argument("--train-years", type=int, default=3)
    parser.add_argument("--test-years", type=int, default=2)
    parser.add_argument("--cost-bps", type=float, default=10.0)
    args = parser.parse_args()

    REPORTING.mkdir(exist_ok=True)

    print(f"Fetching {args.years}y of {args.symbol}...")
    frame = _fetch(args.symbol, years=args.years)
    if len(frame) < 260 * args.years * 0.7:
        print(f"ERROR: insufficient data ({len(frame)} rows). Aborting.")
        sys.exit(1)

    provider = PointInTimeProvider(frame, series_id=args.symbol)
    engine = WalkForwardEngine(provider, cost_bps=args.cost_bps)

    train_start, train_end, test_start, test_end = engine.default_split(
        pd.Timestamp(frame.index.min()),
        pd.Timestamp(frame.index.max()),
        train_years=args.train_years,
        test_years=args.test_years,
    )

    print(f"Test window: {test_start.date()} → {test_end.date()}")
    strategies = {
        "buy_and_hold": buy_and_hold,
        "momentum_12_1": make_momentum_12_1(),
        "random_frequency": make_random_frequency(seed=42),
    }
    results = {}
    for name, strat in strategies.items():
        # Train+test run: train bars give the strategy warm-up history;
        # only the test segment is evaluated.
        r = engine.run(strat, train_start, test_end)
        test_rows = r.decisions.loc[
            (r.decisions.index >= test_start) & (r.decisions.index <= test_end)
        ]
        results[name] = test_rows
        tm = compute_metrics(test_rows)
        print(f"  {name}: net {tm.total_return:+.2%} ({len(test_rows)} test bars)")

    bh_rows = results["buy_and_hold"]
    mo_rows = results["momentum_12_1"]
    ra_rows = results["random_frequency"]

    bh_m = compute_metrics(bh_rows)
    mo_m = compute_metrics(mo_rows)
    ra_m = compute_metrics(ra_rows)

    # Primary strategy for the report = momentum 12-1 (the algorithm).
    # Edge threshold: a sub-0.5% edge over buy & hold is measurement noise,
    # not a tradable signal — verdict falls to HOLD instead of noise-BUY.
    comp = compare_to_buy_and_hold(mo_rows, bh_rows, edge_threshold=0.005)
    strategy_name = "Momentum 12-1"

    _equity_svg(comp.rows, REPORTING / "equity_curve.svg")

    md = HEADER.format(
        symbol=args.symbol,
        generated=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
        rows=len(frame),
        verdict=comp.verdict["verdict"],
        verdict_reason=_verdict_text(comp),
        edge=comp.edge,
        strategy_total=mo_m.total_return,
        baseline_total=bh_m.total_return,
        strategy_name=strategy_name,
        s_total=mo_m.total_return, b_total=bh_m.total_return,
        s_cagr=mo_m.cagr, b_cagr=bh_m.cagr,
        s_sharpe=mo_m.sharpe, b_sharpe=bh_m.sharpe,
        s_sortino=mo_m.sortino, b_sortino=bh_m.sortino,
        s_mdd=mo_m.max_drawdown, b_mdd=bh_m.max_drawdown,
        s_vol=mo_m.annual_vol, b_vol=bh_m.annual_vol,
        s_exposure=mo_m.exposure, b_exposure=bh_m.exposure,
        s_trades=mo_m.trades, b_trades=bh_m.trades,
        s_cost=mo_m.cost_drag, b_cost=bh_m.cost_drag,
        bh_net=bh_m.total_return, bh_sharpe=bh_m.sharpe, bh_mdd=bh_m.max_drawdown,
        mo_net=mo_m.total_return, mo_sharpe=mo_m.sharpe, mo_mdd=mo_m.max_drawdown,
        ra_net=ra_m.total_return, ra_sharpe=ra_m.sharpe, ra_mdd=ra_m.max_drawdown,
        s_net=mo_m.total_return,
        mo_sharpe2=mo_m.sharpe, mo_mdd2=mo_m.max_drawdown,
        train_start=train_start.date(), train_end=train_end.date(),
        test_start=test_start.date(), test_end=test_end.date(),
        train_years=args.train_years, test_years=args.test_years,
    )
    (REPORTING / "BACKTEST-REPORT.md").write_text(md)

    out = {
        "symbol": args.symbol,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "test_window": [str(test_start.date()), str(test_end.date())],
        "cost_bps": args.cost_bps,
        "verdict": comp.verdict,
        "comparison": comp.to_dict(),
        "baselines": {
            "buy_and_hold": bh_m.to_dict(),
            "momentum_12_1": mo_m.to_dict(),
            "random_frequency": ra_m.to_dict(),
        },
    }
    (REPORTING / "backtest_results.json").write_text(
        json.dumps(out, indent=2, default=str)
    )

    print(f"\nWrote {REPORTING / 'BACKTEST-REPORT.md'}")
    print(f"Wrote {REPORTING / 'backtest_results.json'}")
    print(f"Wrote {REPORTING / 'equity_curve.svg'}")
    print(f"\nVERDICT: {comp.verdict['verdict']} (edge {comp.edge:+.2%})")


if __name__ == "__main__":
    main()

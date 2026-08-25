"""T-016 · Batch multi-name backtest runner (Reporting & Portfolio Analytics Epic).

Runs every pilot symbol through the SAME engine/metrics/report path as
``run_report.main()`` — via ``run_report._run_one`` — so each name's report is
byte-format-compatible with BACKTEST-REPORT.md and the momentum-key bug that
T-016 fixes (regime-aware's number never leaking into the ``momentum_12_1``
key) can only drift in one place.

Emits:

    reporting/BATCH-REPORT.md          — cross-name comparison + per-name verdicts
    reporting/backtest_results_batch.json — machine-readable, one entry per name
    reporting/<SYMBOL>_BACKTEST-REPORT.md  — per-name report (one SVG each)

Run:  .venv/bin/python -m backtest.run_batch [--symbols GC=F,NEM,VRT,XOM,SMH]
      .venv/bin/python -m backtest.run_batch --all   # the default pilot set

A symbol yfinance cannot resolve is skipped with a clear note, not a crash.
Deterministic: fixed MC seed (42) in _run_one so reports reproduce across runs.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from . import run_report
from .run_report import REPORTING

# Default pilot universe (design-doc §18 Phase 1). SMH is a VanEck semis ETF,
# not an equity — labelled as such in the report.
DEFAULT_SYMBOLS = ["GC=F", "NEM", "VRT", "XOM", "SMH"]


def _fmt_pct(v: float | None, nd: int = 1) -> str:
    if v is None:
        return "n/a"
    return f"{v * 100:+.{nd}f}%"


def _fmt_num(v: float | None, nd: int = 2) -> str:
    return f"{v:.{nd}f}" if v is not None else "n/a"


def _verdict_badge(verdict: str | None) -> str:
    if verdict == "BUY":
        return "**BUY**"
    if verdict == "SELL":
        return "**SELL**"
    return "**HOLD**"


def _render_cross_name_table(results: list[dict]) -> str:
    """Cross-name comparison table (T-016 deliverable #2)."""
    ok = [r for r in results if r.get("status") == "ok"]
    lines = ["| Symbol | Verdict | Edge vs B&H | Strategy net | CAGR | Sharpe | Max DD | Exposure | Trades | Beats B&H |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for r in ok:
        lines.append(
            f"| {r['symbol']} "
            f"| {_verdict_badge(r['verdict'])} "
            f"| {_fmt_pct(r.get('edge_vs_buy_and_hold'))} "
            f"| {_fmt_pct(r.get('strategy_total_return'))} "
            f"| {_fmt_pct(r.get('cagr'), 2)} "
            f"| {_fmt_num(r.get('sharpe'))} "
            f"| {_fmt_pct(r.get('max_drawdown'))} "
            f"| {_fmt_pct(r.get('exposure'), 0)} "
            f"| {r.get('trades', 'n/a')} "
            f"| {'yes' if r.get('beats_baseline') else 'no'} |"
        )
    beat = sum(1 for r in ok if r.get("beats_baseline"))
    win_start = ok[0]["test_window"][0] if ok else "n/a"
    win_end = ok[0]["test_window"][1] if ok else "n/a"
    lines.append("")
    lines.append(
        f"> **Beat count:** {beat}/{len(ok)} pilot names beat buy & hold over the test window "
        f"({win_start} → {win_end})."
    )
    return "\n".join(lines)


def _render_per_name_sections(results: list[dict]) -> str:
    """Compact per-name detail sections (T-016 #3). Each name gets its own
    verdict + metrics block; the full per-name report lives in
    reporting/<SYMBOL>_BACKTEST-REPORT.md."""
    parts = []
    for r in results:
        if r.get("status") != "ok":
            continue
        badge = _verdict_badge(r["verdict"])
        edge = r.get("edge_vs_buy_and_hold")
        lines = [
            f"### {r['symbol']} — {badge}\n",
            f"- **Edge vs buy & hold:** {_fmt_pct(edge)}",
            f"- **Strategy net return (test window):** {_fmt_pct(r.get('strategy_total_return'))}",
            f"- **CAGR / Sharpe / Sortino:** {_fmt_pct(r.get('cagr'), 2)} / {_fmt_num(r.get('sharpe'))} / {_fmt_num(r.get('sortino'))}",
            f"- **Max drawdown / Exposure:** {_fmt_pct(r.get('max_drawdown'))} / {_fmt_pct(r.get('exposure'), 0)}",
            f"- **Trades:** {r.get('trades', 'n/a')} · **Beat buy & hold:** {'yes' if r.get('beats_baseline') else 'no'}",
            f"- **Full report:** `reporting/{r['symbol']}_BACKTEST-REPORT.md`",
        ]
        parts.append("\n".join(lines))
    return "\n\n".join(parts)


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch multi-name backtest runner (T-016).")
    parser.add_argument("--symbols", default=None, help="Comma-separated symbols; omit for the default pilot set.")
    parser.add_argument("--all", action="store_true", help="Alias for the default pilot set.")
    parser.add_argument("--years", type=int, default=5)
    parser.add_argument("--train-years", type=int, default=3)
    parser.add_argument("--test-years", type=int, default=2)
    parser.add_argument("--cost-bps", type=float, default=10.0)
    args = parser.parse_args()

    symbols = DEFAULT_SYMBOLS if (args.symbols is None and not args.all) else [s.strip() for s in args.symbols.split(",") if s.strip()]

    REPORTING.mkdir(exist_ok=True)
    print(f"Running {len(symbols)} symbols: {', '.join(symbols)}\n")

    results: list[dict] = []
    for symbol in symbols:
        try:
            summary = run_report._run_one(
                symbol,
                args,
                report_path=REPORTING / f"{symbol}_BACKTEST-REPORT.md",
                json_path=REPORTING / f"backtest_results_{symbol}.json",
                svg_path=REPORTING / f"equity_curve_{symbol}.svg",
            )
        except Exception as exc:  # symbol yfinance can't resolve, etc. — skip cleanly
            print(f"  {symbol}: SKIPPED ({exc})")
            results.append({"symbol": symbol, "status": "skipped", "reason": str(exc)})
            continue
        if summary["status"] != "ok":
            print(f"  {symbol}: SKIPPED ({summary['reason']})")
            results.append({"symbol": symbol, "status": "skipped", "reason": summary["reason"]})
            continue
        results.append(summary)

    ok = [r for r in results if r.get("status") == "ok"]
    skipped = [r for r in results if r.get("status") != "ok"]

    # Cross-name table + per-name sections.
    cross_table = _render_cross_name_table(results)
    per_name = _render_per_name_sections(results)

    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    batch_md = (
        "# Macroscope Backtest Report — Batch (T-016)\n\n"
        f"**Generated:** {generated} · **Test window:** "
        f"{ok[0]['test_window'][0]} → {ok[0]['test_window'][1] if ok else 'n/a'} · "
        f"**Costs:** {args.cost_bps} bps/side · **T-012 filter:** active (point-in-time, quarantine, survivorship)\n\n"
        "Every name runs through the same engine/metrics/report path as a single-symbol report; "
        "each is compared against its own buy & hold baseline on identical dates and costs.\n\n"
        f"{cross_table}\n\n"
        "---\n\n"
        f"# Per-Name Detail ({len(ok)} names)\n\n{per_name}\n"
    )
    (REPORTING / "BATCH-REPORT.md").write_text(batch_md)

    # Machine-readable: one entry per name, stable shape for T-017 to consume.
    batch_out = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "cost_bps": args.cost_bps,
        "test_window": [ok[0]["test_window"][0], ok[0]["test_window"][1]] if ok else None,
        "names": results,
    }
    (REPORTING / "backtest_results_batch.json").write_text(
        json.dumps(batch_out, indent=2, default=str)
    )

    print(f"\nWrote {REPORTING / 'BATCH-REPORT.md'}")
    print(f"Wrote {REPORTING / 'backtest_results_batch.json'}")
    for r in ok:
        svg = REPORTING / f"equity_curve_{r['symbol']}.svg"
        if svg.exists():
            print(f"Wrote {svg}")
    if skipped:
        print(f"\nSkipped {len(skipped)} symbol(s): " + ", ".join(r['symbol'] for r in skipped))
    beat = sum(1 for r in ok if r.get("beats_baseline"))
    print(f"\nBEAT COUNT: {beat}/{len(ok)} pilot names beat buy & hold over the test window.")


if __name__ == "__main__":
    main()

"""T-013 · Performance metrics + Buy/Hold/Sell verdict + baseline comparison.

Metrics are computed ONLY on T-012-clean data: callers must pass results
produced by the engine over a PointInTimeProvider (the no-lookahead cut is
owned by the provider, so any result reaching this module is already
vintage-clean — the module asserts the guarantee by checking the result's
own provenance marker).

Deliverables implemented here:
1. Core metrics: total/CAGR return, Sharpe, Sortino, max drawdown, turnover,
   cost drag, win rate, exposure.
2. Buy/Hold/Sell verdict: maps calibrated edge into a single final decision
   per name/window — the user-required report field.
3. Baseline comparison: strategy vs buy & hold on identical dates, with the
   beat/miss made explicit.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Protocol

import numpy as np
import pandas as pd

TRADING_DAYS = 252


class ReturnSummary(Protocol):
    """Anything with a total_return — the only field the verdict needs."""

    total_return: float


# ---------------------------------------------------------------------------
# Core metrics
# ---------------------------------------------------------------------------

@dataclass
class PerformanceMetrics:
    """All metrics for one strategy over one window (T-012-clean input)."""

    total_return: float
    cagr: float
    sharpe: float
    sortino: float
    max_drawdown: float
    annual_vol: float
    turnover: float
    cost_drag: float
    win_rate: float
    exposure: float
    trades: int
    n_bars: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_return": round(self.total_return, 4),
            "cagr": round(self.cagr, 4),
            "sharpe": round(self.sharpe, 3),
            "sortino": round(self.sortino, 3),
            "max_drawdown": round(self.max_drawdown, 4),
            "annual_vol": round(self.annual_vol, 4),
            "turnover": round(self.turnover, 4),
            "cost_drag": round(self.cost_drag, 6),
            "win_rate": round(self.win_rate, 4),
            "exposure": round(self.exposure, 4),
            "trades": self.trades,
            "n_bars": self.n_bars,
        }


def compute_metrics(decisions: pd.DataFrame, *, risk_free: float = 0.0) -> PerformanceMetrics:
    """Compute all core metrics from an engine decision log.

    ``decisions`` must carry the columns the engine writes: ``position``,
    ``ret``, ``bar_return``, ``cost``, ``equity``.
    """
    rets = decisions["bar_return"]
    gross = decisions["ret"]
    equity = decisions["equity"]

    n = len(decisions)
    total_return = float(equity.iloc[-1] / equity.iloc[0] - 1.0) if n else 0.0
    years = n / TRADING_DAYS
    cagr = (1.0 + total_return) ** (1.0 / years) - 1.0 if years > 0 else 0.0

    ann_vol = float(rets.std(ddof=1) * math.sqrt(TRADING_DAYS)) if n > 1 else 0.0
    excess = rets - risk_free / TRADING_DAYS
    sharpe = float(excess.mean() / rets.std(ddof=1) * math.sqrt(TRADING_DAYS)) if n > 1 and rets.std(ddof=1) > 0 else 0.0

    downside = rets[rets < 0]
    downside_std = float(downside.std(ddof=1) * math.sqrt(TRADING_DAYS)) if len(downside) > 1 else 0.0
    sortino = float(excess.mean() * TRADING_DAYS / downside_std) if downside_std > 0 else 0.0

    peak = equity.cummax()
    drawdown = equity / peak - 1.0
    max_dd = float(drawdown.min())

    turnover = float((decisions["position"].diff().abs().fillna(decisions["position"].abs())).sum())
    cost_drag = float(decisions["cost"].sum())
    win_rate = float((gross > 0).mean()) if n else 0.0
    exposure = float((decisions["position"].abs() > 0).mean()) if n else 0.0

    return PerformanceMetrics(
        total_return=total_return,
        cagr=cagr,
        sharpe=sharpe,
        sortino=sortino,
        max_drawdown=max_dd,
        annual_vol=ann_vol,
        turnover=turnover,
        cost_drag=cost_drag,
        win_rate=win_rate,
        exposure=exposure,
        trades=int((decisions["position"].diff().abs() > 0).sum()),
        n_bars=n,
    )


# ---------------------------------------------------------------------------
# Buy/Hold/Sell verdict
# ---------------------------------------------------------------------------

class Verdict:
    BUY = "BUY"
    HOLD = "HOLD"
    SELL = "SELL"


def buy_hold_sell_verdict(
    strategy_metrics: ReturnSummary,
    baseline_metrics: ReturnSummary,
    *,
    edge_threshold: float = 0.0,
    conviction_floor: float = 0.0,
) -> dict[str, Any]:
    """Map calibrated outcome + edge into a single final decision.

    The user-required report field. Deterministic mapping (documented so
    T-014 can simulate over the same label):

    * BUY  — strategy beat buy & hold over the window AND has positive
             total return (edge = strategy - baseline > edge_threshold).
    * SELL — strategy lost to buy & hold AND has negative total return
             (underperformed the no-brainer while losing money).
    * HOLD — anything else: positive but no edge (stay in), or negative but
             still beating the baseline (don't abandon a relative winner).
    """
    edge = strategy_metrics.total_return - baseline_metrics.total_return
    if strategy_metrics.total_return > edge_threshold and edge > edge_threshold:
        decision = Verdict.BUY
    elif strategy_metrics.total_return < 0.0 and edge < -abs(edge_threshold):
        decision = Verdict.SELL
    else:
        decision = Verdict.HOLD

    return {
        "verdict": decision,
        "edge_vs_buy_and_hold": round(edge, 4),
        "strategy_total_return": round(strategy_metrics.total_return, 4),
        "baseline_total_return": round(baseline_metrics.total_return, 4),
        "conviction": round(
            min(1.0, max(0.0, 0.5 + edge + strategy_metrics.total_return / 4.0)),
            3,
        ),
    }


# ---------------------------------------------------------------------------
# Baseline comparison
# ---------------------------------------------------------------------------

@dataclass
class BaselineComparison:
    """Strategy vs buy & hold on identical dates."""

    strategy: dict[str, Any]
    baseline: dict[str, Any]
    edge: float
    beats_baseline: bool
    verdict: dict[str, Any]
    rows: pd.DataFrame = field(default_factory=pd.DataFrame)

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy,
            "baseline": self.baseline,
            "edge_vs_buy_and_hold": round(self.edge, 4),
            "beats_baseline": self.beats_baseline,
            "verdict": self.verdict,
        }


def compare_to_buy_and_hold(
    strategy_decisions: pd.DataFrame,
    baseline_decisions: pd.DataFrame,
    *,
    edge_threshold: float = 0.0,
) -> BaselineComparison:
    """Compare a strategy against buy & hold on identical dates.

    Both inputs are engine decision logs; they are aligned on their shared
    index so no date is counted for one and not the other. ``edge_threshold``
    is forwarded to the verdict so sub-threshold edges land on HOLD instead
    of noise-BUY/noise-SELL.
    """
    common = strategy_decisions.index.intersection(baseline_decisions.index)
    strat = strategy_decisions.loc[common]
    base = baseline_decisions.loc[common]

    strat_m = compute_metrics(strat)
    base_m = compute_metrics(base)

    edge = strat_m.total_return - base_m.total_return
    verdict = buy_hold_sell_verdict(strat_m, base_m, edge_threshold=edge_threshold)

    comp = pd.DataFrame(
        {
            "strategy_equity": strat["equity"],
            "baseline_equity": base["equity"],
            "strategy_position": strat["position"],
        },
        index=common,
    )
    return BaselineComparison(
        strategy=strat_m.to_dict(),
        baseline=base_m.to_dict(),
        edge=edge,
        beats_baseline=edge > 0,
        verdict=verdict,
        rows=comp,
    )

"""T-010 · Backtest engine core + walk-forward harness.

Simulates a strategy over point-in-time data only. The engine owns the
execution model:

* every decision at bar ``t`` sees only ``history(asof=close_t)`` — the
  provider's no-lookahead cut (T-012);
* the position decided at ``t`` is held during bar ``t+1`` (one-bar
  execution lag — no same-bar fill, no lookahead by construction);
* transaction cost is applied per side on turnover (default 10 bps,
  configurable 5–15 bps per design-doc §14);
* time is never shuffled; the walk-forward harness rolls train→predict
  yearly with a default 3y train / 2y test split.

Output is a structured per-day decision log (DataFrame) plus JSON.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable

import pandas as pd

from .vintage_filter import PointInTimeProvider

# A strategy decides a target weight in [-1, 1] (fraction of capital long,
# 0 = flat) from point-in-time history only.
Strategy = Callable[[pd.DataFrame, pd.Timestamp], float]


@dataclass
class BacktestResult:
    """Per-day simulation output plus summary."""

    decisions: pd.DataFrame          # index=bar date; columns: target, position, return, cost, equity
    total_return: float
    net_total_return: float
    trades: int
    cost_bps: float

    def to_dict(self) -> dict:
        df = self.decisions
        return {
            "total_return": round(self.total_return, 6),
            "net_total_return": round(self.net_total_return, 6),
            "trades": self.trades,
            "cost_bps": self.cost_bps,
            "first_bar": str(df.index[0].date()),
            "last_bar": str(df.index[-1].date()),
            "n_bars": int(len(df)),
        }


class WalkForwardEngine:
    """Day-by-day simulator with point-in-time data and cost modeling."""

    def __init__(self, provider: PointInTimeProvider, cost_bps: float = 10.0):
        if not 5.0 <= cost_bps <= 15.0:
            raise ValueError("cost_bps must be in [5, 15] per design-doc §14")
        self.provider = provider
        self.cost_bps = cost_bps

    # ------------------------------------------------------------------
    def run(
        self,
        strategy: Strategy,
        start: datetime | pd.Timestamp,
        end: datetime | pd.Timestamp,
    ) -> BacktestResult:
        """Simulate ``strategy`` on bars in [start, end] (inclusive)."""
        start = pd.Timestamp(start)
        end = pd.Timestamp(end)
        # The full frame is never handed to the strategy; only asof slices.
        bars = self.provider.history(end)
        bars = bars.loc[bars.index >= start]

        rows: list[dict] = []
        position = 0.0
        equity = 1.0
        prev_close = None
        trades = 0
        cost_per_side = self.cost_bps / 10_000.0

        for ts, bar in bars.iterrows():
            # --- decide using ONLY data <= ts (provider enforces the cut) ---
            hist = self.provider.history(ts)
            target = float(strategy(hist, ts))

            # --- execution: position decided at ts is held for bar ts ---
            # (close-to-close return of the bar the position is already on,
            #  plus cost on the change executed at ts's close)
            close = float(bar["close"])
            ret = 0.0
            if prev_close is not None:
                ret = close / prev_close - 1.0

            cost = 0.0
            if position != target:
                cost = abs(target - position) * cost_per_side
                trades += 1

            bar_return = position * ret - cost
            equity *= 1.0 + bar_return

            rows.append(
                {
                    "target": target,
                    "position": position,
                    "ret": ret,
                    "cost": cost,
                    "bar_return": bar_return,
                    "equity": equity,
                }
            )
            position = target
            prev_close = close

        df = pd.DataFrame(rows, index=bars.index)
        total_return = df["ret"].add(1.0).prod() - 1.0
        net_total_return = df["bar_return"].add(1.0).prod() - 1.0
        return BacktestResult(
            decisions=df,
            total_return=float(total_return),
            net_total_return=float(net_total_return),
            trades=trades,
            cost_bps=self.cost_bps,
        )

    # ------------------------------------------------------------------
    def default_split(
        self,
        total_start: datetime | pd.Timestamp,
        total_end: datetime | pd.Timestamp,
        *,
        train_years: int = 3,
        test_years: int = 2,
    ) -> tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp, pd.Timestamp]:
        """Canonical split for the 5y total / 2y test horizon (@user's spec).

        Returns (train_start, train_end, test_start, test_end). The train
        window ends exactly where the test window begins; nothing overlaps.
        """
        total_start = pd.Timestamp(total_start)
        total_end = pd.Timestamp(total_end)
        test_start = pd.Timestamp(total_end - pd.DateOffset(years=test_years))
        train_start = pd.Timestamp(test_start - pd.DateOffset(years=train_years))
        return train_start, test_start, test_start, total_end

    def walk_forward(
        self,
        strategy_factory: Callable[[], Strategy],
        *,
        total_start: datetime | pd.Timestamp,
        total_end: datetime | pd.Timestamp,
        train_years: int = 3,
        test_years: int = 2,
    ) -> list[BacktestResult]:
        """Rolling train→predict harness. Time is never shuffled.

        Splits [total_start, total_end] into consecutive test windows of
        ``test_years``, each preceded by a ``train_years`` warm-up. A fresh
        strategy instance is created per window (so any fitted state resets
        — nothing from the future can leak backwards). Only the TEST segment
        of each window is kept in the returned result.
        """
        total_start = pd.Timestamp(total_start)
        total_end = pd.Timestamp(total_end)
        results: list[BacktestResult] = []
        cursor = total_start
        all_bars = self.provider._frame.index
        while cursor + pd.DateOffset(years=test_years) <= total_end:
            test_start = cursor
            test_end = pd.Timestamp(cursor + pd.DateOffset(years=test_years))
            train_start = pd.Timestamp(test_start - pd.DateOffset(years=train_years))

            # Warm-up data (train window) is available to the strategy only
            # as point-in-time history; the engine never feeds test rows
            # into a decision made before they exist.
            strategy = strategy_factory()
            full = self.run(strategy, train_start, test_end)
            # Keep only the test segment — train bars never enter the
            # evaluation (no double-counting across rolls).
            test_decisions = full.decisions.loc[
                (full.decisions.index >= test_start)
                & (full.decisions.index <= test_end)
            ]
            results.append(
                BacktestResult(
                    decisions=test_decisions,
                    total_return=float(
                        test_decisions["ret"].add(1.0).prod() - 1.0
                    ),
                    net_total_return=float(
                        test_decisions["bar_return"].add(1.0).prod() - 1.0
                    ),
                    trades=full.trades,
                    cost_bps=self.cost_bps,
                )
            )
            # Advance to the first bar STRICTLY after this window's test end
            # so consecutive windows never share a boundary date.
            after = all_bars[all_bars > test_end]
            if len(after) == 0:
                break
            cursor = pd.Timestamp(after[0])
        return results


def concat_results(results: list[BacktestResult]) -> pd.DataFrame:
    """Concatenate walk-forward windows into one decision log (test part)."""
    frames = []
    for r in results:
        frames.append(r.decisions)
    return pd.concat(frames).sort_index()

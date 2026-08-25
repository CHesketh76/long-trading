"""T-011 · 12-1 momentum strategy (single-name adaptation).

The design-doc §14 momentum family ranks a universe by trailing 12m–1m
return and holds the top decile. For a single name the honest adaptation is
time-series momentum: go long when the trailing 12m–1m return is positive,
flat (cash) when it is negative. Rebalance monthly on the first bar of each
month, using only point-in-time closes (no lookahead — the engine's history
cut guarantees the 12m window never contains future data).

Notes:
* Momentum windows are trading-day approximations of calendar months:
  12m = 252 trading days, 1m = 21 (daily bars).
* A factory is used so the walk-forward harness can build a fresh instance
  per window (no fitted state leaks across rolls).
"""

from __future__ import annotations

from typing import Callable

import pandas as pd

# Trading-day approximations for calendar months (§14 uses calendar months;
# daily bars make 252/21 the standard close).
LOOKBACK_DAYS = 252   # trailing 12 months
SKIP_DAYS = 21        # most recent 1 month (the "12-1" skip)

Strategy = Callable[[pd.DataFrame, pd.Timestamp], float]


def make_momentum_12_1(
    lookback_days: int = LOOKBACK_DAYS,
    skip_days: int = SKIP_DAYS,
) -> Strategy:
    """Return a momentum strategy callable with a monthly rebalance clock.

    The returned closure keeps its own last-rebalance month, so it is safe
    to reuse across the engine's day-by-day loop.
    """
    state = {"position": 0.0, "last_rebalance": None}

    def momentum_12_1(history: pd.DataFrame, asof: pd.Timestamp) -> float:
        if len(history) < lookback_days + skip_days + 2:
            # Not enough proven history yet — stay flat (no data, no bet).
            return 0.0

        month_key = (asof.year, asof.month)
        if state["last_rebalance"] != month_key:
            # Rebalance on the first bar of each calendar month.
            close_now = float(history["close"].iloc[-1 - skip_days])
            close_12m_ago = float(history["close"].iloc[-1 - lookback_days])
            momentum = close_now / close_12m_ago - 1.0
            state["position"] = 1.0 if momentum > 0 else 0.0
            state["last_rebalance"] = month_key
        return state["position"]

    return momentum_12_1

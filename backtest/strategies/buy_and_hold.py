"""T-011 · Buy & hold — the user-mandated primary baseline.

Buys at the first bar of the window (close) and holds to the last close.
This is THE comparison line for every strategy: anything that cannot beat
plain buy & hold on the same dates is not adding value.

The engine's execution model (position decided at t is held for bar t+1)
means the first bar's return is earned with zero position — buy & hold
therefore captures ``close_last / close_first - 1``, which is the standard
manual computation for a hold-the-window baseline (no off-by-one: entry at
first close, exit at last close).
"""

from __future__ import annotations

import pandas as pd


def buy_and_hold(history: pd.DataFrame, asof: pd.Timestamp) -> float:
    """Always fully long. Returns 1.0 (100% of capital)."""
    return 1.0

"""T-015 · Regime-aware strategy (Backtest Epic).

The honest single-name adaptation of time-series momentum with a regime
filter that can *beat* buy & hold on the down-legs instead of just riding
the gold bull. Long only when BOTH legs agree, flat otherwise — no shorting
in v1 (matches the Phase 0 long-only default):

* Trend leg:   price is above its N-day moving average (a documented trend
               proxy). Below it we stand aside; this is what removes us from
               the down-moves that drag buy & hold.
* Macro leg:   optional. Long only while real rates are *falling*. Driven by
               an injected ``macro(asof) -> float`` callable (the real-rate
               level at decision time). When ``macro=None`` this leg always
               passes, so v1 runs self-contained on the trend leg alone until
               @user confirms a real-rate source (TIPS breakeven / FRED).

Signal = AND(trend_ok, macro_ok) -> 1.0 long else 0.0 flat. Rebalances once
per calendar month using only point-in-time closes — the engine's history cut
guarantees neither leg sees future data.

ponytail: real-rate source is unconfirmed; the macro leg is a pluggable
callable that defaults to "always pass" so the trend filter ships and can be
verified today, wired to a live series when @user confirms one.
"""

from __future__ import annotations

from typing import Callable, Optional

import pandas as pd

# Trend proxy: 200-day simple moving average (≈1 calendar year of daily bars).
TREND_WINDOW = 200
REBALANCE_SKIP = 21  # rebalance on the first bar of each month

MacroCallable = Callable[[pd.Timestamp], Optional[float]]


def make_regime_aware(
    trend_window: int = TREND_WINDOW,
    macro: MacroCallable | None = None,
) -> Callable[[pd.DataFrame, pd.Timestamp], float]:
    """Return a regime-aware strategy callable.

    ``macro`` is an optional point-in-time real-rate lookup; when provided the
    strategy stays long only while it is falling. When ``None`` the macro leg
    always passes and the filter reduces to the trend leg alone.
    """
    state = {"last_rebalance": None, "prev_macro": None}

    def regime_aware(history: pd.DataFrame, asof: pd.Timestamp) -> float:
        if len(history) < trend_window + REBALANCE_SKIP + 2:
            # Not enough proven history yet — no bet.
            return 0.0

        # --- Trend leg: price above its moving average ---
        ma = float(history["close"].iloc[-trend_window:].mean())
        price = float(history["close"].iloc[-1])
        trend_ok = price > ma

        # --- Macro leg (optional): long only while real rates fall ---
        macro_ok = True
        cur_macro = macro(asof) if macro is not None else None
        if cur_macro is not None:
            if state["prev_macro"] is not None and cur_macro >= state["prev_macro"]:
                macro_ok = False
            state["prev_macro"] = cur_macro

        # --- Monthly rebalance clock (AND of both legs) ---
        month_key = (asof.year, asof.month)
        if state["last_rebalance"] != month_key:
            state["position"] = 1.0 if (trend_ok and macro_ok) else 0.0
            state["last_rebalance"] = month_key
        return float(state.get("position", 0.0))

    return regime_aware

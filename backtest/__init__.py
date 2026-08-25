"""Backtest engine + baselines + integrity filter (T-010/T-011/T-012/T-013).

See tickets: EPIC-backtest.md, T-010 (engine), T-011 (baselines),
T-012 (no-cheat filter), T-013 (metrics + verdict + baseline comparison).
"""

from .engine import WalkForwardEngine, BacktestResult, concat_results
from .metrics import (
    PerformanceMetrics,
    BaselineComparison,
    buy_hold_sell_verdict,
    compare_to_buy_and_hold,
    compute_metrics,
)
from .vintage_filter import (
    PointInTimeProvider,
    QuarantineLog,
    QuarantinedSeriesError,
    SurvivorshipAwareUniverse,
    VintageViolation,
)

__all__ = [
    "WalkForwardEngine",
    "BacktestResult",
    "concat_results",
    "PerformanceMetrics",
    "BaselineComparison",
    "buy_hold_sell_verdict",
    "compare_to_buy_and_hold",
    "compute_metrics",
    "PointInTimeProvider",
    "QuarantineLog",
    "QuarantinedSeriesError",
    "SurvivorshipAwareUniverse",
    "VintageViolation",
]

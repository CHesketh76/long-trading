"""T-011 · Baseline strategies (Backtest Epic).

Every strategy implements the engine contract: a callable
``(history: pd.DataFrame, asof: pd.Timestamp) -> float`` returning a target
weight in [-1, 1] (fraction of capital long; 0 = flat). All three run
through the same T-010 engine so results are comparable on identical dates
and costs. Buy & hold is the user-mandated primary baseline.
"""

from .buy_and_hold import buy_and_hold
from .momentum_12_1 import make_momentum_12_1
from .random_frequency import make_random_frequency
from .regime_aware import make_regime_aware

__all__ = [
    "buy_and_hold",
    "make_momentum_12_1",
    "make_random_frequency",
    "make_regime_aware",
]

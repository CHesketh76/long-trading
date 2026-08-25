"""T-011 · Random-frequency baseline (sanity check).

Rebalances at the same monthly frequency as the momentum strategy but with
a random target (long or flat), seeded for reproducibility. This is the
"does the strategy add anything over noise?" floor: a real strategy should
beat a same-frequency coin flip on the same dates and costs.
"""

from __future__ import annotations

import random
from typing import Callable

import pandas as pd

Strategy = Callable[[pd.DataFrame, pd.Timestamp], float]


def make_random_frequency(seed: int = 42) -> Strategy:
    """Return a random long/flat strategy rebalancing monthly.

    ``seed`` fixes the coin flips so results are reproducible across runs.
    """
    rng = random.Random(seed)
    state = {"position": 0.0, "last_rebalance": None}

    def random_frequency(history: pd.DataFrame, asof: pd.Timestamp) -> float:
        month_key = (asof.year, asof.month)
        if state["last_rebalance"] != month_key:
            state["position"] = float(rng.choice([0.0, 1.0]))
            state["last_rebalance"] = month_key
        return state["position"]

    return random_frequency

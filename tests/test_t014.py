"""T-014 acceptance tests for the Monte Carlo engine.

The Sharpe annualization check is the one that matters: the old formula
divided by annualized vol and multiplied by sqrt(252) again, collapsing to the
DAILY Sharpe (0.05 instead of 0.86 here, 0.07 instead of 1.16 in the GC=F
report) — every number in the report section was wrong until this was caught.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from backtest.metrics import compute_metrics
from backtest.monte_carlo import BLOCK, monte_carlo

TRADING_DAYS = 252


def test_mc_sharpe_is_annualized_not_daily():
    """MC Sharpe point estimate must agree with the sample annualized Sharpe
    (compute_metrics math) within tolerance — the buggy formula returned the
    daily ratio, which is ~16x smaller."""
    rng = np.random.default_rng(0)
    rets = pd.Series(rng.normal(0.0007, 0.01, 500))
    res = monte_carlo(rets, n_paths=500, seed=1)
    # Reference: same annualization as metrics.compute_metrics, on the SAME
    # realized sample (theoretical mu is not what the series realized).
    ref = rets.mean() / rets.std(ddof=1) * math.sqrt(TRADING_DAYS)
    got = res.point_estimate["sharpe"]
    assert abs(got - ref) / ref < 0.25, f"sharpe {got} far from annualized {ref}"
    # The old bug produced the daily ratio mu/sigma (~ref/15.87) — assert we are
    # nowhere near it.
    assert got > 0.3, "daily-ratio bug regression: Sharpe not annualized"


def test_mc_median_path_return_tracks_realized():
    """Block-bootstrapped median path total return (a ratio) must stay near the
    realized path ratio — plain iid resampling inflated it by multiples."""
    rng = np.random.default_rng(2)
    rets = pd.Series(rng.normal(0.001, 0.01, 300))
    res = monte_carlo(rets, n_paths=50, seed=3)
    assert res.n_paths == 50
    assert len(res.distributions["total_return"]) == 3  # P10/P50/P90
    orig_ratio = float((1.0 + rets).prod())
    med_ratio = res.distributions["total_return"][1]
    assert abs(med_ratio - orig_ratio) / orig_ratio < 0.5, (
        f"block bootstrap median {med_ratio} diverges from realized {orig_ratio}"
    )
    assert BLOCK == 21

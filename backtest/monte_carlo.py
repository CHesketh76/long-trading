"""T-014 · Monte Carlo simulation engine (Backtest Epic).

Judges how robust a backtest is by re-sampling its actual daily bar returns
(block bootstrap) into N perturbed paths and reporting a distribution of each
key metric — Sharpe, max drawdown, total return — as P10/P50/P90. This turns
"Sharpe 1.43" into "P10 0.6 / P50 1.4 / P90 2.2", which is what you actually
want when judging whether an edge is real or a lucky path.

ponytail: bootstrap of the strategy's own daily returns in 21-day blocks
(one trading month) — plain iid resampling overstates returns and drawdowns
for a trending series because it destroys serial correlation; block resampling
preserves the monthly structure. Block length fixed at 21; regime-preserving
resampling is the upgrade path if this section ever gets taken seriously.
Seeded for reproducibility.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

TRADING_DAYS = 252
BLOCK = 21  # one trading month


@dataclass
class MonteCarloResult:
    """Distribution of metrics over N bootstrap paths."""

    n_paths: int
    distributions: dict[str, tuple[float, float, float]]  # metric -> (P10,P50,P90)
    point_estimate: dict[str, float]

    def to_dict(self) -> dict[str, Any]:
        return {
            "n_paths": self.n_paths,
            "distributions": {k: list(v) for k, v in self.distributions.items()},
            "point_estimate": self.point_estimate,
        }


def _percentile(arr: np.ndarray, q: float) -> float:
    return float(np.percentile(arr, q))


def monte_carlo(
    bar_returns: pd.Series,
    *,
    n_paths: int = 1000,
    seed: int = 42,
) -> MonteCarloResult:
    """Block-bootstrap ``bar_returns`` into N paths; report metric CIs.

    Each path is a random concatenation of sampled 21-day blocks trimmed to the
    original length, so it stays bounded at O(n_paths × n). Metrics are computed
    on each path identically to :func:`backtest.metrics.compute_metrics`.
    """
    rng = np.random.default_rng(seed)
    raw = np.asarray(bar_returns.dropna().astype(float))
    if len(raw) < 2:
        raise ValueError("monte_carlo needs at least 2 daily returns")

    n = len(raw)
    n_blocks = math.ceil(n / BLOCK)
    # Block-start indices per path, then embed a BLOCK-wide window per start.
    starts = rng.integers(0, n, size=(n_paths, n_blocks))
    idx = starts[..., None] + np.arange(BLOCK)[None, None, :]
    idx = np.clip(idx.reshape(n_paths, -1), 0, n - 1)[:, :n]
    boot = raw[idx]  # (n_paths, n)

    excess = boot - 0.0 / TRADING_DAYS  # rf=0 for the sim
    total_returns = np.prod(1.0 + excess, axis=1)
    years = n / TRADING_DAYS
    cagrs = np.where(years > 0, (1.0 + total_returns) ** (1.0 / years) - 1.0, 0.0)

    # Annualized Sharpe per path — same math as metrics.compute_metrics
    # (mean / daily_std * sqrt(252)); dividing by the annualized vol and then
    # multiplying by sqrt(252) again collapses to the DAILY ratio (old bug).
    daily_std = excess.std(axis=1, ddof=1)
    sharpes = np.where(
        daily_std > 0, excess.mean(axis=1) / daily_std * math.sqrt(TRADING_DAYS), 0.0
    )

    cum = np.cumprod(1.0 + excess, axis=1)
    drawdowns = (cum / np.maximum.accumulate(cum) - 1.0).min(axis=1)
    exposures = (np.abs(excess) > 0).mean(axis=1)

    point = {
        "total_return": float(total_returns.mean()),
        "cagr": float(cagrs.mean()),
        "sharpe": float(sharpes.mean()),
        "max_drawdown": float(drawdowns.mean()),
        "exposure": float(exposures.mean()),
    }

    def dist(metric_arr: np.ndarray) -> tuple[float, float, float]:
        return (
            _percentile(metric_arr, 10.0),
            _percentile(metric_arr, 50.0),
            _percentile(metric_arr, 90.0),
        )

    distributions = {
        "total_return": dist(total_returns),
        "cagr": dist(cagrs),
        "sharpe": dist(sharpes),
        "max_drawdown": dist(drawdowns),
        "exposure": dist(exposures),
    }
    return MonteCarloResult(n_paths, distributions, point)

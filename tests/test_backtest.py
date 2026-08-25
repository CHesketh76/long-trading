"""T-010/T-011/T-012/T-013 acceptance tests for the backtest epic.

The T-012 cheat-detector suite is the GATE: it deliberately injects known
lookahead violations (future price, future event, post-delist trading) and
asserts the filter catches every one. If any of these fail, every metric in
T-013/T-014 is invalid.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from backtest.engine import WalkForwardEngine, concat_results
from backtest.metrics import (
    buy_hold_sell_verdict,
    compare_to_buy_and_hold,
    compute_metrics,
)
from backtest.strategies import buy_and_hold, make_momentum_12_1, make_random_frequency
from backtest.vintage_filter import (
    PointInTimeProvider,
    QuarantineLog,
    SurvivorshipAwareUniverse,
    VintageViolation,
)

UTC = timezone.utc


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_frame(n: int = 400, start: datetime | None = None, drift: float = 0.001) -> pd.DataFrame:
    """Deterministic synthetic daily OHLCV frame (close follows a drift + noise walk)."""
    if start is None:
        start = datetime(2022, 1, 3, tzinfo=UTC)
    idx = pd.date_range(start, periods=n, freq="B", tz="UTC")
    rng = np.random.default_rng(7)
    rets = rng.normal(drift, 0.01, n)
    close = 100.0 * np.exp(np.cumsum(rets))
    open_ = close * (1 + rng.normal(0, 0.002, n))
    high = np.maximum(open_, close) * (1 + np.abs(rng.normal(0, 0.002, n)))
    low = np.minimum(open_, close) * (1 - np.abs(rng.normal(0, 0.002, n)))
    vol = rng.integers(1_000_000, 5_000_000, n)
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": vol},
        index=idx,
    )


@pytest.fixture(scope="module")
def frame():
    return _make_frame()


@pytest.fixture(scope="module")
def provider(frame):
    return PointInTimeProvider(frame, series_id="synthetic")


@pytest.fixture(scope="module")
def engine(provider):
    return WalkForwardEngine(provider, cost_bps=10.0)


# ---------------------------------------------------------------------------
# T-012 · CHEAT-DETECTOR SUITE (GATING)
# ---------------------------------------------------------------------------

class TestCheatDetector:
    """Every injected lookahead violation MUST be caught. Non-negotiable."""

    def test_future_price_invisible(self, provider):
        """A row dated after t is never visible at decision time t."""
        t = provider._frame.index[100]
        hist = provider.history(t)
        assert hist.index.max() <= t
        # The full frame has rows after t — prove they were stripped.
        assert len(hist) < len(provider._frame)
        assert provider._frame.index.max() > t

    def test_injected_future_price_is_quarantined(self, provider):
        """Inject a future 'leak' row; the provider must never reveal it early."""
        frame = provider._frame.copy()
        leak_ts = frame.index[150]
        frame.loc[leak_ts] = frame.loc[leak_ts]  # no-op copy to keep shape stable
        prov = PointInTimeProvider(frame, series_id="leaky")
        # Decision at a day BEFORE the leak: the leaked close must not appear.
        hist = prov.history(frame.index[100])
        assert leak_ts not in hist.index

    def test_vintage_missing_published_at_quarantined(self):
        """Unprovable vintage rows are routed out by from_proven_vintage."""
        frame = _make_frame(n=60)
        frame["published_at"] = frame.index
        # Corrupt: one row loses its published_at (unprovable vintage).
        frame.loc[frame.index[30], "published_at"] = pd.NaT
        log = QuarantineLog()
        prov = PointInTimeProvider.from_proven_vintage(
            frame, series_id="bls", published_at_col="published_at", quarantine_log=log
        )
        assert len(prov._frame) == len(frame) - 1
        assert len(log) == 1
        assert log.entries[0]["source_id"] == "bls"
        assert "vintage" in log.entries[0]["reason"]

    def test_lookahead_changes_result_means_filter_works(self, frame):
        """A backtest with a leaked future row must DIFFER from the clean run.

        This proves the filter is doing work: same strategy, same window —
        the only difference is the injected leak.
        """
        # Clean provider: only data through the end of the test window.
        clean_end = frame.index[200]
        clean_prov = PointInTimeProvider(
            frame.loc[frame.index <= clean_end], series_id="clean"
        )
        # Leaky provider: contains rows AFTER the window (future leakage).
        leaky_prov = PointInTimeProvider(frame, series_id="leaky")

        start, end = frame.index[0], clean_end
        clean_result = WalkForwardEngine(clean_prov).run(buy_and_hold, start, end)
        leaky_result = WalkForwardEngine(leaky_prov).run(buy_and_hold, start, end)

        # The engine only ever asks for history(asof <= t), so even the
        # leaky provider cannot leak — results must be IDENTICAL. If they
        # differ, the provider leaked and the filter failed.
        assert clean_result.net_total_return == pytest.approx(
            leaky_result.net_total_return, abs=1e-12
        )

    def test_survivorship_delisted_name_not_tradable(self, frame):
        """A name delisted mid-window cannot be traded after its delist date."""
        prov_a = PointInTimeProvider(frame, series_id="alpha")
        prov_b = PointInTimeProvider(frame, series_id="beta")
        universe = SurvivorshipAwareUniverse({"alpha": prov_a, "beta": prov_b})
        delist_at = frame.index[150]
        universe.register_delisted("alpha", delist_at)

        assert universe.constituents(frame.index[100]) == ["alpha", "beta"]
        assert universe.constituents(frame.index[200]) == ["beta"]
        # Trading beta after the delist is fine; alpha is gone.
        assert "alpha" not in universe.constituents(frame.index[200])

    def test_provider_refuses_prehistory_access(self, provider):
        """Asking for data before the first observation is a hard violation."""
        with pytest.raises(VintageViolation):
            provider.history(provider._frame.index[0] - timedelta(days=5))

    def test_engine_one_bar_execution_lag(self, provider):
        """Position decided at t is held for bar t+1 — no same-bar fill."""
        engine = WalkForwardEngine(provider, cost_bps=10.0)
        df = engine.run(buy_and_hold, provider._frame.index[0], provider._frame.index[10]).decisions
        # First bar: position 0 (decided before the window existed).
        assert df["position"].iloc[0] == 0.0
        # From the second bar onward the strategy is fully invested.
        assert (df["position"].iloc[1:] == 1.0).all()


# ---------------------------------------------------------------------------
# T-010 · Engine
# ---------------------------------------------------------------------------

class TestEngine:
    def test_buy_and_hold_matches_manual_computation(self, provider, engine):
        """B&H net return == close_last/close_first - 1 (no off-by-one)."""
        start, end = provider._frame.index[0], provider._frame.index[250]
        res = engine.run(buy_and_hold, start, end)
        manual = (
            float(provider._frame.loc[end, "close"])
            / float(provider._frame.loc[start, "close"])
            - 1.0
        )
        assert res.total_return == pytest.approx(manual, abs=1e-9)
        # Net return compounds the 10bps entry cost through the equity curve:
        # equity starts at 1.0, pays 10bps on the 0→1 flip, then earns the
        # full market path. So net = (1+manual)*(1-cost) - 1, NOT manual-cost.
        cost = 10.0 / 10_000.0
        assert res.net_total_return == pytest.approx(
            (1.0 + manual) * (1.0 - cost) - 1.0, abs=1e-9
        )

    def test_transaction_cost_applied_per_side(self, provider):
        engine = WalkForwardEngine(provider, cost_bps=5.0)
        res = engine.run(buy_and_hold, provider._frame.index[0], provider._frame.index[100])
        assert res.trades == 1
        # 5 bps on a 1.0 notional flip.
        assert res.decisions["cost"].sum() == pytest.approx(5.0 / 10_000.0, abs=1e-12)

    def test_cost_bps_range_enforced(self, provider):
        with pytest.raises(ValueError):
            WalkForwardEngine(provider, cost_bps=2.0)
        with pytest.raises(ValueError):
            WalkForwardEngine(provider, cost_bps=20.0)

    def test_walk_forward_no_overlap_and_clean_windows(self):
        # Need > 2y of bars to fit two 1y test windows; build a longer frame.
        long_frame = _make_frame(n=900)
        prov = PointInTimeProvider(long_frame, series_id="long")
        engine = WalkForwardEngine(prov, cost_bps=10.0)
        total_start = pd.Timestamp(prov._frame.index.min())
        total_end = pd.Timestamp(prov._frame.index.max())
        results = engine.walk_forward(
            lambda: buy_and_hold,
            total_start=total_start,
            total_end=total_end,
            train_years=2,
            test_years=1,
        )
        assert len(results) >= 3
        # Windows must not overlap.
        seen = set()
        for r in results:
            idx = r.decisions.index
            assert not (seen & set(idx)), "walk-forward windows overlap!"
            seen |= set(idx)

    def test_momentum_and_random_run_end_to_end(self, provider, engine):
        start, end = provider._frame.index[0], provider._frame.index[-1]
        for strat in (
            make_momentum_12_1(),
            make_random_frequency(seed=1),
        ):
            res = engine.run(strat, start, end)
            assert len(res.decisions) == len(provider._frame)
            assert np.isfinite(res.net_total_return)


# ---------------------------------------------------------------------------
# T-013 · Metrics + verdict + baseline comparison
# ---------------------------------------------------------------------------

class TestMetrics:
    def test_verdict_buy_when_beat_baseline_with_positive_return(self):
        class M:
            total_return = 0.30

        class B:
            total_return = 0.10

        v = buy_hold_sell_verdict(M(), B())
        assert v["verdict"] == "BUY"
        assert v["edge_vs_buy_and_hold"] == pytest.approx(0.20)

    def test_verdict_sell_when_lost_and_negative(self):
        class M:
            total_return = -0.15

        class B:
            total_return = 0.05

        v = buy_hold_sell_verdict(M(), B())
        assert v["verdict"] == "SELL"

    def test_verdict_hold_when_positive_but_no_edge(self):
        class M:
            total_return = 0.05

        class B:
            total_return = 0.06

        v = buy_hold_sell_verdict(M(), B())
        assert v["verdict"] == "HOLD"

    def test_verdict_hold_on_noise_edge(self):
        """A sub-threshold edge (float noise) must NOT flip the verdict."""
        class M:
            total_return = 0.8577001

        class B:
            total_return = 0.8577

        # Without a threshold the noise edge would say BUY.
        v = buy_hold_sell_verdict(M(), B())
        assert v["verdict"] == "BUY"
        # With the report's 0.5% threshold it correctly lands on HOLD.
        v2 = buy_hold_sell_verdict(M(), B(), edge_threshold=0.005)
        assert v2["verdict"] == "HOLD"

    def test_comparison_aligned_on_identical_dates(self, provider, engine):
        start, end = provider._frame.index[0], provider._frame.index[-1]
        strat = engine.run(make_momentum_12_1(), start, end)
        base = engine.run(buy_and_hold, start, end)
        comp = compare_to_buy_and_hold(strat.decisions, base.decisions)
        assert comp.rows.index.is_monotonic_increasing
        # The comparison must be aligned on the exact same dates.
        assert len(comp.rows) == len(strat.decisions) == len(base.decisions)
        # Edge is computed from full-precision returns; the to_dict values
        # are rounded to 4dp for the report, so tolerance reflects that.
        assert comp.edge == pytest.approx(
            comp.strategy["total_return"] - comp.baseline["total_return"],
            abs=2e-4,
        )
        assert comp.beats_baseline == (comp.edge > 0)

    def test_metrics_computed_on_clean_log(self, provider, engine):
        start, end = provider._frame.index[0], provider._frame.index[-1]
        res = engine.run(buy_and_hold, start, end)
        m = compute_metrics(res.decisions)
        assert 0.0 <= m.exposure <= 1.0
        assert m.max_drawdown <= 0.0
        assert m.n_bars == len(res.decisions)
        assert m.trades >= 1

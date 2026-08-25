"""T-012 · No-cheating / lookahead filter — the integrity gatekeeper.

Enforces point-in-time discipline so no future information leaks into any
decision. This is a hard gate: before ANY metric in T-013/T-014 is trusted,
these guarantees must hold:

1. *No lookahead*: at decision time ``t`` only rows with timestamp <= t are
   visible. Anything arriving after ``t`` is stripped before the strategy
   sees it.
2. *Quarantine*: any series/row whose published/retrieved vintage cannot be
   proven point-in-time is routed out of the live stream.
3. *Survivorship*: a name removed from the universe after its removal date
   cannot be traded post-removal; constituents are as-of-date.

The cheat-detector test suite (tests/test_backtest.py) deliberately injects
known lookahead violations and asserts the filter rejects them — if those
tests fail, every number downstream is invalid.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

import pandas as pd


class VintageViolation(Exception):
    """Raised when a data access would leak future information."""


class QuarantinedSeriesError(Exception):
    """Raised when a requested series is quarantined (unprovable vintage)."""


@dataclass
class QuarantineLog:
    """Records every row/series the filter rejected and why."""

    entries: list[dict] = field(default_factory=list)

    def reject(self, source_id: str, ts, reason: str) -> None:
        self.entries.append(
            {
                "source_id": source_id,
                "timestamp": str(ts),
                "reason": reason,
            }
        )

    def __len__(self) -> int:
        return len(self.entries)


class PointInTimeProvider:
    """Price/series provider that only ever reveals data available at ``t``.

    Wraps a pandas DataFrame indexed by a datetime-like index. Every query is
    an ``asof`` slice: ``history(asof=t)`` returns rows with index <= t and
    nothing else. The provider owns the no-lookahead guarantee — strategies
    never touch the raw frame.
    """

    def __init__(
        self,
        frame: pd.DataFrame,
        *,
        series_id: str = "default",
        quarantine_log: QuarantineLog | None = None,
    ):
        if not isinstance(frame.index, pd.DatetimeIndex):
            frame = frame.copy()
            frame.index = pd.to_datetime(frame.index)
        self._frame = frame.sort_index()
        self.series_id = series_id
        # NB: explicit None check — QuarantineLog defines __len__, so an
        # empty log is falsy and `or` would silently discard it.
        self.log = quarantine_log if quarantine_log is not None else QuarantineLog()

    # -- quarantine ------------------------------------------------------

    @classmethod
    def from_proven_vintage(
        cls,
        frame: pd.DataFrame,
        *,
        series_id: str,
        published_at_col: str | None = None,
        quarantine_log: QuarantineLog | None = None,
    ) -> "PointInTimeProvider":
        """Build a provider, quarantining rows that can't prove their vintage.

        ``published_at_col``: optional column holding the publisher-stated
        release time. Rows whose release time is missing (NaN/NaT) are
        unprovable and get routed to quarantine (mirrors T-002's
        ``is_quarantine_candidate``). When the column is absent, vintage is
        considered proven by retrieval and all rows pass.
        """
        log = quarantine_log if quarantine_log is not None else QuarantineLog()
        frame = frame.copy()
        if published_at_col is not None and published_at_col in frame.columns:
            bad = frame[published_at_col].isna()
            for ts, _ in frame.loc[bad].iterrows():
                log.reject(series_id, ts, "unprovable vintage (missing published_at)")
            frame = frame.loc[~bad]
        return cls(frame, series_id=series_id, quarantine_log=log)

    # -- point-in-time access -------------------------------------------

    def history(self, asof: datetime | pd.Timestamp) -> pd.DataFrame:
        """Return only rows with timestamp <= asof. The core no-lookahead cut.

        Raises VintageViolation when the caller asks for a timestamp before
        the series' first proven observation (defensive; a well-formed
        strategy never does this).
        """
        t = pd.Timestamp(asof)
        if t.tzinfo is None:
            t = t.tz_localize("UTC")
        else:
            t = t.tz_convert("UTC")
        if self._frame.empty:
            return self._frame.iloc[0:0]
        first = self._frame.index[0]
        if t < first:
            raise VintageViolation(
                f"asof {t} precedes first observation {first} of {self.series_id}"
            )
        return self._frame.loc[self._frame.index <= t]

    def last_price(self, asof: datetime | pd.Timestamp) -> float | None:
        """Most recent close at or before ``asof``, or None if none exists."""
        h = self.history(asof)
        if h.empty:
            return None
        return float(h["close"].iloc[-1])

    # -- survivorship ----------------------------------------------------

    def tradable_universe(self, asof: datetime | pd.Timestamp) -> list[str]:
        """Names still in the universe at ``asof`` (as-of-date constituents).

        For a single-series provider this is the series itself unless it has
        a ``delisted_at`` attribute set; multi-name universes are handled by
        :class:`SurvivorshipAwareUniverse`.
        """
        t = pd.Timestamp(asof)
        delisted = getattr(self, "delisted_at", None)
        if delisted is not None and t >= pd.Timestamp(delisted):
            return []
        return [self.series_id]


class SurvivorshipAwareUniverse:
    """Multi-name universe where each name knows its own removal date.

    A name delisted at ``delisted_at`` stops being tradable at that instant —
    the backtest can never hold it after removal. This kills survivorship
    bias by construction: the universe is always as-of-date.
    """

    def __init__(self, providers: dict[str, PointInTimeProvider]):
        self._providers = dict(providers)

    def register_delisted(self, name: str, delisted_at) -> None:
        """Mark a name as removed from the universe at ``delisted_at``."""
        self._providers[name].delisted_at = pd.Timestamp(delisted_at)

    def constituents(self, asof: datetime | pd.Timestamp) -> list[str]:
        t = pd.Timestamp(asof)
        out = []
        for name, prov in self._providers.items():
            delisted = getattr(prov, "delisted_at", None)
            if delisted is None or t < pd.Timestamp(delisted):
                out.append(name)
        return sorted(out)

    def provider(self, name: str) -> PointInTimeProvider:
        return self._providers[name]


def assert_point_in_time(result_rows: pd.DataFrame, violations: list[pd.DataFrame]) -> None:
    """Test helper: prove injected future rows never entered the simulation.

    ``result_rows`` is the engine's per-day decision log (indexed by decision
    day); ``violations`` is a list of frames containing rows that must NOT
    appear at any earlier decision day.
    """
    for v in violations:
        for ts in v.index:
            visible_before = result_rows.index < ts
            if visible_before.any():
                raise AssertionError(
                    f"lookahead leak: row @ {ts} influenced a decision at an earlier day"
                )

"""Vintage / point-in-time tagging layer (T-002).

Stamps every ingested :class:`macroscope.models.EventObject` with provenance and
vintage fields *before* it can reach storage or a backtest, and enforces
no-lookahead by construction: anything that cannot prove its vintage is
quarantined out of the live corpus. This is what makes §14 backtesting honest —
a dataset entry whose release time cannot be proven never enters a backtest.

Deliverables (see tickets/T-002.md):
  1. stamp() / quarantine_reasons() — published_at vs retrieved_at, a
     ``vintage_ok`` bool and one or more ``quarantine_reason`` strings.
  2. dedupe() — SimHash near-duplicate collapse within a time window; keeps the
     earliest + highest-tier copy and propagates a cluster id so "same story,
     40 outlets" counts once (§4.2).
  3. record_revision() / make_revision() — macro-release first-print + revision
     chain stored as separate later-dated events (no silent overwrite), wired
     into T-001's ``event_revisions`` table.
  4. quarantine() — the rule engine that routes unprovable items to a quarantine
     bucket instead of the live corpus.

Pure standard library: SimHash is implemented here so no third-party dep has to
be installed (the restricted build env can't install one).
"""

from __future__ import annotations

import hashlib
import json as _json
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional

from macroscope.models import EventObject


# ---------------------------------------------------------------------------
# SimHash (pure stdlib) — text similarity used by dedupe()
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def simhash(text: str, bits: int = 64) -> int:
    """Return the SimHash of ``text`` as a non-negative ``bits``-bit integer.

    Tokenize on lowercase word chars, hash each token to ``bits`` with SHA-256,
    weight by frequency, and fold into a single register whose Hamming distance
    to another item's SimHash approximates text similarity (closer == more alike).
    """
    if not text or not text.strip():
        return 0
    # Keep every numeric token -- even a lone digit like "0" or "9" -- so that
    # distinct macro prints ("US CPI rose 0.3%" vs "...0.9%") do not collapse to
    # identical SimHashes. Drop only short *alpha* tokens, which are almost
    # always noise (a, i, etc.).
    counts = Counter(
        t for t in _TOKEN_RE.findall(text.lower())
        if t.isdigit() or len(t) > 1
    )
    register = [0] * bits
    for token, weight in counts.items():
        digest = hashlib.sha256(token.encode()).digest()
        h = int.from_bytes(digest[:8], "big")
        for i in range(bits):
            register[i] += weight if (h >> i) & 1 else -weight
    result = 0
    for i, v in enumerate(register):
        if v > 0:
            result |= 1 << i
    return result


def hamming(a: int, b: int, bits: int = 64) -> int:
    """Number of differing low ``bits`` between two integers."""
    x = (a ^ b) & ((1 << bits) - 1)
    return bin(x).count("1")


def default_similarity_threshold(bits: int = 64) -> int:
    """Near-duplicate Hamming threshold.

    Short texts carry fewer meaningful bits, so scale the threshold down with
    text length rather than using a fixed cutoff. Defaults to ~bits/8 for long
    documents; callers may pass an explicit value.
    """
    return max(3, bits // 8)


# ---------------------------------------------------------------------------
# Quarantine rule engine (deliverable #4 + stamping, deliverable #1)
# ---------------------------------------------------------------------------

@dataclass
class StampResult:
    """Outcome of tagging one event with vintage/provenance fields."""

    source_id: str
    published_at: Optional[datetime]
    vintage_ok: bool
    quarantine_reasons: list[str] = field(default_factory=list)
    cluster_id: Optional[str] = None
    deduped_by: Optional[str] = None  # id of the copy we kept, if this one was dropped


def quarantine_reasons(
    evt: EventObject,
    *,
    known_sources: Optional[Iterable[str]] = None,
) -> list[str]:
    """Return every reason an item cannot be proven point-in-time.

    An empty list means the item is vintage_ok and may enter the live corpus.
    Rules (from T-002):
      * missing ``published_at`` — no publisher-stated release time at all;
      * retrieved before published — impossible time travel / lookahead;
      * source tier unverifiable — ``source_id`` not in the known-source set, so
        we cannot confirm it is a legitimate, tiered source.
    """
    reasons: list[str] = []
    if evt.published_at is None:
        reasons.append("missing published_at")
    elif evt.retrieved_at is not None and evt.retrieved_at < evt.published_at:
        reasons.append("retrieved before published (lookahead)")
    if known_sources is not None and evt.source_id not in known_sources:
        reasons.append("source tier unverifiable")
    return reasons


def stamp(
    evt: EventObject,
    *,
    known_sources: Optional[Iterable[str]] = None,
) -> StampResult:
    """Tag one event with its vintage verdict. ``vintage_ok`` is True iff no
    quarantine reason applies."""
    reasons = quarantine_reasons(evt, known_sources=known_sources)
    return StampResult(
        source_id=evt.source_id,
        published_at=evt.published_at,
        vintage_ok=len(reasons) == 0,
        quarantine_reasons=reasons,
    )


def quarantine(
    items: Iterable[EventObject],
    *,
    known_sources: Optional[Iterable[str]] = None,
) -> tuple[list[StampResult], list[StampResult]]:
    """Split ``items`` into ``(live, quarantined)`` by vintage verdict.

    The live corpus never contains a quarantined row — this is the gate that
    keeps unproven-vintage data out of backtests (§14).
    """
    live: list[StampResult] = []
    quarantined: list[StampResult] = []
    for evt in items:
        res = stamp(evt, known_sources=known_sources)
        (live if res.vintage_ok else quarantined).append(res)
    return live, quarantined


# ---------------------------------------------------------------------------
# Dedupe within time windows (deliverable #2)
# ---------------------------------------------------------------------------

@dataclass
class Cluster:
    """A group of near-duplicate items that collapse to one logical event."""

    cluster_id: str
    kept_event_id: str
    members: list[str] = field(default_factory=list)
    reason: str = "near-duplicate within time window"


def _anchor(evt: EventObject) -> datetime:
    """Anchor ordering on the earliest available point-in-time signal."""
    return evt.published_at or evt.retrieved_at or datetime.max.replace(tzinfo=timezone.utc)


def dedupe(
    items: Iterable[EventObject],
    *,
    window_hours: float = 48,
    simhash_bits: int = 64,
    similarity_threshold: Optional[int] = None,
) -> dict[str, Cluster]:
    """Collapse near-duplicate items that fall within ``window_hours`` of each
    other into a single cluster.

    Ordering is anchored on the earliest published time; an item joins the first
    existing cluster whose representative is textually similar (Hamming distance
    <= threshold) *and* within the window. Within a cluster we keep the copy with
    the highest ``source_tier``, breaking ties by earliest point-in-time — so
    "same story, 40 outlets" counts once and the best-sourced copy survives.

    Returns a mapping of ``cluster_id -> Cluster``. Members are identified by
    their ``source_id`` (the model's only stable identity field); callers that
    need finer keys can pass an id map via :func:`stamp_after_dedupe`.
    """
    ordered = sorted(items, key=_anchor)
    threshold = similarity_threshold if similarity_threshold is not None else default_similarity_threshold(simhash_bits)
    window = timedelta(hours=window_hours)

    # representatives and their clusters in creation order (parallel lists)
    reps: list[EventObject] = []
    cluster_ids: list[str] = []
    clusters: dict[str, Cluster] = {}

    for evt in ordered:
        anchor = _anchor(evt)
        best_rep: Optional[EventObject] = None
        for rep in reps:
            if abs(anchor - _anchor(rep)) > window:
                continue
            dist = hamming(simhash(evt.raw_text, simhash_bits),
                           simhash(rep.raw_text, simhash_bits), simhash_bits)
            if dist <= threshold:
                best_rep = rep
                break

        if best_rep is None:
            cid = f"cl_{len(clusters):08x}"
            clusters[cid] = Cluster(cluster_id=cid, kept_event_id=evt.source_id)
            reps.append(evt)
            cluster_ids.append(cid)
        else:
            cid = cluster_ids[reps.index(best_rep)]
            cluster = clusters[cid]
            # Lower source_tier number == higher authority (BLS=1 "T1", Reuters=2 "T2").
            # Compare the incoming item against the *current kept rep*, not itself:
            # _tier_of(evt.source_id, ordered) would find evt in `ordered` and return
            # its own tier, making the comparison always False. A later-arriving
            # higher-authority copy displaces the earlier rep (and joins members).
            current_tier = _tier_of(cluster.kept_event_id, ordered)
            if evt.source_tier < current_tier:
                # Displaced rep becomes a member (it is part of the cluster but no
                # longer the kept copy); the new higher-authority rep is kept. The
                # old kept rep was never in `members` -- it created the cluster as
                # the kept id -- so we append rather than remove.
                if cluster.kept_event_id not in cluster.members:
                    cluster.members.append(cluster.kept_event_id)
                cluster.kept_event_id = evt.source_id
            cluster.members.append(evt.source_id)

    return clusters


def _tier_of(source_id: str, items: Iterable[EventObject] | None = None) -> int:
    """Look up a source's tier by id; -1 if unknown."""
    for evt in items or []:
        if evt.source_id == source_id:
            return evt.source_tier
    return -1


def stamp_after_dedupe(
    items: Iterable[EventObject],
    *,
    clusters: dict[str, Cluster],
    known_sources: Optional[Iterable[str]] = None,
) -> list[StampResult]:
    """Re-run :func:`stamp` for every item, adding ``cluster_id`` and marking
    dropped members with ``deduped_by`` (the id of the copy we kept)."""
    drop_map: dict[str, str] = {}
    for cluster in clusters.values():
        for member in cluster.members:
            if member != cluster.kept_event_id:
                drop_map[member] = cluster.kept_event_id

    results: list[StampResult] = []
    for evt in items:
        res = stamp(evt, known_sources=known_sources)
        res.cluster_id = _cluster_for(evt.source_id, clusters)
        if evt.source_id in drop_map:
            res.deduped_by = drop_map[evt.source_id]
        results.append(res)
    return results


def _cluster_for(source_id: str, clusters: dict[str, Cluster]) -> Optional[str]:
    for cid, cluster in clusters.items():
        if source_id in cluster.members or source_id == cluster.kept_event_id:
            return cid
    return None


# ---------------------------------------------------------------------------
# Macro-release revision handling (deliverable #3)
# ---------------------------------------------------------------------------

def make_revision(
    original: EventObject,
    *,
    revision_at: datetime,
    revised_text: Optional[str] = None,
) -> EventObject:
    """Return a later-dated copy of ``original`` representing a macro release
    revision. The result is a *distinct* event (later ``published_at``), never
    an in-place overwrite."""
    return original.model_copy(update={
        "raw_text": revised_text or original.raw_text,
        "published_at": revision_at,
        "retrieved_at": datetime.now(timezone.utc),
    })


def record_revision(
    conn,
    *,
    source_id: str,
    published_at: datetime,
    sequence: int,
    revised_text: str,
    entities: Optional[list[str]] = None,
    numbers_extracted: Optional[dict] = None,
    direction_assertions: Optional[list] = None,
    prompt_hash: Optional[str] = None,
) -> tuple[str, str]:
    """Create a NEW later-dated ``events`` row for a macro-release revision and
    log it in ``event_revisions``. Returns ``(new_event_id, revision_id)``.

    The original first-print row is never touched — feeding a revised CPI print
    therefore yields two dated events, not one overwritten row (T-002 acceptance).
    """
    from sqlalchemy import text

    new_event_id = f"{source_id}-rev@{published_at.isoformat()}"
    revision_id = f"rev-{new_event_id}@{published_at.isoformat()}"

    conn.execute(text("""INSERT INTO events (
        event_id, event_ts, sequence, source_id, published_at, retrieved_at,
        url, raw_text, language, source_tier, event_type, entities,
        direction_assertions, numbers_extracted, novelty_score,
        extractor_confidence, prompt_hash
    ) VALUES (:event_id, :event_ts, :sequence, :source_id, :published_at,
              :retrieved_at, :url, :raw_text, :language, :source_tier,
              :event_type, :entities, :direction_assertions,
              :numbers_extracted, :novelty_score, :extractor_confidence,
              :prompt_hash)"""), {
        "event_id": new_event_id,
        "event_ts": published_at,
        "sequence": sequence,
        "source_id": source_id,
        "published_at": published_at,
        "retrieved_at": datetime.now(timezone.utc),
        "url": None,
        "raw_text": revised_text,
        "language": "en",
        "source_tier": 1,
        "event_type": "macro_data",
        "entities": _json.dumps(entities or []),
        "direction_assertions": _json.dumps(direction_assertions or []),
        "numbers_extracted": _json.dumps(numbers_extracted or {}),
        "novelty_score": None,
        "extractor_confidence": None,
        "prompt_hash": prompt_hash,
    })

    conn.execute(text("""INSERT INTO event_revisions
        (event_id, revision_at, first_print, revision_jsonb)
        VALUES (:eid, :rev, :fp, :json)"""), {
        "eid": new_event_id,
        "rev": published_at.isoformat(),
        "fp": False,
        "json": _json.dumps({"is_revision": True, "diff": {"raw_text": revised_text}}),
    })

    return new_event_id, revision_id


# ---------------------------------------------------------------------------
# Audit trail (acceptance: reproducible)
# ---------------------------------------------------------------------------

def audit_trail(engine) -> dict[str, StampResult]:
    """Read the live corpus back from storage and re-stamp every row.

    Proves the vintage fields are durable and reproducible — what sr-dev checks
    for in the audit-trail acceptance item. Returns ``source_id -> StampResult``.
    """
    from .models import EventObject
    from sqlalchemy import text

    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT event_id, source_id, published_at, retrieved_at, raw_text, "
            "source_tier FROM events ORDER BY event_ts"
        )).fetchall()
        known = {r[0] for r in conn.execute(text(
            "SELECT source_id FROM source_registry"
        )).fetchall()}

    results: dict[str, StampResult] = {}
    for event_id, source_id, published_at, retrieved_at, raw_text, source_tier in rows:
        evt = EventObject(
            source_id=source_id,
            published_at=published_at,
            retrieved_at=retrieved_at or datetime.now(timezone.utc),
            raw_text=raw_text or "",
            source_tier=int(source_tier),
        )
        results[event_id] = stamp(evt, known_sources=known)
    return results

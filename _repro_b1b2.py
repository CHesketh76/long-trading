from datetime import datetime, timedelta, timezone
from macroscope.models import EventObject
from macroscope.vintage import dedupe, simhash, hamming, _tier_of


def evt(sid, pub, text="", tier=1):
    return EventObject(source_id=sid, published_at=pub, raw_text=text, source_tier=tier)


base = datetime(2026, 8, 20, 13, 0, tzinfo=timezone.utc)

# ---- B2: "0.3%" vs "0.9%" collapse? ----
a = evt("r1", base, "US CPI rose 0.3% in July", tier=2)
b = evt("r2", base + timedelta(minutes=5), "US CPI rose 0.9% in July", tier=2)
h_a = simhash(a.raw_text)
h_b = simhash(b.raw_text)
print("B2 hamming:", hamming(h_a, h_b), "(0 == identical -> BUG)")
clusters = dedupe([a, b])
kept = next(iter(clusters.values())).kept_event_id
print("B2 clusters:", len(clusters), "-> kept:", kept)
print("B2 verdict: COLLAPSED (bug)" if len(clusters) == 1 else "B2 verdict: separate (good)")

# ---- B1: later tier-1 must displace earlier tier-3 rep ----
c = evt("early_t3", base - timedelta(minutes=10), "US CPI rose 0.5% in July", tier=3)
d = evt("late_t1", base + timedelta(minutes=2), "US CPI rose 0.5% in July", tier=1)
cl2 = next(iter(dedupe([c, d]).values()))
print("\nB1 kept:", cl2.kept_event_id, "(expected 'late_t1')")
print("B1 verdict: WRONG-KEPT (bug)" if cl2.kept_event_id == "early_t3" else "B1 verdict: correct")

# ---- B1 dead-code proof ----
print("\n_sanity _tier_of('late_t1',[c,d]) =", _tier_of("late_t1", [c, d]),
      "-> '1<1' never true, so no upgrade ever fires")

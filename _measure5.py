import hashlib
from collections import Counter


def _sh(tok, bits):
    digest = hashlib.sha256(tok.encode()).digest()
    return int.from_bytes(digest[:8], "big")


def simhash(text, bits=64, scheme="keep_digits"):
    if not text or not text.strip():
        return 0
    import re
    raw = re.findall(r"[a-z0-9.]+", text.lower())
    if scheme == "drop_single":
        toks = [t for t in raw if len(t) > 1]
    elif scheme == "keep_digits":
        toks = [t for t in raw]  # keep everything incl single digits
    elif scheme == "atomic_num":
        toks = [t for t in raw]  # numbers already atomic via '.' in regex
    counts = Counter(toks)
    register = [0] * bits
    for token, weight in counts.items():
        h = _sh(token, bits)
        for i in range(bits):
            register[i] += (weight if (h >> i) & 1 else -weight)
    result = 0
    for i, v in enumerate(register):
        if v > 0:
            result |= 1 << i
    return result


def hamming(a, b, bits=64):
    x = (a ^ b) & ((1 << bits) - 1)
    return bin(x).count("1")


CASES = [
    ("identical", "US CPI rose 0.3% in July", "US CPI rose 0.3% in July"),
    ("percent-variant (should COLLAPSE)", "US CPI rose 0.3% in July", "US CPI rose 0.3 percent in July"),
    ("0.3 vs 0.9 (should SEPARATE)", "US CPI rose 0.3% in July", "US CPI rose 0.9% in July"),
    ("0.3 vs 1.3 (should SEPARATE)", "US CPI rose 0.3% in July", "US CPI rose 1.3% in July"),
    ("unrelated (SEPARATE)", "US CPI rose 0.3% in July", "Fed hikes rates by 75bps"),
]

for scheme in ["drop_single", "keep_digits", "atomic_num"]:
    print(f"\n=== scheme: {scheme} ===")
    for name, a, b in CASES:
        dist = hamming(simhash(a, scheme=scheme), simhash(b, scheme=scheme))
        verdict = "COLLAPSE" if dist <= 8 else "separate"
        flag = ""
        if "percent-variant" in name and dist > 8:
            flag = "  <-- FAILS (should collapse)"
        if "0.3 vs 0.9" in name and dist <= 8:
            flag = "  <-- FAILS (should separate)"
        print(f"  {dist:>2}  {verdict:<9} {name}{flag}")

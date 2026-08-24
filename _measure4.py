import hashlib
from collections import Counter


def simhash(text, bits=64):
    if not text or not text.strip():
        return 0
    # whole numbers (incl. decimals) are atomic tokens; alpha words kept too
    counts = Counter(t for t in _TOKEN_RE.findall(text.lower()))
    register = [0] * bits
    for token, weight in counts.items():
        digest = hashlib.sha256(token.encode()).digest()
        h = int.from_bytes(digest[:8], "big")
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


import re
_TOKEN_RE = re.compile(r"[a-z0-9.]+")


def d(a, b):
    return hamming(simhash(a), simhash(b))


print("identical            :", d("US CPI rose 0.3% in July", "US CPI rose 0.3% in July"))
print("'percent' variant    :", d("US CPI rose 0.3% in July", "US CPI rose 0.3 percent in July"))
print("0.3% vs 0.9%         :", d("US CPI rose 0.3% in July", "US CPI rose 0.9% in July"))
print("0.3% vs 1.3%         :", d("US CPI rose 0.3% in July", "US CPI rose 1.3% in July"))
print("unrelated            :", d("US CPI rose 0.3% in July", "Fed hikes rates by 75bps"))

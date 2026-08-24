import re, hashlib
from collections import Counter

_ORIG = re.compile(r'([a-z]+(?:\.[a-z]+)*|[0-9]+(?:\.[0-9]+)*)')


def _sh(tok, bits):
    digest = hashlib.sha256(tok.encode()).digest()
    return int.from_bytes(digest[:8], "big")


def orig_simhash(text, bits=64):
    if not text or not text.strip():
        return 0
    counts = Counter(t for t in _ORIG.findall(text.lower()) if len(t) > 1)
    if not counts:
        return 0
    total = sum(counts.values())
    bits_vec = [0] * bits
    for tok, cnt in counts.items():
        h = _sh(tok, bits)
        for i in range(bits):
            if (h >> i) & 1:
                bits_vec[i] += cnt
            else:
                bits_vec[i] -= cnt
    return sum(1 << i for i in range(bits) if bits_vec[i] >= total / 2)


def orig_hamming(a, b):
    return bin(a ^ b).count("1")


A = "US CPI rose 0.3% in July"
B = "US CPI rose 0.3 percent in July"
C = "US CPI rose 0.9% in July"

print("=== ORIGINAL (git HEAD) tokenizer ===")
print("percent-variant A vs B:", orig_hamming(orig_simhash(A), orig_simhash(B)), "(threshold=8)")
print("0.3 vs 0.9   A vs C:", orig_hamming(orig_simhash(A), orig_simhash(C)))

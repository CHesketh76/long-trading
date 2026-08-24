from macroscope.vintage import simhash, hamming


def d(a, b):
    return hamming(simhash(a), simhash(b))


A = "US CPI rose 0.3% in July"
B = "US CPI rose 0.3 percent in July"
C = "US CPI rose 0.9% in July"

print("percent-variant (must COLLAPSE, <=8):", d(A, B))
print("0.3 vs 0.9   (must SEPARATE, >8)   :", d(A, C))
print()
print("identical:", d(A, A))
print("unrelated:", d("US CPI rose 0.3% in July", "gold rallies on rate cut fears"))

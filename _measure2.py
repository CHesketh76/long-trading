from macroscope.vintage import simhash, hamming


def d(a, b):
    return hamming(simhash(a), simhash(b))


# With lone-digit filter: single digits dropped from token bag.
print("identical            :", d("US CPI rose 0.3% in July", "US CPI rose 0.3% in July"))
print("'percent' variant    :", d("US CPI rose 0.3% in July", "US CPI rose 0.3 percent in July"))
print("0.3% vs 0.9%         :", d("US CPI rose 0.3% in July", "US CPI rose 0.9% in July"))
print("0.3% vs 1.3%         :", d("US CPI rose 0.3% in July", "US CPI rose 1.3% in July"))
print("unrelated            :", d("US CPI rose 0.3% in July", "Fed hikes rates by 75bps"))

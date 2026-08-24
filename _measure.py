from macroscope.vintage import simhash, hamming, default_similarity_threshold


def d(a, b):
    return hamming(simhash(a), simhash(b))


print("default threshold:", default_similarity_threshold(64))
print()
# collapse cases (must stay collapsed: dist <= threshold)
print("identical vs identical :", d("US CPI rose 0.3% in July", "US CPI rose 0.3% in July"))
print("'percent' variant       :", d("US CPI rose 0.3% in July", "US CPI rose 0.3 percent in July"))
print()
# discriminating case (must stay SEPARATE: dist > threshold)
print("0.3% vs 0.9%            :", d("US CPI rose 0.3% in July", "US CPI rose 0.9% in July"))
print("0.3% vs 1.3%            :", d("US CPI rose 0.3% in July", "US CPI rose 1.3% in July"))
print("0.3% vs 0.4%            :", d("US CPI rose 0.3% in July", "US CPI rose 0.4% in July"))
print()
# unrelated (should be far)
print("unrelated               :", d("US CPI rose 0.3% in July", "Fed hikes rates by 75bps"))

import re

_ORIG = re.compile(r'([a-z]+(?:\.[a-z]+)*|[0-9]+(?:\.[0-9]+)*)')


def orig_tokens(text):
    return [t for t in _ORIG.findall(text.lower()) if len(t) > 1]


def new_tokens(text):
    return list(_ORIG.findall(text.lower()))


A = "US CPI rose 0.3% in July"
C = "US CPI rose 0.9% in July"

print("ORIGINAL tokenizer token bags:")
print("  A:", orig_tokens(A))
print("  C:", orig_tokens(C))
print("  identical?", orig_tokens(A) == orig_tokens(C))
print()
print("NEW (keep digits) token bags:")
print("  A:", new_tokens(A))
print("  C:", new_tokens(C))
print()

# sr-dev's actual example of single-digit dropping:
S1 = "US CPI rose 3% in July"
S2 = "US CPI rose 9% in July"
print("sr-dev's single-digit example:")
print("  '3%' orig:", orig_tokens(S1), "| '9%' orig:", orig_tokens(S2))
print("  identical under original?", orig_tokens(S1) == orig_tokens(S2))

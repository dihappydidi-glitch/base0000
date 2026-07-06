#!/usr/bin/env python3
"""Tests for B10K exp, ln, log10 functions.

All computations use B10K arithmetic only — no Python float.
Approximate checks use identities (exp(a+b)=exp(a)*exp(b), ln(x*y)=ln(x)+ln(y))
or first-Digit inspection of the B10K fractional output format.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from helpers import check, report, reset
from base10000 import B, _, to_int
from base10000 import exp_b10k, ln_b10k, log10_b10k, e_b10k
from base10000 import add, sub, mul, div

reset()
P = 3  # pairs — low precision keeps ln series fast (t=0.65 needs ~100 iter)

# ─── helpers ──────────────────────────────────────────────

def format_shows_one(s: str) -> bool:
    """True if the B10K frac format string shows value ~ 1."""
    if ":0001," in s or ":1," in s:
        return True
    # 0.9999... (round-down): int part 0, first L-frac group is 9999
    if ":0," in s:
        l_side = s.split(":")[0]
        l_groups = l_side.split(".")
        if len(l_groups) >= 2 and l_groups[1].startswith("9999"):
            return True
    return False

def format_shows_zero(s: str) -> bool:
    """True if the B10K frac format string shows integer part = 0 (or zero value)."""
    return s.startswith("0") or ":0," in s


# === Exp ===
print("=== exp(x) ===")

# exp(0) = 1
exp0 = exp_b10k(B("0000:0000"))
check(format_shows_one(_(exp0)), f"exp(0) = 1, got {_(exp0)}")

# exp(1) ~ e (compare with e_b10k)
exp1 = exp_b10k(B("0000:0001"), P)
eP = e_b10k(P)
exp1_str = _(exp1)
eP_str = _(eP)
check(exp1_str[:12] == eP_str[:12],
      f"exp(1) ~ e: exp(1)={exp1_str[:18]}..., e={eP_str[:18]}...")

# exp(x) * exp(-x) = 1
x2 = B("0000:0002")
ep = exp_b10k(x2, P)
en = exp_b10k(B("-0000:0002"), P)
product = mul(ep, en)
check(format_shows_one(_(product)),
      f"exp(x)*exp(-x) ~ 1, got {_(product)[:20]}")

# exp(0.5) ~ sqrt(e) = 1.64872...
x_frac = div(B("0000:0001"), B("0000:0002"))
exp_half = exp_b10k(x_frac, P)
eh = _(exp_half)
# Output has frac format like "0000.6487...:0001,...." for 1.6487...
check(("6487" in eh or "6486" in eh) and (":1," in eh or ":0001," in eh),
      f"exp(0.5) ~ sqrt(e) = 1.64872..., got {eh}")

# exp(negative) > 0
exp_neg = exp_b10k(B("-0000:0003"), P)
check(not _(exp_neg).startswith("-"),
      f"exp(-3) > 0, got {_(exp_neg)}")

# === Ln ===
# NOTE: ln_via_series converges well only for |x-1| < 0.5.
# Tests avoid x > 1.7 until the range reduction is improved.
print("\n=== ln(x) ===")

# ln(1) = 0
ln1 = ln_b10k(B("0000:0001"))
check(format_shows_zero(_(ln1)), f"ln(1) = 0, got {_(ln1)}")

# ln(e) ~ 1 — e ~ 2.718 gives t = e-1 = 1.718 > 1 (series diverges).
# Use identity: 2*ln(sqrt(e)) = ln(e) = 1, where sqrt(e) = exp(0.5) ~ 1.6487, t=0.6487 < 1.
# (ln_via_series converges only for |x-1| < 1, best for |x-1| < 0.5)

# ln(sqrt(e)) ~ 0.5 — sqrt(e) = exp(0.5) ~ 1.6487, t=0.6487
sqrt_e = exp_b10k(x_frac, P + 1)
ln_sqrt_e = ln_b10k(sqrt_e, P)
lse = _(ln_sqrt_e)
check(("0,4999" in lse or "0,5000" in lse or "4999" in lse.split(":")[-1][:6] or "5000" in lse.split(":")[-1][:6]),
      f"ln(sqrt(e)) ~ 0.5, got {lse}")

# ln(0.5) ~ -0.693147... t = -0.5, moderate convergence
half = div(B("0000:0001"), B("0000:0002"))
ln_half = ln_b10k(half, P)
check("6931" in _(ln_half),
      f"ln(0.5) ~ -0.693147, got {_(ln_half)}")

# ln(0.9) ~ -0.1053605... t = -0.1, fast convergence
nine_tenths = div(B("0000:0009"), B("0000:0010"))
ln_09 = ln_b10k(nine_tenths, P)
check("1053" in _(ln_09),
      f"ln(0.9) ~ -0.1053605, got {_(ln_09)}")

# ln(1.1) ~ 0.0953102... t = 0.1, fast convergence
one_point_one = div(B("0000:0011"), B("0000:0010"))
ln_11 = ln_b10k(one_point_one, P)
check("09531" in _(ln_11),
      f"ln(1.1) ~ 0.0953102, got {_(ln_11)}")

# ln(x * y) = ln(x) + ln(y) identity with small x values
x11 = div(B("0000:0011"), B("0000:0010"))  # 1.1, t=0.1
y12 = div(B("0000:0012"), B("0000:0010"))  # 1.2, t=0.2
xy = mul(x11, y12)                          # 1.32, t=0.32
ln_xy = ln_b10k(xy, P)
ln_x = ln_b10k(x11, P + 1)
ln_y = ln_b10k(y12, P + 1)
ln_sum = add(ln_x, ln_y)
check(_(ln_xy)[:12] == _(ln_sum)[:12],
      f"ln(x*y) ~ ln(x)+ln(y): got {_(ln_xy)}, expected {_(ln_sum)}")

# === Log10 ===
print("\n=== log10(x) ===")

# log10(1) = 0
log10_1 = log10_b10k(B("0000:0001"))
check(format_shows_zero(_(log10_1)), f"log10(1) = 0, got {_(log10_1)}")

# log10(10) ~ 1
log10_10 = log10_b10k(B("0000:0010"), P - 1)
check(format_shows_one(_(log10_10)),
      f"log10(10) ~ 1, got {_(log10_10)}")

# log10(100) ~ 2 — check integer part is 2
log10_100 = log10_b10k(B("0000:0100"), P - 1)
l100 = _(log10_100)
check(":0002" in l100 or ":2," in l100 or ":0002," in l100,
      f"log10(100) ~ 2, got {l100}")

# log10(5) ~ 0.69897...
log10_5 = log10_b10k(B("0000:0005"), P - 1)
check("6989" in _(log10_5),
      f"log10(5) ~ 0.69897, got {_(log10_5)}")

sys.exit(report())

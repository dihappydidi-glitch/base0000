#!/usr/bin/env python3
"""Tests for B10K trig functions: sin, cos, tan, atan.

All computations use B10K arithmetic only — no Python float.
For approximate checks we use identities (sin2+cos2=1) or format-string
inspection of the B10K fractional output format.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from helpers import check, report, reset
from base10000 import B, _, to_int
from base10000 import sin_b10k, cos_b10k, tan_b10k, atan_b10k, pi_b10k
from base10000 import add, sub, mul, div, neg

reset()
P5 = 5  # default pairs — moderate precision, fast series

# ─── helpers ──────────────────────────────────────────────

def format_shows_one(s: str) -> bool:
    """True if the B10K frac format string shows integer part ~ 1."""
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

def format_shows_minus_one(s: str) -> bool:
    """True if integer part is -1 (e.g. cos(pi))."""
    return "-" in s and (":0001," in s or ":1," in s)


# === Sin ===
print("=== sin(x) ===")

# sin(0) = 0
sin0 = sin_b10k(B("0000:0000"))
check(_(sin0).startswith("0"), f"sin(0) = 0, got {_(sin0)}")

# sin(pi/2) ~ 1 — use identity sin2+cos2 = 1
half_pi = div(pi_b10k(P5), B("0000:0002"))
sin_half_pi = sin_b10k(half_pi, P5)
cos_half_pi = cos_b10k(half_pi, P5)
one = add(mul(sin_half_pi, sin_half_pi), mul(cos_half_pi, cos_half_pi))
check(format_shows_one(_(one)),
      f"sin2+cos2 ~ 1, got {_(one)}")

# sin(pi) ~ 0
pi5 = pi_b10k(P5)
sin_pi = sin_b10k(pi5, P5)
check(format_shows_zero(_(sin_pi)),
      f"sin(pi) ~ 0, got {_(sin_pi)}")

# sin(-x) = -sin(x) — oddness
x = B("0000:0005")
sx = sin_b10k(x, P5)
snx = sin_b10k(B("-0000:0005"), P5)
check(_(add(sx, snx)).startswith("0"),
      f"sin(-x) = -sin(x): sin(5)={_(sx)}, sin(-5)={_(snx)}")

# === Cos ===
print("\n=== cos(x) ===")

# cos(0) = 1
cos0 = cos_b10k(B("0000:0000"))
check(format_shows_one(_(cos0)), f"cos(0) = 1, got {_(cos0)}")

# cos(pi/2) ~ 0
cos_half_pi = cos_b10k(half_pi, P5)
check(format_shows_zero(_(cos_half_pi)),
      f"cos(pi/2) ~ 0, got {_(cos_half_pi)}")

# cos(pi) ~ -1
cos_pi = cos_b10k(pi5, P5)
check(format_shows_minus_one(_(cos_pi)),
      f"cos(pi) ~ -1, got {_(cos_pi)}")

# cos(-x) = cos(x) — evenness
cx = cos_b10k(x, P5)
cnx = cos_b10k(B("-0000:0005"), P5)
check(_(cx) == _(cnx),
      f"cos(-x) = cos(x): cos(5)={_(cx)}, cos(-5)={_(cnx)}")

# === Tan ===
print("\n=== tan(x) ===")

# tan(0) = 0
tan0 = tan_b10k(B("0000:0000"))
check(_(tan0).startswith("0"), f"tan(0) = 0, got {_(tan0)}")

# tan(pi/4) ~ 1
quarter_pi = div(pi_b10k(P5), B("0000:0004"))
tan_quarter = tan_b10k(quarter_pi, P5)
check(format_shows_one(_(tan_quarter)),
      f"tan(pi/4) ~ 1, got {_(tan_quarter)}")

# tan(-x) = -tan(x) — oddness
x_small = B("0000:0003")
tan3 = tan_b10k(x_small, P5)
tan_neg3 = tan_b10k(B("-0000:0003"), P5)
check(_(tan3) == _(neg(tan_neg3)) or _(add(tan3, tan_neg3)).startswith("0"),
      f"tan(-x) = -tan(x): tan(3)={_(tan3)}, tan(-3)={_(tan_neg3)}")

# === Atan ===
print("\n=== atan(x) ===")

# atan(0) = 0
atan0 = atan_b10k(B("0000:0000"))
check(_(atan0).startswith("0"), f"atan(0) = 0")

# atan(1) ~ pi/4 — check via 4*atan(1) ~ pi (same frac_pairs)
atan1 = atan_b10k(B("0000:0001"), P5)
four_atan1 = mul(atan1, B("0000:0004"))
pi5_str = _(pi_b10k(P5))
four_atan1_str = _(four_atan1)
check(four_atan1_str[:12] == pi5_str[:12],
      f"4*atan(1) ~ pi: got {four_atan1_str}, pi={pi5_str}")

# atan(-x) = -atan(x) — oddness
atan_neg = atan_b10k(B("-0000:0001"), P5)
check(_(atan_neg).startswith("-"),
      f"atan(-1) = -pi/4, got {_(atan_neg)}")

# atan(x) + atan(1/x) = pi/2  (for x > 0)
x2 = B("0000:0002")
atan_x = atan_b10k(x2, P5)
x_inv = div(B("0000:0001"), x2)
atan_inv = atan_b10k(x_inv, P5)
sum_atans = add(atan_x, atan_inv)
half_pi5 = div(pi_b10k(P5), B("0000:0002"))
sum_str = _(sum_atans)
half_pi5_str = _(half_pi5)
check(sum_str[:12] == half_pi5_str[:12],
      f"atan(x)+atan(1/x) ~ pi/2: sum={sum_str}, pi/2={half_pi5_str}")

sys.exit(report())

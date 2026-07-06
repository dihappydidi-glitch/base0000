#!/usr/bin/env python3
"""Tests for B10K constants: pi, e."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from helpers import check, report, reset
from base10000 import B, _, format_num
from base10000 import pi_b10k, e_b10k

reset()

# === Pi ===
print("=== pi (Machin) ===")

# pi(10) should give ~80 digits of pi
p10 = pi_b10k(10)
p_str = _(p10)
# B10K frac format: 0000.1415.3589.3846:0003,.9265.7932.2643...
# Integer part shows as ':0003,'
check(":0003," in p_str,
      f"pi(10) integer part = 3, got {p_str[:30]}")
# First L-side fractional group = 1415 (pi = 3.1415...)
check("1415" in p_str,
      f"pi(10) first 4 frac digits = 1415, got {p_str[:40]}")
# First R-side fractional group = 9265 (next 4 digits)
check(":0003,.9265" in p_str,
      f"pi(10) next 4 frac digits = 9265, got {p_str[:50]}")

# Verify default precision works
p_def = pi_b10k()
check(len(_(p_def)) > 20, f"pi() default precision > 20 chars: {len(_(p_def))}")

# pi(3) — very low precision check
p3 = pi_b10k(3)
p3_str = _(p3)
check(":0003," in p3_str, f"pi(3) int part = 3, got {p3_str}")
check("1415" in p3_str, f"pi(3) starts 1415, got {p3_str}")

# pi(1) — minimal: ~8 digits
p1 = pi_b10k(1)
p1_str = _(p1)
check(":0003," in p1_str or ":3," in p1_str,
      f"pi(1) int part ~ 3, got {p1_str}")

print("\n=== e (Euler) ===")

# e(5) should give 40 digits of e
e5 = e_b10k(5)
e_str = _(e5)
# e = 2.7182818284590452353602874713526624977572...
# B10K frac format: 0000.7182.8182.8459:0002,.0452.3536.0287...
# Integer part = 2
check(":0002," in e_str,
      f"e(5) integer part = 2, got {e_str[:30]}")
# First L groups: 7182 8182 8459 (e = 2.71828 1828 4590 ...)
check("7182" in e_str,
      f"e(5) first 4 frac digits = 7182, got {e_str[:40]}")
# First R group = 8182, second R group = 0452
check(":0002,.8182" in e_str,
      f"e(5) next 4 frac digits = 8182, got {e_str[:50]}")
check("0452" in e_str,
      f"e(5) has 0452 group, got {e_str[:60]}")

# e(1) — minimal check
e1 = e_b10k(1)
e1_str = _(e1)
check("7182" in e1_str or ":0002," in e1_str,
      f"e(1) ~ 2.718, got {e1_str}")

# e(0) — degenerate case (should still produce something reasonable)
e0 = e_b10k(0)
e0_str = _(e0)
check(len(e0_str) > 0, f"e(0) produces output: {e0_str}")

# Verify defaults
e_def = e_b10k()
check(len(_(e_def)) > 15, f"e() default precision > 15 chars: {len(_(e_def))}")

sys.exit(report())

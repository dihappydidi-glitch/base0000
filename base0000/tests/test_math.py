#!/usr/bin/env python3
"""Tests for B10K math functions: fact, gcd, lcm, sqrt, fib, shift."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from helpers import check, check_eq, check_int, report, reset
from base10000 import B, _, to_int, format_num
from base10000 import fact, gcd, lcm, isqrt, sqrt_b10k, fib_b10k
from base10000 import shift_left, shift_right

reset()

# === Factorial ===
print("=== Факториал ===")
check_int(fact(B("0000:0000")), 1, "0! = 1")
check_int(fact(B("0000:0001")), 1, "1! = 1")
check_int(fact(B("0000:0005")), 120, "5! = 120")
check_int(fact(B("0000:0006")), 720, "6! = 720")
check_int(fact(B("0000:0010")), 3628800, "10! = 3628800")
check_int(fact(B("0000:0020")), 2432902008176640000, "20! = 2432902008176640000")

# === GCD / LCM ===
print("\n=== НОД / НОК ===")
check_int(gcd(B("0000:0012"), B("0000:0008")), 4, "gcd(12,8) = 4")
check_int(gcd(B("0000:0017"), B("0000:0005")), 1, "gcd(17,5) = 1")
check_int(gcd(B("0000:0000"), B("0000:0005")), 5, "gcd(0,5) = 5")
check_int(gcd(B("0000:0012"), B("0000:0000")), 12, "gcd(12,0) = 12")
check_int(lcm(B("0000:0012"), B("0000:0008")), 24, "lcm(12,8) = 24")
check_int(lcm(B("0000:0003"), B("0000:0005")), 15, "lcm(3,5) = 15")
check_int(lcm(B("0000:0006"), B("0000:0008")), 24, "lcm(6,8) = 24")

# === Integer sqrt ===
print("\n=== Квадратный корень ===")
check_int(isqrt(B("0000:0144")), 12, "isqrt(144) = 12")
check_int(isqrt(B("0000:0002")), 1, "isqrt(2) = 1")
check_int(isqrt(B("0000:0000")), 0, "isqrt(0) = 0")
check_int(isqrt(B("0000:0001")), 1, "isqrt(1) = 1")
check_int(isqrt(B("0000:9999")), 99, "isqrt(9999) = 99")
check_int(isqrt(B("0001:0000")), 100, "isqrt(10000) = 100")
check_int(isqrt(B("9999:9999")), 9999, "isqrt(99999999) = 9999")

# === Fractional sqrt ===
print("\n=== Квадратный корень (дробный) ===")
s = sqrt_b10k(B("0000:0002"), 4)
s_str = format_num(s)
# In B10K format, sqrt(2) should have integer part 1 (righthalf = 0001,.)
check(":0001," in s_str,
      f"sqrt(2) integer part = 1, got {s_str}")
# Fractional part should start with 4142
check("4142" in s_str,
      f"sqrt(2) fractional starts with 4142..., got {s_str}")

# === Fibonacci ===
print("\n=== Фибоначчи ===")
check_int(fib_b10k(B("0000:0000")), 0, "fib(0) = 0")
check_int(fib_b10k(B("0000:0001")), 1, "fib(1) = 1")
check_int(fib_b10k(B("0000:0002")), 1, "fib(2) = 1")
check_int(fib_b10k(B("0000:0003")), 2, "fib(3) = 2")
check_int(fib_b10k(B("0000:0004")), 3, "fib(4) = 3")
check_int(fib_b10k(B("0000:0005")), 5, "fib(5) = 5")
check_int(fib_b10k(B("0000:0010")), 55, "fib(10) = 55")
check_int(fib_b10k(B("0000:0020")), 6765, "fib(20) = 6765")

# === Shifts ===
print("\n=== Сдвиги ===")
v = B("0000:0005")
check_eq(shift_left(v, 1), "0005:0000", "shift_left(5,1) = 50000")
check_eq(shift_right(v, 0), "0000:0005", "shift_right(5,0) = 5")
check_int(shift_right(v, 1), 0, "shift_right(5,1) = 0")

v2 = B("0000.0000:0001.0000")  # 100,000,000
check_int(shift_right(v2, 2), 1, "shift_right(1e8,2) = 1")

sys.exit(report())

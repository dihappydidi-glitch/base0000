#!/usr/bin/env python3
"""Tests for B10K arithmetic: add, sub, mul, div, mod, pow, comparisons."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from helpers import check, check_eq, check_int, report, reset
from base10000 import B, _, parse, format_num, to_int
from base10000 import add, sub, mul, div, mod, pow_b10k, div_mod

reset()

# === Addition ===
print("=== Сложение / вычитание ===")
check_eq(add(B("0000:0005"), B("0000:0003")), "0000:0008", "5+3=8")
check_eq(add(B("0000:9999"), B("0000:0001")), "0001:0000", "9999+1=10000")
check_eq(add(B("9999:9999"), B("0000:0001")), "0000.0000:0001.0000", "99999999+1=100000000")
check_eq(add(B("0000:0005"), B("-0000:0003")), "0000:0002", "5+(-3)=2")
check_eq(add(B("0000:0003"), B("-0000:0005")), "-0000:0002", "3+(-5)=-2")
check_eq(add(B("0000:0000"), B("0000:0000")), "0000:0000", "0+0=0")

# === Subtraction ===
check_eq(sub(B("0000:0005"), B("0000:0003")), "0000:0002", "5-3=2")
check_eq(sub(B("0001:0000"), B("0000:0001")), "0000:9999", "10000-1=9999")

# === Multiplication ===
print("\n=== Умножение ===")
check_eq(mul(B("0000:0005"), B("0000:0003")), "0000:0015", "5*3=15")
check_eq(mul(B("0000:0012"), B("0000:0012")), "0000:0144", "12*12=144")
check_eq(mul(B("0000:9999"), B("0000:9999")), "9998:0001", "9999*9999=99980001")
check_eq(mul(B("9999:9999"), B("9999:9999")), "9999.0000:9998.0001", "99999999*99999999")
check_eq(mul(B("0001:0000"), B("0001:0000")), "0000.0000:0001.0000", "10000*10000")
check_eq(mul(B("-0000:0003"), B("0000:0005")), "-0000:0015", "(-3)*5=-15")

# === Division and Remainder ===
print("\n=== Деление и остаток ===")
check_eq(div(B("9998:0001"), B("0000:9999")), "0000:9999", "99980001/9999=9999")
check_eq(div(B("0000.0000:0001.0000"), B("0001:0000")), "0001:0000", "100000000/10000=10000")
check_eq(div(B("0001:0000"), B("0000:0003")), "0000:3333", "10000/3=3333")
check_eq(div(B("0000:0015"), B("0000:0003")), "0000:0005", "15/3=5")
check_eq(div(B("0000:0010"), B("0000:0003")), "0000:0003", "10/3=3")
check_eq(mod(B("0000:0010"), B("0000:0003")), "0000:0001", "10%3=1")

# Euclidean division (negative)
q, r = div_mod(parse("-0000:0007"), parse("0000:0003"))
check(format_num(q) == "-0000:0003" and format_num(r) == "0000:0002",
      f"-7 // 3 = {format_num(q)}, r = {format_num(r)} (expected -3, 2)")

# === Exponentiation ===
print("\n=== Степень ===")
check_eq(pow_b10k(B("0000:0002"), B("0000:0010")), "0000:1024", "2^10=1024")
check_eq(pow_b10k(B("0000:0010"), B("0000:0000")), "0000:0001", "10^0=1")
check_int(pow_b10k(B("0000:0003"), B("0000:0005")), 243, "3^5=243")

# === Comparisons ===
print("\n=== Сравнения ===")
a, b = B("0000:0005"), B("0000:0003")
check(a == B("0000:0005"), "5 == 5")
check(a != b, "5 != 3")
check(not (a == b), "5 != 3 (not eq)")
check(not (a < b), "5 > 3")
check(a > b, "5 > 3")
check(b < a, "3 < 5")
check(not (a <= b), "5 > 3")
check(b <= a, "3 <= 5")
check(-a == B("-0000:0005"), "-5 == -5")
check(abs(-a) == a, "abs(-5) == 5")
check(abs(a) == a, "abs(5) == 5")

# === Python operators ===
print("\n=== Операторы Python ===")
check_int(a + b, 8, "5+3=8 (operator)")
check_int(a - b, 2, "5-3=2 (operator)")
check_int(a * b, 15, "5*3=15 (operator)")
check_int(a // b, 1, "5//3=1 (operator)")
check_int(a % b, 2, "5%3=2 (operator)")
check_int(a ** b, 125, "5**3=125 (operator)")

sys.exit(report())

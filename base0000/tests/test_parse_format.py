#!/usr/bin/env python3
"""Tests for B10K parse and format functions."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from helpers import check, check_eq, check_int, report, reset
from base10000 import B, _, parse, parse_frac, format_num, to_int, to_dec

reset()

# === Parse ===
print("=== parse() ===")
check_eq(parse("0000:0005"), "0000:0005", "parse simple int")
check_eq(parse("-0000:0005"), "-0000:0005", "parse negative int")
check_eq(parse("0000:0000"), "0000:0000", "parse zero")
check_eq(parse("0001:0000"), "0001:0000", "parse 10000")
check_eq(parse("9999:9999"), "9999:9999", "parse 99999999")
check_eq(parse("0000.0000:0001.0000"), "0000.0000:0001.0000", "parse multi-group")

# === B() alias ===
print("\n=== B() ===")
check_eq(B("0000:0007"), "0000:0007", "B() alias")

# === parse_frac ===
print("\n=== parse_frac() ===")
# New format: int, L0.R0.L1.R1... (2 groups per pair)
pf = parse_frac("3,1415.9265.3589.7932.3846.2643.3832.7950")
check(pf.frac_pairs > 0, f"parse_frac pi(4) has frac_pairs={pf.frac_pairs}")

# === format_num ===
print("\n=== format_num() ===")
check_eq(format_num(B("0000:0042")), "0000:0042", "format int")
check_eq(format_num(B("-0000:0042")), "-0000:0042", "format negative int")
check_eq(format_num(B("0000:0000")), "0000:0000", "format zero")
check(format_num(B("9999:9999")) == "9999:9999", "format 9999:9999")

# === _() alias ===
check(_(B("0000:0042")) == "0000:0042", "_() alias for format_num")

# === to_int ===
print("\n=== to_int() ===")
check_int(B("0000:0000"), 0, "to_int(0)")
check_int(B("0000:0001"), 1, "to_int(1)")
check_int(B("0000:9999"), 9999, "to_int(9999)")
check_int(B("0001:0000"), 10000, "to_int(10000)")
check_int(B("-0000:0005"), -5, "to_int(-5)")
check_int(B("9999:0001"), 10000 * 9999 + 1, "to_int(multi)")
check_int(B("0000.0000:0001.0000"), 100000000, "to_int(1e8)")

# === to_dec ===
print("\n=== to_dec() ===")
check(to_dec(B("0000:0100")) == "100", "to_dec(100)")
check(to_dec(B("-0000:0005")) == "-5", "to_dec(-5)")
check(to_dec(B("0000:0000")) == "0", "to_dec(0)")
check(to_dec(B("0001:0000")) == "10000", "to_dec(10000)")

# to_dec with fractional pairs
from base10000 import pi_b10k
pstr = to_dec(pi_b10k(4), 4)
check("3.1415" in pstr, f"to_dec pi(4) has 3.14: {pstr}")

# Round-trip: parse then format returns same
orig = "0000:0123"
check(format_num(parse(orig)) == orig, f"round-trip: {orig}")

orig2 = "-9999:9999"
check(format_num(parse(orig2)) == orig2, f"round-trip negative: {orig2}")

# === Edge cases ===
print("\n=== Краевые случаи ===")
check_eq(B("0000:0000"), B("0000:0000"), "zero equality")
check(B("0000:0001") != B("0000:0002"), "1 != 2")
check(B("0000:0001") == B("0000:0001"), "1 == 1")

# Multi-group formats
check_eq(parse("0000.0000:0000.0000"), "0000:0000", "multi-group zero")
check_eq(parse("0000.0001:0000.0002"), "0001:0002", "multi-group value")

sys.exit(report())

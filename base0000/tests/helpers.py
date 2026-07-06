#!/usr/bin/env python3
"""Shared test helpers for B10K tests."""
import sys, os
sys.set_int_max_str_digits(100_000_000)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from base10000 import B, _, to_int, format_num, BASE

failures = 0

def check(condition, msg=""):
    global failures
    if not condition:
        print(f"  FAIL: {msg}")
        failures += 1
        return False
    else:
        print(f"  OK: {msg}")
        return True

def check_eq(got, expected, msg=""):
    """Check B10K values are equal (compares formatted strings)."""
    g = _(got) if hasattr(got, 'digs') else str(got)
    e = _(expected) if hasattr(expected, 'digs') else str(expected)
    return check(g == e, f"{msg}: expected {e}, got {g}")

def check_int(got, expected, msg=""):
    """Check B10K value equals a Python int."""
    return check(to_int(got) == expected, f"{msg}: expected {expected}, got {to_int(got)}")

def report():
    """Print summary and return exit code."""
    global failures
    if failures == 0:
        print(f"\n=== All OK ===")
        return 0
    else:
        print(f"\n=== {failures} FAILURES ===")
        return 1

def reset():
    global failures
    failures = 0

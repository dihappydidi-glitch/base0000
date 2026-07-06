#!/usr/bin/env python3
"""Run all B10K test modules."""
import subprocess, sys, os, glob

test_dir = os.path.dirname(os.path.abspath(__file__))
test_files = sorted(glob.glob(os.path.join(test_dir, "test_*.py")))

failures = 0
for tf in test_files:
    name = os.path.basename(tf)
    print(f"\n{'='*60}")
    print(f"  {name}")
    print(f"{'='*60}")
    r = subprocess.run([sys.executable, tf], cwd=test_dir)
    if r.returncode != 0:
        failures += 1
        print(f"  >>> {name} FAILED (exit {r.returncode})")

print(f"\n{'='*60}")
if failures == 0:
    print(f"  All {len(test_files)} test modules passed!")
else:
    print(f"  {failures}/{len(test_files)} test modules FAILED!")
sys.exit(failures)

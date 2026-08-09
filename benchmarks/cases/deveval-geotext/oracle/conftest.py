"""Held-out oracle path shim (E-79, generated).

grade_oracle runs the adapter's `pytest oracle ...` from the produced
repository root, and bare pytest does NOT put the working directory on
sys.path. DevEval suites import the produced modules by name (e.g.
`from calc import add`), so without this shim every imported case errors at
collection regardless of how good the produced code is.

Mirrors benchmarks/cases/cat-cafe-monitoring/oracle/conftest.py.
"""
import os
import sys

# The produced repo root is the parent of this oracle/ dir once copied in.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

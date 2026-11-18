"""Exact binomial interval math for the SC rollup (026 T010, A-5).

The Clopper-Pearson computation is self-contained stdlib math, split out
of sc_rollup.py when that module crossed its 470-line plan budget after
the renderer move (the plan's stated contingency) had already fired.
Fleet n is tiny (MIN_RUNS..7), so direct exact binomial sums are exact
and fast — no scipy, no new dependency.
"""

from __future__ import annotations

from math import comb


def _binom_tail_ge(p: float, k: int, n: int) -> float:
    """P(X >= k) for X ~ Bin(n, p), direct exact sum."""
    return sum(comb(n, i) * p**i * (1.0 - p) ** (n - i) for i in range(k, n + 1))


def clopper_pearson(k: int, n: int) -> tuple[float, float]:
    """Exact two-sided 95% Clopper-Pearson bounds, closed form by
    bisection on the binomial tails. 4/5 -> (0.2836, 0.9949)."""
    a = 0.05

    def solve_ge(target: float) -> float:  # lower: P(X >= k | lo) = a/2
        lo, hi = 0.0, 1.0
        for _ in range(200):
            mid = (lo + hi) / 2
            if _binom_tail_ge(mid, k, n) > target:
                hi = mid
            else:
                lo = mid
        return lo

    def solve_le(target: float) -> float:  # upper: P(X <= k | hi) = a/2
        lo, hi = 0.0, 1.0
        for _ in range(200):
            mid = (lo + hi) / 2
            if 1.0 - _binom_tail_ge(mid, k + 1, n) > target:
                lo = mid
            else:
                hi = mid
        return hi

    return (0.0 if k == 0 else solve_ge(a / 2), 1.0 if k == n else solve_le(a / 2))


def ci95_label(hits: int, n: int) -> str:
    """The rendered interval beside a rate ("CI95 [lo, hi]"; "" when no
    rate can exist). n is the floor, not proof of reliability (A-5)."""
    if n == 0 or hits > n:
        return ""
    lo, hi = clopper_pearson(hits, n)
    return f"CI95 [{lo:.2f}, {hi:.2f}]"

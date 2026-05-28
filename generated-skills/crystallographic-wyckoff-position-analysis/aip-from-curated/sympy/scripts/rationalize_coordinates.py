#!/usr/bin/env python3
"""Convert a sequence of floats to exact rational fractions with a bounded denominator.

Wraps `sympy.Rational(x).limit_denominator(max_denominator)` and serializes the
result as canonical fraction strings (e.g. "1/2", "0", "2/3"). The denominator
cap is non-negotiable input — pick the value the task specifies; do not invent
your own.

Usage:
    from rationalize_coordinates import rationalize
    rationalize([0.0, 0.5, 0.5], max_denominator=12)
    # ['0', '1/2', '1/2']

    rationalize([0.333333, 0.666666, 0.125], max_denominator=12)
    # ['1/3', '2/3', '1/8']
"""

from __future__ import annotations

from typing import Iterable, List

from sympy import Rational


def rationalize(values: Iterable[float], max_denominator: int) -> List[str]:
    """Return canonical fraction strings for `values`, denominators bounded by `max_denominator`.

    Uses `sympy.Rational.limit_denominator` (Stern-Brocot best rational
    approximation). NumPy scalars are accepted.
    """
    if max_denominator < 1:
        raise ValueError(f"max_denominator must be >= 1, got {max_denominator}")
    return [str(Rational(float(v)).limit_denominator(max_denominator)) for v in values]


def rationalize_one(value: float, max_denominator: int) -> str:
    """Single-value convenience wrapper around `rationalize`."""
    return rationalize([value], max_denominator)[0]


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-denominator", type=int, required=True,
                        help="Upper bound on denominator (e.g. 12).")
    parser.add_argument("values", nargs="+", type=float,
                        help="Floats to convert.")
    args = parser.parse_args()
    print(json.dumps(rationalize(args.values, args.max_denominator)))

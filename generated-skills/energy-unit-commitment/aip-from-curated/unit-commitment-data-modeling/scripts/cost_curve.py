"""Piecewise-linear total-cost lookup for a thermal production curve.

The curve is a list of `{"mw": float, "cost": float}` breakpoints. Each
`cost` is the TOTAL production cost at that output level — NOT marginal
cost and NOT an incremental segment cost. Treat unfamiliar source
fields (`heat_rate`, `incremental_cost`, slope/intercept pairs) as
distinct shapes that must be converted to total-cost breakpoints before
this helper is used.

Conventions:

* The curve is sorted by `mw`; the source may arrive unsorted.
* Output at or below the smallest breakpoint returns the smallest
  breakpoint's cost. Output at or above the largest breakpoint returns
  the largest breakpoint's cost. The interior is linearly interpolated
  between the bracketing breakpoints.
* When a unit is offline (`u == 0`), production cost is zero; the curve
  is not evaluated. Callers should skip offline periods.
* If the smallest breakpoint sits at `pmin`, its cost may already cover
  the online minimum-output cost. Do not add a separate fixed online
  cost unless the source data explicitly says so.
"""

from __future__ import annotations

from typing import Iterable


def interpolate_total_cost(points: Iterable[dict], output_mw: float) -> float:
    """Return the total production cost at `output_mw` from a piecewise-linear curve.

    Raises ValueError only if the curve is empty.
    """
    pts = sorted(
        ((float(p["mw"]), float(p["cost"])) for p in points),
        key=lambda x: x[0],
    )
    if not pts:
        raise ValueError("empty cost curve")
    if output_mw <= pts[0][0]:
        return pts[0][1]
    if output_mw >= pts[-1][0]:
        return pts[-1][1]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x0 <= output_mw <= x1:
            if x1 == x0:
                return y0
            return y0 + (output_mw - x0) * (y1 - y0) / (x1 - x0)
    raise ValueError(f"output {output_mw} outside curve range")


if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) != 2:
        print("usage: cost_curve.py <input.json>", file=sys.stderr)
        sys.exit(2)
    with open(sys.argv[1]) as f:
        payload = json.load(f)
    if "points" not in payload or "output_mw" not in payload:
        print("input.json must contain 'points' and 'output_mw'", file=sys.stderr)
        sys.exit(2)
    cost = interpolate_total_cost(payload["points"], float(payload["output_mw"]))
    print(json.dumps({"total_cost": cost}, indent=2))
    sys.exit(0)

"""Piecewise-linear production-cost lookup.

The cost curve is a list of `{"mw": float, "cost": float}` breakpoints with
the cost being the TOTAL production cost at that output level — not a
marginal cost.

Conventions captured from the operating-rules guide:

* The smallest breakpoint is usually at `pmin`. The cost at that point may
  already include the online minimum-output cost; do not add a separate
  fixed online cost unless the data explicitly says so.
* Output below the smallest breakpoint clamps to the smallest cost; output
  above the largest breakpoint clamps to the largest cost. The interior is
  linearly interpolated between adjacent breakpoints.
* When a unit is offline (`u == 0`), production cost is zero — the curve
  is not evaluated.
"""

from __future__ import annotations

from typing import Iterable, Sequence


def total_cost_from_curve(points: Iterable[dict], output_mw: float) -> float:
    """Return the total production cost at `output_mw` using a piecewise-linear
    total-cost curve.

    Clamps to the endpoints; raises ValueError only if the curve is empty.
    """
    pts = sorted(((float(p["mw"]), float(p["cost"])) for p in points), key=lambda x: x[0])
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
    raise ValueError(f"output {output_mw} outside curve")


def schedule_production_cost(
    u: Sequence[int],
    production_actual_mw: Sequence[float],
    points: Iterable[dict],
) -> float:
    """Sum the per-period production cost over a unit's schedule.

    `production_actual_mw` is the actual-MW output (not above-min). If the
    surrounding model uses above-min internally, convert before calling.
    Offline periods (u == 0) contribute zero.
    """
    pts = list(points)
    total = 0.0
    for t, p in enumerate(production_actual_mw):
        if int(u[t]) == 0:
            continue
        total += total_cost_from_curve(pts, float(p))
    return total


if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) != 2:
        print("usage: production_cost.py <input.json>", file=sys.stderr)
        sys.exit(2)
    with open(sys.argv[1]) as f:
        payload = json.load(f)

    if "output_mw" in payload and "points" in payload:
        cost = total_cost_from_curve(payload["points"], float(payload["output_mw"]))
        print(json.dumps({"production_cost": cost}, indent=2))
        sys.exit(0)
    if all(k in payload for k in ("u", "production_actual_mw", "points")):
        cost = schedule_production_cost(
            payload["u"],
            payload["production_actual_mw"],
            payload["points"],
        )
        print(json.dumps({"total_production_cost": cost}, indent=2))
        sys.exit(0)
    print("input.json missing required keys", file=sys.stderr)
    sys.exit(2)

"""Control-system step-response metrics.

Reusable functions for evaluating simulation results against a target setpoint.
Both importable and runnable as a CLI:

    python scripts/metrics.py --json '{"times": [...], "values": [...], "target": 30.0}'

CLI prints a JSON object with keys: rise_time, overshoot_percent,
steady_state_error, settling_time. rise_time and settling_time may be null
when the response never crosses the relevant thresholds.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Iterable, Optional, Sequence


def rise_time(
    times: Sequence[float],
    values: Sequence[float],
    target: float,
) -> Optional[float]:
    """Time from 10% to 90% of target. None if either threshold never reached."""
    t10 = t90 = None
    for t, v in zip(times, values):
        if t10 is None and v >= 0.1 * target:
            t10 = t
        if t90 is None and v >= 0.9 * target:
            t90 = t
            break
    if t10 is not None and t90 is not None:
        return t90 - t10
    return None


def overshoot_percent(values: Iterable[float], target: float) -> float:
    """Peak overshoot as a percentage above target. Zero if peak <= target."""
    max_val = max(values)
    if max_val <= target:
        return 0.0
    return ((max_val - target) / target) * 100


def steady_state_error(
    values: Sequence[float],
    target: float,
    final_fraction: float = 0.1,
) -> float:
    """Absolute error between target and the mean of the final `final_fraction` of samples."""
    n = len(values)
    start = int(n * (1 - final_fraction))
    tail = values[start:]
    final_avg = sum(tail) / len(tail)
    return abs(target - final_avg)


def settling_time(
    times: Sequence[float],
    values: Sequence[float],
    target: float,
    tolerance: float = 0.02,
) -> Optional[float]:
    """First time after which the response stays within ±tolerance*target. None if never."""
    band = target * tolerance
    lower, upper = target - band, target + band
    settled_at = None
    for t, v in zip(times, values):
        if v < lower or v > upper:
            settled_at = None
        elif settled_at is None:
            settled_at = t
    return settled_at


def all_metrics(
    times: Sequence[float],
    values: Sequence[float],
    target: float,
    final_fraction: float = 0.1,
    tolerance: float = 0.02,
) -> dict:
    return {
        "rise_time": rise_time(times, values, target),
        "overshoot_percent": overshoot_percent(values, target),
        "steady_state_error": steady_state_error(values, target, final_fraction),
        "settling_time": settling_time(times, values, target, tolerance),
    }


def _main() -> int:
    parser = argparse.ArgumentParser(description="Compute control-system step-response metrics.")
    parser.add_argument(
        "--json",
        help='JSON object with keys: times (list[float]), values (list[float]), target (float), '
        'and optional final_fraction, tolerance.',
    )
    parser.add_argument("--json-file", help="Path to a file containing the same JSON payload.")
    args = parser.parse_args()

    if not args.json and not args.json_file:
        parser.error("provide --json or --json-file")

    payload = json.loads(args.json) if args.json else json.load(open(args.json_file))
    result = all_metrics(
        times=payload["times"],
        values=payload["values"],
        target=payload["target"],
        final_fraction=payload.get("final_fraction", 0.1),
        tolerance=payload.get("tolerance", 0.02),
    )
    json.dump(result, sys.stdout)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())

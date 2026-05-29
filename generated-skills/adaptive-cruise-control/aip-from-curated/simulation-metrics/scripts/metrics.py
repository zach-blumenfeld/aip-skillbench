#!/usr/bin/env python3
"""Control-system step-response metrics: rise time, overshoot,
steady-state error, settling time.

Importable:
    from metrics import rise_time, overshoot_percent, steady_state_error, settling_time

CLI:
    python metrics.py --csv simulation_results.csv --column ego_speed --target 30.0
    # optional: --tolerance 0.02 --final-fraction 0.1
Outputs JSON: {"rise_time": ..., "overshoot_percent": ..., "steady_state_error": ..., "settling_time": ...}
A null in JSON means the metric is undefined for the given trace (e.g., target never reached).
"""

import argparse
import csv
import json
import math
import sys


def rise_time(times, values, target):
    """Time for value to go from 10% to 90% of target."""
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


def overshoot_percent(values, target):
    """Maximum excursion above target, as a percentage of target."""
    max_val = max(values)
    if max_val <= target:
        return 0.0
    return ((max_val - target) / target) * 100


def steady_state_error(values, target, final_fraction=0.1):
    """|target - mean(final_fraction tail of values)|."""
    n = len(values)
    start = int(n * (1 - final_fraction))
    final_avg = sum(values[start:]) / len(values[start:])
    return abs(target - final_avg)


def settling_time(times, values, target, tolerance=0.02):
    """First time the trace enters the ±tolerance band AND stays inside
    for the remainder of the trace. A re-exit resets the candidate time."""
    band = target * tolerance
    lower, upper = target - band, target + band

    settled_at = None
    for t, v in zip(times, values):
        if v < lower or v > upper:
            settled_at = None
        elif settled_at is None:
            settled_at = t

    return settled_at


def compute_all(times, values, target, tolerance=0.02, final_fraction=0.1):
    return {
        "rise_time": rise_time(times, values, target),
        "overshoot_percent": overshoot_percent(values, target),
        "steady_state_error": steady_state_error(values, target, final_fraction),
        "settling_time": settling_time(times, values, target, tolerance),
    }


def _read_csv(path, time_col, value_col):
    times, values = [], []
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        if time_col not in reader.fieldnames or value_col not in reader.fieldnames:
            raise SystemExit(
                f"CSV columns missing. Need '{time_col}' and '{value_col}'. "
                f"Found: {reader.fieldnames}"
            )
        for row in reader:
            t_raw = row[time_col]
            v_raw = row[value_col]
            if t_raw in (None, "") or v_raw in (None, ""):
                continue
            try:
                t = float(t_raw)
                v = float(v_raw)
            except ValueError:
                continue
            if math.isnan(t) or math.isnan(v):
                continue
            times.append(t)
            values.append(v)
    if not times:
        raise SystemExit(f"No numeric rows found in {path} for columns {time_col}, {value_col}.")
    return times, values


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--csv", required=True, help="Path to simulation results CSV.")
    p.add_argument("--column", required=True, help="Column to evaluate (e.g., ego_speed).")
    p.add_argument("--target", required=True, type=float, help="Target/setpoint value.")
    p.add_argument("--time-column", default="time", help="Time column name (default: time).")
    p.add_argument("--tolerance", type=float, default=0.02,
                   help="Settling-time band as fraction of target (default: 0.02).")
    p.add_argument("--final-fraction", type=float, default=0.1,
                   help="Tail fraction used for steady-state error (default: 0.1).")
    args = p.parse_args()

    times, values = _read_csv(args.csv, args.time_column, args.column)
    result = compute_all(times, values, args.target, args.tolerance, args.final_fraction)
    json.dump(result, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()

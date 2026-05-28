"""Validate a planned-trajectory matrix against physical accel limits.

The drone's motors saturate when commanded beyond the physical
acceleration envelope derived from `system_params.yaml`:

  az  (upward)     ≤  accel_limit_up      m/s²    e.g. 6.962
  az  (downward)   ≥ -accel_limit_down    m/s²    e.g. -9.429
  √(ax²+ay²)       ≤  accel_limit_horiz   m/s²    e.g. 13.602

A trajectory that violates these will fail tracking no matter how
well-tuned the controller is. Run this before committing to a
trajectory so failures surface at planning time, not in simulation.

CLI
---
    uv run scripts/check_acceleration_limits.py <trajectory.npy> \
        --params /root/system_params.yaml

Exit 0 if all timesteps satisfy the limits, 1 otherwise. JSON Lines
violations stream to stderr; one-line summary on stdout.
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import yaml


def check_limits(trajectory, accel_up, accel_down, accel_horiz):
    """Inspect rows 12:15 of a (15 × N) trajectory for limit violations.

    Returns a dict:
      {
        "ok": bool,
        "max_az": float,
        "min_az": float,
        "max_horiz": float,
        "violations": {
            "az_up":   [(timestep, value), ...],
            "az_down": [(timestep, value), ...],
            "horiz":   [(timestep, value), ...],
        },
      }
    """
    acc = np.asarray(trajectory)[12:15, :]
    ax, ay, az = acc[0], acc[1], acc[2]
    horiz = np.sqrt(ax * ax + ay * ay)

    az_up_bad = np.where(az > accel_up)[0]
    az_dn_bad = np.where(az < -accel_down)[0]
    horiz_bad = np.where(horiz > accel_horiz)[0]

    return {
        "ok": int(az_up_bad.size + az_dn_bad.size + horiz_bad.size) == 0,
        "max_az": float(az.max()),
        "min_az": float(az.min()),
        "max_horiz": float(horiz.max()),
        "violations": {
            "az_up": [(int(i), float(az[i])) for i in az_up_bad],
            "az_down": [(int(i), float(az[i])) for i in az_dn_bad],
            "horiz": [(int(i), float(horiz[i])) for i in horiz_bad],
        },
    }


def main(argv=None):
    p = argparse.ArgumentParser(
        description="Check a planned trajectory against drone accel limits.",
    )
    p.add_argument("trajectory", help="Path to planned_trajectory.npy")
    p.add_argument(
        "--params",
        default="/root/system_params.yaml",
        help="Path to system_params.yaml (default: /root/system_params.yaml)",
    )
    args = p.parse_args(argv)

    with open(args.params) as f:
        params = yaml.safe_load(f)
    accel_up = float(params["accel_limit_up"])
    accel_down = float(params["accel_limit_down"])
    accel_horiz = float(params["accel_limit_horiz"])

    matrix = np.load(args.trajectory)
    if matrix.ndim != 2 or matrix.shape[0] != 15:
        print(
            f"trajectory must have shape (15, N); got {matrix.shape}",
            file=sys.stderr,
        )
        return 1

    report = check_limits(matrix, accel_up, accel_down, accel_horiz)

    if not report["ok"]:
        for kind, items in report["violations"].items():
            for ts, val in items:
                json.dump(
                    {
                        "path": str(Path(args.trajectory).resolve()),
                        "kind": f"limit-violation:{kind}",
                        "timestep": ts,
                        "value": val,
                        "severity": "error",
                    },
                    sys.stderr,
                )
                sys.stderr.write("\n")
        print(
            f"FAIL  max_az={report['max_az']:.3f}  min_az={report['min_az']:.3f}"
            f"  max_horiz={report['max_horiz']:.3f}",
        )
        return 1

    print(
        f"OK    max_az={report['max_az']:.3f}  min_az={report['min_az']:.3f}"
        f"  max_horiz={report['max_horiz']:.3f}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

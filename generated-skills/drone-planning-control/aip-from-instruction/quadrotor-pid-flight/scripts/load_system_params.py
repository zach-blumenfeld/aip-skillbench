"""Load drone system parameters from YAML.

Required keys: accel_limit_up, accel_limit_down, accel_limit_horiz.
All other keys are optional and fall back to a generic 1 kg quadrotor.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

REQUIRED = ["accel_limit_up", "accel_limit_down", "accel_limit_horiz"]


def load(path: str | Path) -> dict:
    with open(path) as f:
        raw = yaml.safe_load(f) or {}
    missing = [k for k in REQUIRED if k not in raw]
    if missing:
        raise KeyError(f"system_params.yaml missing required keys: {missing}")
    return {
        "mass": float(raw.get("mass", 1.0)),
        "g": float(raw.get("g", 9.81)),
        "Ixx": float(raw.get("Ixx", 0.02)),
        "Iyy": float(raw.get("Iyy", 0.02)),
        "Izz": float(raw.get("Izz", 0.04)),
        "motor_tau": float(raw.get("motor_tau", 0.05)),
        "accel_limit_up": float(raw["accel_limit_up"]),
        "accel_limit_down": float(raw["accel_limit_down"]),
        "accel_limit_horiz": float(raw["accel_limit_horiz"]),
        "dt": float(raw.get("dt", 0.01)),
        "tilt_limit_deg": float(raw.get("tilt_limit_deg", 30.0)),
    }


if __name__ == "__main__":
    print(json.dumps(load(sys.argv[1]), indent=2))

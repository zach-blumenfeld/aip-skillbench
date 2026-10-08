"""Load system_params.yaml and derive the physical limits the planner must respect."""
import os

import numpy as np

DEFAULT_PARAMS_PATH = os.environ.get("QUAD_PARAMS", "/root/system_params.yaml")

REQUIRED_KEYS = ["sample_rate", "mass", "gravity", "arm_length", "thrust_coefficient",
                 "moment_scale", "motor_constant", "rpm_min", "rpm_max", "inertia"]


def _load_yaml(path):
    try:
        import yaml
        with open(path) as f:
            return yaml.safe_load(f)
    except ImportError:  # minimal fallback: flat `key: value  # comment` files only
        out = {}
        with open(path) as f:
            for line in f:
                line = line.split("#", 1)[0].strip()
                if not line or ":" not in line:
                    continue
                k, v = (s.strip() for s in line.split(":", 1))
                if v.startswith("["):
                    out[k] = [float(x) for x in v.strip("[]").split(",") if x.strip()]
                else:
                    out[k] = float(v)
        return out


def load_params(path=None):
    """Return a params dict. `inertia` becomes np.diag(inertia); derived limits are added.

    Derived keys: dt, T_max, T_min, twr, accel_limit_up/down/horiz (yaml values win when
    present, otherwise derived from motor limits), hover_rpm.
    """
    path = path or DEFAULT_PARAMS_PATH
    raw = _load_yaml(path)
    missing = [k for k in REQUIRED_KEYS if k not in raw]
    if missing:
        raise KeyError(f"{path} is missing keys: {missing}")
    p = dict(raw)
    for k in REQUIRED_KEYS:
        if k != "inertia":
            p[k] = float(p[k])
    inertia = np.asarray(raw["inertia"], dtype=float)
    p["inertia"] = np.diag(inertia) if inertia.ndim == 1 else inertia
    p["sample_rate"] = float(p["sample_rate"])
    p["dt"] = 1.0 / p["sample_rate"]
    m, g, cT = p["mass"], p["gravity"], p["thrust_coefficient"]
    p["T_max"] = 4 * cT * p["rpm_max"] ** 2
    p["T_min"] = 4 * cT * p["rpm_min"] ** 2
    p["twr"] = p["T_max"] / (m * g)
    derived = {
        "accel_limit_up": (p["T_max"] - m * g) / m,
        "accel_limit_down": (m * g - p["T_min"]) / m,
        "accel_limit_horiz": float(np.sqrt(max(p["T_max"] ** 2 - (m * g) ** 2, 0.0)) / m),
    }
    for k, v in derived.items():
        p[k] = float(raw[k]) if k in raw else v
    p["hover_rpm"] = float(np.sqrt(m * g / (4 * cT)))
    return p

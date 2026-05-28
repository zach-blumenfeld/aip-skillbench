#!/usr/bin/env python3
"""Assemble and validate a GaMMA `association` config dict.

Encodes the documented config knowledge from the GaMMA API reference so the
config is built consistently:
  - method -> oversample_factor rule (BGMM=5.0, GMM=1.0)
  - numeric defaults for filtering / DBSCAN keys
  - bfgs_bounds construction in the documented
    ((x_min,x_max), ..., (None,None)) shape from per-dim bounds
  - use_amplitude -> max_sigma22 dependency
  - validation of method, dims, and presence of bounds for each solved dim

Stdlib only (no pandas / no gamma import) so it runs standalone. `dbscan_eps`
must be supplied by the caller — estimate it with `gamma.utils.estimate_eps`
(see references/estimate-eps-api.md) or set a manual value (10-15 s is common).

Import usage (preferred — preserves Python tuples / None in bfgs_bounds):

    from build_gamma_config import build_gamma_config
    config = build_gamma_config(
        bounds={"x(km)": (xmin, xmax), "y(km)": (ymin, ymax), "z(km)": (0, 30)},
        method="BGMM",
        use_amplitude=False,
        dbscan_eps=eps,            # from estimate_eps(...) or a manual value
    )
    events, assignments = association(picks, stations, config, 0, config["method"])

CLI usage (convenience — prints config as JSON for inspection; note that the
time bound (None, None) renders as [null, null] in JSON):

    python build_gamma_config.py params.json
    cat params.json | python build_gamma_config.py -
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict, Iterable, Optional, Tuple

ALLOWED_DIMS = ("x(km)", "y(km)", "z(km)")
ALLOWED_METHODS = ("BGMM", "GMM")
DEFAULT_VEL = {"p": 6.0, "s": 3.47}


def build_gamma_config(
    bounds: Dict[str, Tuple[float, float]],
    *,
    dims: Iterable[str] = ("x(km)", "y(km)", "z(km)"),
    method: str = "BGMM",
    use_amplitude: bool = False,
    use_dbscan: bool = True,
    dbscan_eps: Optional[float] = None,
    dbscan_min_samples: int = 3,
    vel: Optional[Dict[str, float]] = None,
    min_picks_per_eq: int = 5,
    max_sigma11: float = 2.0,
    max_sigma22: float = 1.0,
    max_sigma12: float = 1.0,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Return a validated GaMMA `association` config dict.

    `bounds` maps each solved dim name ("x(km)", "y(km)", "z(km)") to its
    (min, max) extent in km. `extra` is merged last and can set any additional
    documented key (eikonal, covariance_prior, ncpu, dbscan_min_cluster_size,
    dbscan_max_time_space_ratio, min_p_picks_per_eq, min_s_picks_per_eq,
    min_stations) or override a default.
    """
    dims = list(dims)

    if method not in ALLOWED_METHODS:
        raise ValueError(
            f"method must be one of {ALLOWED_METHODS}, got {method!r}"
        )

    bad_dims = [d for d in dims if d not in ALLOWED_DIMS]
    if bad_dims:
        raise ValueError(
            f"dims entries must be from {ALLOWED_DIMS}, got invalid {bad_dims}"
        )
    if not dims:
        raise ValueError("dims must list at least one solved dimension")

    missing = [d for d in dims if d not in bounds]
    if missing:
        raise ValueError(
            f"bounds is missing an entry for solved dim(s): {missing}. "
            f"Provide (min, max) for each dim in dims={dims}."
        )
    for d in dims:
        lo, hi = bounds[d]
        if lo > hi:
            raise ValueError(f"bounds[{d!r}] has min > max: ({lo}, {hi})")

    if use_dbscan and dbscan_eps is None:
        raise ValueError(
            "use_dbscan=True requires dbscan_eps. Estimate it with "
            "gamma.utils.estimate_eps(stations, vp) or set a manual value "
            "(10-15 s is common). See references/estimate-eps-api.md."
        )

    # method -> oversample_factor rule (documented in the config table).
    oversample_factor = 5.0 if method == "BGMM" else 1.0

    # bfgs_bounds: per-dim (min, max) in dims order, then the unbounded time slot.
    bfgs_bounds = tuple(tuple(bounds[d]) for d in dims) + ((None, None),)

    config: Dict[str, Any] = {
        "dims": dims,
        "use_amplitude": use_amplitude,
        "method": method,
        "oversample_factor": oversample_factor,
        "vel": dict(vel) if vel is not None else dict(DEFAULT_VEL),
        "min_picks_per_eq": min_picks_per_eq,
        "max_sigma11": max_sigma11,
        "max_sigma12": max_sigma12,
        "bfgs_bounds": bfgs_bounds,
    }

    # max_sigma22 is the amplitude residual cap — only meaningful (and required)
    # when amplitude is part of the clustering.
    if use_amplitude:
        config["max_sigma22"] = max_sigma22

    if use_dbscan:
        config["use_dbscan"] = True
        config["dbscan_eps"] = dbscan_eps
        config["dbscan_min_samples"] = dbscan_min_samples
    else:
        config["use_dbscan"] = False

    if extra:
        config.update(extra)

    return config


def _main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "params",
        help="Path to a JSON file of keyword arguments, or '-' to read JSON "
        "from stdin. Keys mirror build_gamma_config's parameters; 'bounds' is "
        'required, e.g. {"bounds": {"x(km)": [-35, 92], "y(km)": [-128, 78], '
        '"z(km)": [0, 30]}, "method": "BGMM", "dbscan_eps": 15}.',
    )
    args = parser.parse_args(argv)

    raw = sys.stdin.read() if args.params == "-" else open(args.params).read()
    try:
        params = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"error: params is not valid JSON: {exc}", file=sys.stderr)
        return 1
    if not isinstance(params, dict):
        print("error: params JSON must be an object", file=sys.stderr)
        return 1

    bounds = params.pop("bounds", None)
    if bounds is None:
        print("error: params must include 'bounds'", file=sys.stderr)
        return 1
    bounds = {k: tuple(v) for k, v in bounds.items()}

    try:
        config = build_gamma_config(bounds, **params)
    except (ValueError, TypeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(config, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())

#!/usr/bin/env python3
"""Run a Box Least Squares (BLS) periodogram on a light curve via astropy.

Inputs
------
--data PATH       Whitespace- or comma-delimited text light curve.
--time-col INT    Zero-based column index for time. Default 0.
--flux-col INT    Zero-based column index for flux. Default 1.
--flag-col INT    Optional zero-based column index for quality flag.
                  When set, rows whose flag != --good-flag are dropped.
--good-flag FLOAT Quality-flag value that means "keep this row". Default 0.
--err-col INT     Optional zero-based column index for flux uncertainty.
                  Strongly recommended — BLS weights by 1/dy^2.
--min-period F    Optional minimum period (days). Passed to autopower.
--max-period F    Optional maximum period (days). Passed to autopower.
--durations CSV   Comma-separated transit durations in days.
                  Default "0.05,0.075,0.1,0.15,0.2,0.25,0.3" (broad sweep).
--objective STR   BLS objective: "likelihood" (default) or "snr".
                  SNR is more robust under correlated noise.
--top N           Number of top periodogram peaks to return (default 5).
--delimiter STR   Column delimiter. Default: whitespace (any).

Output (stdout, JSON)
---------------------
{
  "strongest_period_days": float,
  "strongest_duration_days": float,
  "strongest_t0_days": float,
  "max_power": float,
  "n_points": int,
  "objective": "likelihood" | "snr",
  "stats": {
    "depth": float,
    "depth_err": float,
    "depth_snr": float,
    "depth_odd": float,
    "depth_even": float,
    "odd_even_mismatch": float,
    "odd_even_mismatch_sigma": float,
    "transit_count": int,
    "duration": float,
    "period": float
  },
  "top_peaks": [
    {"period_days": float, "duration_days": float, "t0_days": float, "power": float},
    ...
  ]
}

Errors go to stderr; exit 1 on any failure.

Notes
-----
- Wraps `astropy.timeseries.BoxLeastSquares` with `autopower(durations)`.
- This script does NOT detrend or sigma-clip; that belongs to
  `light-curve-preprocessing`. Pass an already-cleaned light curve when the
  goal is to surface a buried transit signal.
- `compute_stats()` is always run on the strongest peak so the agent gets
  depth_snr, odd/even depths, and transit_count for validation in a single
  invocation.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np


def load_columns(
    path: Path,
    *,
    delimiter: str | None,
    time_col: int,
    flux_col: int,
    flag_col: int | None,
    good_flag: float,
    err_col: int | None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray | None]:
    data = np.loadtxt(path, delimiter=delimiter)
    if data.ndim == 1:
        data = data.reshape(1, -1)
    time = data[:, time_col]
    flux = data[:, flux_col]
    err = data[:, err_col] if err_col is not None else None
    if flag_col is not None:
        good = data[:, flag_col] == good_flag
        time = time[good]
        flux = flux[good]
        if err is not None:
            err = err[good]
    finite = np.isfinite(time) & np.isfinite(flux)
    if err is not None:
        finite &= np.isfinite(err)
    time = time[finite]
    flux = flux[finite]
    if err is not None:
        err = err[finite]
    return time, flux, err


def top_peaks(
    periods: np.ndarray,
    durations: np.ndarray,
    t0s: np.ndarray,
    powers: np.ndarray,
    n: int,
) -> list[dict]:
    """Return up to n local-maximum peaks (descending power)."""
    p = np.asarray(powers, dtype=float)
    if p.size == 0:
        return []
    if p.size < 3:
        idxs = [int(np.argmax(p))]
    else:
        interior = (p[1:-1] > p[:-2]) & (p[1:-1] > p[2:])
        idxs = list((np.where(interior)[0] + 1).tolist())
        if not idxs:
            idxs = [int(np.argmax(p))]
    idxs.sort(key=lambda i: p[i], reverse=True)
    out = []
    for i in idxs[:n]:
        out.append(
            {
                "period_days": float(periods[i]),
                "duration_days": float(durations[i]),
                "t0_days": float(t0s[i]),
                "power": float(p[i]),
            }
        )
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", required=True, type=Path)
    ap.add_argument("--time-col", type=int, default=0)
    ap.add_argument("--flux-col", type=int, default=1)
    ap.add_argument("--flag-col", type=int, default=None)
    ap.add_argument("--good-flag", type=float, default=0.0)
    ap.add_argument("--err-col", type=int, default=None)
    ap.add_argument("--min-period", type=float, default=None)
    ap.add_argument("--max-period", type=float, default=None)
    ap.add_argument(
        "--durations",
        type=str,
        default="0.05,0.075,0.1,0.15,0.2,0.25,0.3",
        help="Comma-separated transit durations in days.",
    )
    ap.add_argument(
        "--objective",
        type=str,
        default="likelihood",
        choices=("likelihood", "snr"),
    )
    ap.add_argument("--top", type=int, default=5)
    ap.add_argument(
        "--delimiter",
        type=str,
        default=None,
        help="Column delimiter; default any whitespace.",
    )
    args = ap.parse_args(argv)

    try:
        import astropy.units as u
        from astropy.timeseries import BoxLeastSquares
    except ImportError as exc:
        print(f"ERROR: astropy not installed: {exc}", file=sys.stderr)
        return 1

    try:
        time, flux, err = load_columns(
            args.data,
            delimiter=args.delimiter,
            time_col=args.time_col,
            flux_col=args.flux_col,
            flag_col=args.flag_col,
            good_flag=args.good_flag,
            err_col=args.err_col,
        )
    except Exception as exc:
        print(f"ERROR: failed to load {args.data}: {exc}", file=sys.stderr)
        return 1

    if time.size == 0:
        print("ERROR: no finite rows after filtering", file=sys.stderr)
        return 1

    try:
        durations_d = [float(x) for x in args.durations.split(",") if x.strip()]
    except ValueError as exc:
        print(f"ERROR: bad --durations value: {exc}", file=sys.stderr)
        return 1
    if not durations_d:
        print("ERROR: --durations must list at least one value", file=sys.stderr)
        return 1

    t = time * u.day
    durations_q = np.array(durations_d) * u.day

    try:
        model = BoxLeastSquares(t, flux, dy=err)
    except Exception as exc:
        print(f"ERROR: BoxLeastSquares init failed: {exc}", file=sys.stderr)
        return 1

    autopower_kwargs = {"objective": args.objective}
    if args.min_period is not None:
        autopower_kwargs["minimum_period"] = args.min_period * u.day
    if args.max_period is not None:
        autopower_kwargs["maximum_period"] = args.max_period * u.day

    try:
        pg = model.autopower(durations_q, **autopower_kwargs)
    except Exception as exc:
        print(f"ERROR: autopower failed: {exc}", file=sys.stderr)
        return 1

    period_arr = np.asarray(pg.period.to_value(u.day), dtype=float)
    duration_arr = np.asarray(pg.duration.to_value(u.day), dtype=float)
    t0_arr = np.asarray(pg.transit_time.to_value(u.day), dtype=float)
    power_arr = np.asarray(pg.power, dtype=float)

    best_idx = int(np.argmax(power_arr))
    best_period = period_arr[best_idx] * u.day
    best_duration = duration_arr[best_idx] * u.day
    best_t0 = t0_arr[best_idx] * u.day

    try:
        stats = model.compute_stats(best_period, best_duration, best_t0)
    except Exception as exc:
        print(f"ERROR: compute_stats failed: {exc}", file=sys.stderr)
        return 1

    def _scalar(value, unit=None):
        try:
            if unit is not None:
                value = value.to_value(unit)
            else:
                value = getattr(value, "value", value)
        except AttributeError:
            pass
        arr = np.asarray(value, dtype=float).ravel()
        return float(arr[0]) if arr.size else float("nan")

    depth_pair = stats.get("depth", (np.nan, np.nan))
    depth_val = _scalar(depth_pair[0]) if hasattr(depth_pair, "__len__") and len(depth_pair) >= 2 else _scalar(depth_pair)
    depth_err_val = _scalar(depth_pair[1]) if hasattr(depth_pair, "__len__") and len(depth_pair) >= 2 else float("nan")

    odd = stats.get("depth_odd", (np.nan, np.nan))
    odd_val = _scalar(odd[0]) if hasattr(odd, "__len__") and len(odd) >= 1 else _scalar(odd)
    odd_err_val = _scalar(odd[1]) if hasattr(odd, "__len__") and len(odd) >= 2 else float("nan")

    even = stats.get("depth_even", (np.nan, np.nan))
    even_val = _scalar(even[0]) if hasattr(even, "__len__") and len(even) >= 1 else _scalar(even)
    even_err_val = _scalar(even[1]) if hasattr(even, "__len__") and len(even) >= 2 else float("nan")

    half_pair = stats.get("depth_half", (np.nan, np.nan))
    half_val = _scalar(half_pair[0]) if hasattr(half_pair, "__len__") and len(half_pair) >= 1 else _scalar(half_pair)

    mismatch = odd_val - even_val
    combined_err = float(np.sqrt(odd_err_val ** 2 + even_err_val ** 2)) if np.isfinite(odd_err_val) and np.isfinite(even_err_val) else float("nan")
    mismatch_sigma = float(abs(mismatch) / combined_err) if combined_err > 0 else float("nan")
    depth_snr = float(depth_val / depth_err_val) if depth_err_val and np.isfinite(depth_err_val) and depth_err_val > 0 else float("nan")

    transit_count = stats.get("transit_times")
    if transit_count is not None:
        try:
            transit_count = int(np.asarray(transit_count).size)
        except Exception:
            transit_count = None
    if transit_count is None:
        transit_count = int(stats.get("transit_count", 0) or 0)

    stats_out = {
        "depth": depth_val,
        "depth_err": depth_err_val,
        "depth_snr": depth_snr,
        "depth_odd": odd_val,
        "depth_even": even_val,
        "odd_even_mismatch": float(mismatch),
        "odd_even_mismatch_sigma": mismatch_sigma,
        "depth_half": half_val,
        "transit_count": transit_count,
        "duration": _scalar(best_duration, u.day),
        "period": _scalar(best_period, u.day),
        "t0": _scalar(best_t0, u.day),
    }

    result = {
        "strongest_period_days": _scalar(best_period, u.day),
        "strongest_duration_days": _scalar(best_duration, u.day),
        "strongest_t0_days": _scalar(best_t0, u.day),
        "max_power": float(power_arr[best_idx]),
        "n_points": int(time.size),
        "objective": args.objective,
        "min_period_searched": float(np.nanmin(period_arr)),
        "max_period_searched": float(np.nanmax(period_arr)),
        "stats": stats_out,
        "top_peaks": top_peaks(period_arr, duration_arr, t0_arr, power_arr, args.top),
    }
    json.dump(result, sys.stdout)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())

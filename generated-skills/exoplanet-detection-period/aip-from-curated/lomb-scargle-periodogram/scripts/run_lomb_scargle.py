#!/usr/bin/env python3
"""Run a Lomb-Scargle periodogram on a light curve via lightkurve.

Inputs
------
--data PATH       Whitespace- or comma-delimited text light curve.
--time-col INT    Zero-based column index for time. Default 0.
--flux-col INT    Zero-based column index for flux. Default 1.
--flag-col INT    Optional zero-based column index for quality flag.
                  When set, rows with non-zero flag are dropped.
--err-col INT     Optional zero-based column index for flux uncertainty.
--min-period F    Optional minimum period (days).
--max-period F    Optional maximum period (days).
--top N           Number of top peaks to return (default 5). Useful for
                  detecting harmonics (peaks at fundamental/2, fundamental*2).
--delimiter STR   Column delimiter. Default: whitespace (any).

Output (stdout, JSON)
---------------------
{
  "strongest_period_days": float,
  "max_power": float,
  "n_points": int,
  "min_period_searched": float,
  "max_period_searched": float,
  "top_peaks": [
    {"period_days": float, "power": float},
    ...
  ]
}

Errors go to stderr; exit 1 on any failure.

Notes
-----
- Uses `lightkurve.LightCurve.to_periodogram()` (Lomb-Scargle backend).
- This script does NOT perform outlier removal or detrending — that belongs
  to `light-curve-preprocessing`. Pass an already-cleaned light curve when
  the goal is to surface a buried signal.
- For exoplanet *transit* periods, prefer Transit Least Squares (TLS) after
  this initial Lomb-Scargle pass.
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
    err_col: int | None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray | None]:
    data = np.loadtxt(path, delimiter=delimiter)
    if data.ndim == 1:
        data = data.reshape(1, -1)
    time = data[:, time_col]
    flux = data[:, flux_col]
    err = data[:, err_col] if err_col is not None else None
    if flag_col is not None:
        good = data[:, flag_col] == 0
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


def top_peaks(periods: np.ndarray, powers: np.ndarray, n: int) -> list[dict]:
    """Return up to n local-maximum (period, power) pairs, strongest first."""
    if powers.size == 0:
        return []
    p = np.asarray(powers, dtype=float)
    per = np.asarray(periods, dtype=float)
    # Local maxima: power[i] > both neighbours.
    if p.size < 3:
        idxs = [int(np.argmax(p))]
    else:
        interior = (p[1:-1] > p[:-2]) & (p[1:-1] > p[2:])
        idxs = list((np.where(interior)[0] + 1).tolist())
        # Fall back to global argmax if no interior local-max found.
        if not idxs:
            idxs = [int(np.argmax(p))]
    # Sort by descending power, take top n.
    idxs.sort(key=lambda i: p[i], reverse=True)
    out = []
    for i in idxs[:n]:
        out.append({"period_days": float(per[i]), "power": float(p[i])})
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", required=True, type=Path)
    ap.add_argument("--time-col", type=int, default=0)
    ap.add_argument("--flux-col", type=int, default=1)
    ap.add_argument("--flag-col", type=int, default=None)
    ap.add_argument("--err-col", type=int, default=None)
    ap.add_argument("--min-period", type=float, default=None)
    ap.add_argument("--max-period", type=float, default=None)
    ap.add_argument("--top", type=int, default=5)
    ap.add_argument("--delimiter", type=str, default=None,
                    help="Column delimiter; default any whitespace.")
    args = ap.parse_args(argv)

    try:
        import lightkurve as lk
    except ImportError as exc:
        print(f"ERROR: lightkurve not installed: {exc}", file=sys.stderr)
        return 1

    try:
        time, flux, err = load_columns(
            args.data,
            delimiter=args.delimiter,
            time_col=args.time_col,
            flux_col=args.flux_col,
            flag_col=args.flag_col,
            err_col=args.err_col,
        )
    except Exception as exc:
        print(f"ERROR: failed to load {args.data}: {exc}", file=sys.stderr)
        return 1

    if time.size == 0:
        print("ERROR: no finite rows after filtering", file=sys.stderr)
        return 1

    lc = lk.LightCurve(time=time, flux=flux, flux_err=err)

    kw = {}
    if args.min_period is not None:
        kw["minimum_period"] = args.min_period
    if args.max_period is not None:
        kw["maximum_period"] = args.max_period

    try:
        pg = lc.to_periodogram(**kw)
    except Exception as exc:
        print(f"ERROR: to_periodogram failed: {exc}", file=sys.stderr)
        return 1

    period_arr = np.asarray(pg.period.value, dtype=float)
    power_arr = np.asarray(pg.power.value, dtype=float)

    result = {
        "strongest_period_days": float(pg.period_at_max_power.value),
        "max_power": float(pg.max_power.value),
        "n_points": int(time.size),
        "min_period_searched": float(np.nanmin(period_arr)),
        "max_period_searched": float(np.nanmax(period_arr)),
        "top_peaks": top_peaks(period_arr, power_arr, args.top),
    }
    json.dump(result, sys.stdout)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())

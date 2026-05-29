#!/usr/bin/env python3
"""Run Transit Least Squares (TLS) on a light curve.

Wraps `transitleastsquares.transitleastsquares(...).power(...)` with
sensible defaults for exoplanet transit search. Supports a broad initial
search (no period bounds) and a refinement search (narrow `--min-period`
/ `--max-period` window around a candidate).

Inputs
------
--data PATH       Whitespace- or comma-delimited text light curve.
--time-col INT    Zero-based column index for time. Default 0.
--flux-col INT    Zero-based column index for flux. Default 1.
--flag-col INT    Optional zero-based column index for quality flag.
                  When set, rows with non-zero flag are dropped.
--err-col INT     Zero-based column index for flux uncertainty.
                  REQUIRED unless --no-err is set — TLS weights points
                  by their uncertainties. Default 2.
--no-err          Allow running without flux uncertainties. NOT recommended;
                  emits a warning to stderr.
--min-period F    Optional minimum period (days). Use to refine a candidate.
--max-period F    Optional maximum period (days). Use to refine a candidate.
--refine-around F Optional. Convenience: refine within ±--refine-pct of this
                  candidate period (overrides --min-period/--max-period).
--refine-pct F    Refinement half-width as a fraction (default 0.05 = ±5%).
--delimiter STR   Column delimiter. Default: whitespace (any).

Output (stdout, JSON)
---------------------
{
  "period_days": float,                   # best-fit orbital period
  "period_uncertainty_days": float,
  "T0_days": float,                       # transit epoch (mid-transit time)
  "duration_days": float,
  "depth": float,                         # transit depth (1.0 = no transit)
  "snr": float,                           # signal-to-noise ratio
  "sde": float,                           # Signal Detection Efficiency
  "min_period_searched": float,
  "max_period_searched": float,
  "n_points": int,
  "transits_observed": int,
  "transits_in_data_gaps": int            # if > 0, watch for period * 2 aliasing
}

Errors go to stderr; exit 1 on any failure.

Notes
-----
- Preprocessing (quality cut, sigma-clip, flatten) is OUT OF SCOPE here.
  Run `light-curve-preprocessing` first.
- For a *broad* search, omit period bounds. For a *refined* search, pass
  --refine-around <candidate> (the ±--refine-pct window matches the
  canonical "refine to ±5%" pattern from the curated SKILL.md).
"""
from __future__ import annotations

import argparse
import json
import sys
import warnings
from pathlib import Path

import numpy as np


def load_columns(
    path,
    *,
    delimiter,
    time_col,
    flux_col,
    flag_col,
    err_col,
):
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


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", required=True, type=Path)
    ap.add_argument("--time-col", type=int, default=0)
    ap.add_argument("--flux-col", type=int, default=1)
    ap.add_argument("--flag-col", type=int, default=None)
    ap.add_argument("--err-col", type=int, default=2)
    ap.add_argument("--no-err", action="store_true",
                    help="Run without flux uncertainties (not recommended).")
    ap.add_argument("--min-period", type=float, default=None)
    ap.add_argument("--max-period", type=float, default=None)
    ap.add_argument("--refine-around", type=float, default=None,
                    help="Candidate period; refine within ±--refine-pct.")
    ap.add_argument("--refine-pct", type=float, default=0.05)
    ap.add_argument("--delimiter", type=str, default=None,
                    help="Column delimiter; default any whitespace.")
    args = ap.parse_args(argv)

    try:
        import transitleastsquares as tls
    except ImportError as exc:
        print(f"ERROR: transitleastsquares not installed: {exc}", file=sys.stderr)
        return 1

    err_col = None if args.no_err else args.err_col

    try:
        time, flux, err = load_columns(
            args.data,
            delimiter=args.delimiter,
            time_col=args.time_col,
            flux_col=args.flux_col,
            flag_col=args.flag_col,
            err_col=err_col,
        )
    except Exception as exc:
        print(f"ERROR: failed to load {args.data}: {exc}", file=sys.stderr)
        return 1

    if time.size == 0:
        print("ERROR: no finite rows after filtering", file=sys.stderr)
        return 1

    if args.no_err:
        print("WARNING: running TLS without flux_err — points cannot be properly "
              "weighted; results will be less reliable.", file=sys.stderr)

    if args.refine_around is not None:
        pct = abs(args.refine_pct)
        min_period = args.refine_around * (1.0 - pct)
        max_period = args.refine_around * (1.0 + pct)
    else:
        min_period = args.min_period
        max_period = args.max_period

    try:
        if err is not None:
            model = tls.transitleastsquares(time, flux, err)
        else:
            model = tls.transitleastsquares(time, flux)
    except Exception as exc:
        print(f"ERROR: TLS construction failed: {exc}", file=sys.stderr)
        return 1

    kw = {"show_progress_bar": False, "verbose": False}
    if min_period is not None:
        kw["period_min"] = float(min_period)
    if max_period is not None:
        kw["period_max"] = float(max_period)

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            result = model.power(**kw)
    except Exception as exc:
        print(f"ERROR: TLS power search failed: {exc}", file=sys.stderr)
        return 1

    periods_tested = np.asarray(getattr(result, "periods", []), dtype=float)
    min_searched = float(np.nanmin(periods_tested)) if periods_tested.size else float("nan")
    max_searched = float(np.nanmax(periods_tested)) if periods_tested.size else float("nan")

    out = {
        "period_days": float(result.period),
        "period_uncertainty_days": float(result.period_uncertainty),
        "T0_days": float(result.T0),
        "duration_days": float(result.duration),
        "depth": float(result.depth),
        "snr": float(result.snr),
        "sde": float(result.SDE),
        "min_period_searched": min_searched,
        "max_period_searched": max_searched,
        "n_points": int(time.size),
        "transits_observed": int(getattr(result, "transit_count", 0) or 0),
        "transits_in_data_gaps": int(getattr(result, "empty_transit_count", 0) or 0),
    }
    json.dump(out, sys.stdout)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())

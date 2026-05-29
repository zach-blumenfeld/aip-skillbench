#!/usr/bin/env python3
"""End-to-end transit detection pipeline.

Implements the canonical TLS recipe for finding an exoplanet period from a
TESS-style light curve obscured by stellar activity:

  load -> quality flag filter -> sigma=3 outlier removal -> flatten
  -> TLS broad search -> TLS refined search (+/- 5%) around candidate

Why this script exists: every step here is mechanical. Hand-coding the
preprocessing/refinement sequence repeatedly drifts on sigma, window length,
or refinement window. This script pins the choices that the workflow doc
recommends so the pipeline is reproducible.

Usage:
  python detect_period.py <lc_path> [--out PATH] [--delimiter STR]
                          [--flag-col INT] [--flag-good VALUE]
                          [--no-refine] [--refine-frac FLOAT]
                          [--period-min FLOAT] [--period-max FLOAT]

Input file: whitespace-delimited columns time, flux, quality_flag, flux_err.
By default flag-good=0 (TESS convention: 0 means good).

Prints a JSON summary of {period, sde, snr, depth, t0, period_uncertainty,
n_points, refined} and (when --out is given) writes the period rounded to
5 decimal places to the output path on a single line.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Detect exoplanet period via TLS pipeline.")
    p.add_argument("lc_path", help="Path to light curve text file.")
    p.add_argument("--out", help="Optional path to write the period (rounded to 5 dp).")
    p.add_argument("--delimiter", default=None,
                   help="Column delimiter for np.loadtxt (default: any whitespace).")
    p.add_argument("--time-col", type=int, default=0)
    p.add_argument("--flux-col", type=int, default=1)
    p.add_argument("--flag-col", type=int, default=2,
                   help="Quality flag column index. Use -1 to skip flag filtering.")
    p.add_argument("--err-col", type=int, default=3,
                   help="Flux uncertainty column index. Use -1 if not present.")
    p.add_argument("--flag-good", type=float, default=0.0,
                   help="Value that means 'keep this row' in the flag column (TESS: 0).")
    p.add_argument("--outlier-sigma", type=float, default=3.0)
    p.add_argument("--no-refine", action="store_true",
                   help="Skip the refined TLS search around the candidate.")
    p.add_argument("--refine-frac", type=float, default=0.05,
                   help="Fractional half-width of refinement window (default 0.05 = +/-5%%).")
    p.add_argument("--period-min", type=float, default=None,
                   help="Optional minimum period (days) for the initial broad search.")
    p.add_argument("--period-max", type=float, default=None,
                   help="Optional maximum period (days) for the initial broad search.")
    return p.parse_args(argv)


def _load_columns(path: Path, args: argparse.Namespace) -> tuple[np.ndarray, np.ndarray, np.ndarray | None, np.ndarray | None]:
    data = np.loadtxt(str(path), delimiter=args.delimiter)
    if data.ndim != 2:
        raise SystemExit(f"Expected 2D array from {path}, got shape {data.shape}")
    time = data[:, args.time_col].astype(float)
    flux = data[:, args.flux_col].astype(float)
    flag = data[:, args.flag_col].astype(float) if args.flag_col >= 0 else None
    err = data[:, args.err_col].astype(float) if args.err_col >= 0 else None
    return time, flux, flag, err


def _filter_quality(time: np.ndarray, flux: np.ndarray, flag: np.ndarray | None,
                    err: np.ndarray | None, flag_good: float) -> tuple[np.ndarray, np.ndarray, np.ndarray | None]:
    if flag is None:
        return time, flux, err
    keep = flag == flag_good
    return time[keep], flux[keep], (err[keep] if err is not None else None)


def detect_period(args: argparse.Namespace) -> dict:
    import lightkurve as lk
    import transitleastsquares as tls

    time, flux, flag, err = _load_columns(Path(args.lc_path), args)
    time, flux, err = _filter_quality(time, flux, flag, err, args.flag_good)

    if err is None:
        raise SystemExit(
            "Flux uncertainty column not found. TLS requires flux_err for proper weighting. "
            "Pass --err-col with the correct column index."
        )

    lc = lk.LightCurve(time=time, flux=flux, flux_err=err)
    lc_clean = lc.remove_outliers(sigma=args.outlier_sigma)
    lc_flat = lc_clean.flatten()

    t_arr = lc_flat.time.value
    f_arr = lc_flat.flux.value
    e_arr = lc_flat.flux_err.value

    power_kwargs: dict = {"show_progress_bar": False, "verbose": False}
    if args.period_min is not None:
        power_kwargs["period_min"] = args.period_min
    if args.period_max is not None:
        power_kwargs["period_max"] = args.period_max

    pg = tls.transitleastsquares(t_arr, f_arr, e_arr)
    out = pg.power(**power_kwargs)

    refined = False
    period = float(out.period)
    sde = float(out.SDE)
    snr = float(out.snr)
    depth = float(out.depth)
    t0 = float(out.T0)
    p_unc = float(out.period_uncertainty)

    if not args.no_refine:
        rmin = period * (1.0 - args.refine_frac)
        rmax = period * (1.0 + args.refine_frac)
        pg2 = tls.transitleastsquares(t_arr, f_arr, e_arr)
        out2 = pg2.power(period_min=rmin, period_max=rmax,
                         show_progress_bar=False, verbose=False)
        period = float(out2.period)
        sde = float(out2.SDE)
        snr = float(out2.snr)
        depth = float(out2.depth)
        t0 = float(out2.T0)
        p_unc = float(out2.period_uncertainty)
        refined = True

    return {
        "period": period,
        "period_rounded_5dp": round(period, 5),
        "period_uncertainty": p_unc,
        "sde": sde,
        "snr": snr,
        "depth": depth,
        "t0": t0,
        "n_points_after_filter": int(t_arr.size),
        "refined": refined,
        "outlier_sigma": args.outlier_sigma,
    }


def main(argv: list[str]) -> int:
    args = _parse_args(argv)
    result = detect_period(args)
    print(json.dumps(result, indent=2))
    if args.out:
        Path(args.out).write_text(f"{result['period_rounded_5dp']:.5f}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

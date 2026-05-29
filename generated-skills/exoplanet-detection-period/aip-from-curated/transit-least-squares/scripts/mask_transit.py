#!/usr/bin/env python3
"""Mask the in-transit points of a known transit signal and write the
masked light curve to a new file. Used to search for additional planets
after a first detection.

Inputs
------
--data PATH        Whitespace- or comma-delimited text light curve.
--time-col INT     Zero-based column index for time. Default 0.
--flux-col INT     Zero-based column index for flux. Default 1.
--flag-col INT     Optional zero-based column index for quality flag;
                   rows with flag != 0 are dropped before masking.
--err-col INT      Zero-based column index for flux uncertainty. Default 2.
--period FLOAT     Orbital period of the known transit (days). Required.
--t0 FLOAT         Mid-transit time (days, same epoch as data). Required.
--duration FLOAT   Transit duration (days). Required.
--output PATH      Output light-curve file (CSV with header). Required.
--delimiter STR    Input delimiter. Default: any whitespace.

Output
------
CSV at --output with columns time,flux,flux_err (no flag column —
quality-bad rows are dropped if --flag-col was provided).

Errors go to stderr; exit 1 on any failure.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np


def load_columns(path, *, delimiter, time_col, flux_col, flag_col, err_col):
    data = np.loadtxt(path, delimiter=delimiter)
    if data.ndim == 1:
        data = data.reshape(1, -1)
    time = data[:, time_col]
    flux = data[:, flux_col]
    err = data[:, err_col]
    if flag_col is not None:
        good = data[:, flag_col] == 0
        time = time[good]
        flux = flux[good]
        err = err[good]
    finite = np.isfinite(time) & np.isfinite(flux) & np.isfinite(err)
    return time[finite], flux[finite], err[finite]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", required=True, type=Path)
    ap.add_argument("--time-col", type=int, default=0)
    ap.add_argument("--flux-col", type=int, default=1)
    ap.add_argument("--flag-col", type=int, default=None)
    ap.add_argument("--err-col", type=int, default=2)
    ap.add_argument("--period", type=float, required=True)
    ap.add_argument("--t0", type=float, required=True)
    ap.add_argument("--duration", type=float, required=True)
    ap.add_argument("--output", required=True, type=Path)
    ap.add_argument("--delimiter", type=str, default=None)
    args = ap.parse_args(argv)

    try:
        from transitleastsquares import transit_mask
    except ImportError as exc:
        print(f"ERROR: transitleastsquares not installed: {exc}", file=sys.stderr)
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

    mask = transit_mask(time, args.period, args.duration, args.t0)
    kept = ~mask
    n_in = int(time.size)
    n_kept = int(kept.sum())

    out = np.column_stack([time[kept], flux[kept], err[kept]])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    np.savetxt(
        args.output,
        out,
        delimiter=",",
        header="time,flux,flux_err",
        comments="",
        fmt="%.10g",
    )
    print(f"Masked {n_in - n_kept} of {n_in} points; wrote {n_kept} to {args.output}",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

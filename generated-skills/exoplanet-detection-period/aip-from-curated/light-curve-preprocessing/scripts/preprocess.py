#!/usr/bin/env python3
"""Canonical light-curve preprocessing pipeline.

Order (DO NOT REORDER — outliers can corrupt trend fits, and trend fits can
mis-flag transits as outliers):

  1. Load time / flux / flag / error columns from a delimited TXT.
  2. Apply quality-flag filter (configurable convention).
  3. Sigma-clip outliers via lightkurve.LightCurve.remove_outliers().
  4. Detrend via LightCurve.flatten() (Savitzky-Golay).
  5. Write cleaned (time, flux, flux_err) to an .npz.

Designed to feed BLS / TLS / Lomb-Scargle period searches. Defaults match
TESS transit-detection practice (sigma=3, lightkurve default window).
"""
import argparse
import sys

import lightkurve as lk
import numpy as np

FLAG_CONVENTIONS = {"good_is_zero", "bad_is_zero", "none"}


def load_lc_txt(path, delimiter):
    data = np.loadtxt(path, delimiter=delimiter)
    if data.ndim != 2 or data.shape[1] < 4:
        raise SystemExit(
            f"Expected >=4 columns (time, flux, flag, error); got shape {data.shape}"
        )
    return data[:, 0], data[:, 1], data[:, 2], data[:, 3]


def filter_quality(time, flux, flag, error, convention):
    if convention == "good_is_zero":
        mask = flag == 0
    elif convention == "bad_is_zero":
        mask = flag != 0
    elif convention == "none":
        return time, flux, error, len(time)
    else:
        raise SystemExit(f"Unknown flag convention: {convention}")
    return time[mask], flux[mask], error[mask], int(mask.sum())


def main():
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument(
        "input",
        help="Path to delimited TXT with columns: time, flux, flag, error",
    )
    p.add_argument(
        "--output",
        required=True,
        help="Where to save cleaned arrays (.npz with time, flux, flux_err)",
    )
    p.add_argument(
        "--delimiter",
        default=None,
        help="Column delimiter; default whitespace. Use ' ' for single-space, ',' for CSV.",
    )
    p.add_argument(
        "--flag-convention",
        choices=sorted(FLAG_CONVENTIONS),
        default="good_is_zero",
        help=(
            "good_is_zero = standard TESS/Kepler (keep flag==0); "
            "bad_is_zero = inverted (keep flag!=0); "
            "none = skip flag filtering."
        ),
    )
    p.add_argument(
        "--sigma",
        type=float,
        default=3.0,
        help=(
            "Sigma-clipping threshold for outlier removal. "
            "sigma=3 standard (~0.3%% removed); "
            "sigma=5 conservative; sigma=2 aggressive."
        ),
    )
    p.add_argument(
        "--window-length",
        type=int,
        default=None,
        help=(
            "Savitzky-Golay window for flatten() in cadences. "
            "Must be longer than transit duration but shorter than stellar "
            "rotation period. 100-200: short trends; 300-500: typical TESS; "
            "500-1000: long trends. Omit to use lightkurve's default."
        ),
    )
    p.add_argument(
        "--skip-flatten",
        action="store_true",
        help="Skip flatten() (use when target science needs the trend preserved or you'll detrend elsewhere).",
    )
    p.add_argument(
        "--skip-outlier-removal",
        action="store_true",
        help="Skip sigma clipping (use only when downstream method handles outliers itself).",
    )
    args = p.parse_args()

    time, flux, flag, error = load_lc_txt(args.input, delimiter=args.delimiter)
    n_total = len(time)
    print(f"loaded {n_total} cadences from {args.input}", file=sys.stderr)

    time, flux, error, n_q = filter_quality(
        time, flux, flag, error, args.flag_convention
    )
    print(
        f"quality filter [{args.flag_convention}]: kept {n_q}/{n_total} cadences",
        file=sys.stderr,
    )

    lc = lk.LightCurve(time=time, flux=flux, flux_err=error)

    if args.skip_outlier_removal:
        lc_clean = lc
        print("outlier removal: SKIPPED", file=sys.stderr)
    else:
        lc_clean, mask = lc.remove_outliers(sigma=args.sigma, return_mask=True)
        n_removed = int(np.sum(mask))
        print(
            f"sigma={args.sigma} clipping: kept {len(lc_clean)} cadences ({n_removed} removed)",
            file=sys.stderr,
        )

    if args.skip_flatten:
        lc_out = lc_clean
        print("flatten: SKIPPED", file=sys.stderr)
    else:
        if args.window_length is None:
            lc_out = lc_clean.flatten()
            print("flatten: window=lightkurve-default", file=sys.stderr)
        else:
            lc_out = lc_clean.flatten(window_length=args.window_length)
            print(f"flatten: window={args.window_length}", file=sys.stderr)

    out_time = np.asarray(lc_out.time.value)
    out_flux = np.asarray(lc_out.flux.value)
    out_err = np.asarray(lc_out.flux_err.value)

    np.savez(args.output, time=out_time, flux=out_flux, flux_err=out_err)
    print(f"wrote {len(out_time)} cadences to {args.output}", file=sys.stderr)
    print(args.output)


if __name__ == "__main__":
    main()

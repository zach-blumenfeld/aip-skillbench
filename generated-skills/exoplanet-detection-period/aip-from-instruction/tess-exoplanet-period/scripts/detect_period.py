#!/usr/bin/env python3
"""Detect the orbital period of a transiting exoplanet from a TESS-style
light curve where stellar activity masks the transit.

Pipeline
--------
1. Load 4-column whitespace-separated light curve (time MJD, normalized
   flux, quality flag, flux uncertainty).
2. Keep quality == 0 rows; drop NaN/inf; sort by time.
3. Detrend stellar activity with a Savitzky-Golay filter; window ~1 day
   (>> transit duration, ~ rotation timescale), polyorder 3.
4. Asymmetric sigma-clip the detrended flux (cut upward outliers harder
   than downward — transits are real downward dips).
5. Box-Least-Squares periodogram (astropy.timeseries.BoxLeastSquares)
   over durations 0.05–0.20 days with frequency_factor=5.
6. Refine the best period on a fine linear grid (±1%, 10k samples) so
   the answer has enough precision for 5-decimal rounding.
7. Write the period to the output file as one floating-point number
   rounded to `--decimals` (default 5). No header, no units.

Usage
-----
    python detect_period.py /root/data/tess_lc.txt /root/period.txt
    python detect_period.py in.txt out.txt --window-days 1.5 --decimals 5

Dependencies: numpy, scipy, astropy.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from astropy.stats import sigma_clip
from astropy.timeseries import BoxLeastSquares
from scipy.signal import savgol_filter


def load_lightcurve(path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Load a 4-column whitespace-separated TESS-style light curve.

    Returns (time, flux, quality, flux_uncertainty) as float64 arrays.
    """
    data = np.loadtxt(path)
    if data.ndim != 2 or data.shape[1] < 4:
        raise ValueError(
            f"Expected >=4 columns in {path}, got shape {data.shape}"
        )
    t = data[:, 0].astype(np.float64)
    f = data[:, 1].astype(np.float64)
    q = data[:, 2].astype(np.float64)
    e = data[:, 3].astype(np.float64)
    return t, f, q, e


def quality_filter(
    t: np.ndarray, f: np.ndarray, q: np.ndarray, e: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Keep quality == 0 and drop non-finite rows. Sort by time."""
    mask = (q == 0) & np.isfinite(t) & np.isfinite(f) & np.isfinite(e)
    t, f, e = t[mask], f[mask], e[mask]
    order = np.argsort(t)
    return t[order], f[order], e[order]


def detrend_savgol(
    t: np.ndarray, f: np.ndarray, window_days: float = 1.0, polyorder: int = 3
) -> np.ndarray:
    """Divide out the slow stellar-activity envelope.

    Window is much larger than typical transit duration (~1–5 h) so dips
    survive, but small enough to track stellar rotation modulation.
    Cadence inferred from the median of np.diff(t).
    """
    if len(f) < 5:
        return f.copy()
    cadence = float(np.median(np.diff(t)))
    if cadence <= 0:
        cadence = (t.max() - t.min()) / max(len(t) - 1, 1)
    win = max(int(round(window_days / cadence)), 51)
    if win % 2 == 0:
        win += 1
    if win >= len(f):
        win = len(f) - 1 if len(f) % 2 == 0 else len(f) - 2
        win = max(win, polyorder + 2)
        if win % 2 == 0:
            win -= 1
    trend = savgol_filter(f, window_length=win, polyorder=polyorder)
    # Avoid divide-by-zero in pathological inputs.
    trend = np.where(np.abs(trend) < 1e-12, 1.0, trend)
    return f / trend


def asymmetric_clip(
    t: np.ndarray,
    f: np.ndarray,
    e: np.ndarray,
    sigma_upper: float = 3.0,
    sigma_lower: float = 6.0,
    maxiters: int = 5,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Clip upward outliers harder than downward.

    Transits are real downward outliers; clipping them symmetrically
    erases the signal. Flares and cosmic rays are upward outliers and
    should go.
    """
    clipped = sigma_clip(
        f,
        sigma_lower=sigma_lower,
        sigma_upper=sigma_upper,
        maxiters=maxiters,
        masked=True,
        copy=True,
    )
    keep = ~clipped.mask
    return t[keep], f[keep], e[keep]


def bls_search(
    t: np.ndarray,
    f: np.ndarray,
    e: np.ndarray,
    min_period: float = 0.5,
    baseline_divisor: float = 2.5,
    durations: np.ndarray | None = None,
    frequency_factor: float = 5.0,
) -> tuple[BoxLeastSquares, float, float]:
    """Run BLS autopower; return (bls_obj, best_period, best_power).

    Period grid: minimum 0.5 d, maximum baseline / baseline_divisor
    (≥2 full transits in window). durations default 0.05–0.20 d
    (~1.2–4.8 h), the typical short-period transit range.
    """
    if durations is None:
        durations = np.linspace(0.05, 0.20, 5)
    baseline = float(t.max() - t.min())
    max_period = baseline / baseline_divisor
    if max_period <= min_period:
        raise ValueError(
            f"Baseline too short ({baseline:.2f} d) for min_period {min_period}"
        )
    bls = BoxLeastSquares(t, f, dy=e)
    result = bls.autopower(
        durations,
        minimum_period=min_period,
        maximum_period=max_period,
        frequency_factor=frequency_factor,
    )
    periods = np.asarray(getattr(result.period, "value", result.period), dtype=float)
    powers = np.asarray(getattr(result.power, "value", result.power), dtype=float)
    idx = int(np.argmax(powers))
    return bls, float(periods[idx]), float(powers[idx])


def refine_peak(
    bls: BoxLeastSquares,
    period: float,
    durations: np.ndarray | None = None,
    frac: float = 0.01,
    n: int = 10_000,
) -> float:
    """Re-evaluate BLS on a fine linear grid around the coarse peak."""
    if durations is None:
        durations = np.linspace(0.05, 0.20, 5)
    grid = np.linspace(period * (1 - frac), period * (1 + frac), n)
    res = bls.power(grid, durations)
    powers = np.asarray(getattr(res.power, "value", res.power), dtype=float)
    return float(grid[int(np.argmax(powers))])


def detect_period(
    in_path: Path,
    window_days: float = 1.0,
    min_period: float = 0.5,
) -> tuple[float, float]:
    """End-to-end: load → filter → detrend → clip → BLS → refine.

    Returns (coarse_period_d, refined_period_d).
    """
    t, f, q, e = load_lightcurve(in_path)
    t, f, e = quality_filter(t, f, q, e)
    f_det = detrend_savgol(t, f, window_days=window_days)
    t2, f2, e2 = asymmetric_clip(t, f_det, e)
    bls, coarse, _ = bls_search(t2, f2, e2, min_period=min_period)
    refined = refine_peak(bls, coarse)
    return coarse, refined


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("input", type=Path, help="path to 4-col TESS light curve")
    ap.add_argument("output", type=Path, help="path to write the period to")
    ap.add_argument(
        "--decimals",
        type=int,
        default=5,
        help="rounding precision for the written period (default 5)",
    )
    ap.add_argument(
        "--window-days",
        type=float,
        default=1.0,
        help="Savitzky-Golay window in days (default 1.0)",
    )
    ap.add_argument(
        "--min-period",
        type=float,
        default=0.5,
        help="minimum BLS search period in days (default 0.5)",
    )
    args = ap.parse_args(argv)

    coarse, refined = detect_period(
        args.input,
        window_days=args.window_days,
        min_period=args.min_period,
    )
    args.output.write_text(f"{refined:.{args.decimals}f}\n")
    print(
        f"coarse_period_d={coarse:.6f}  "
        f"refined_period_d={refined:.{args.decimals}f}  "
        f"-> {args.output}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

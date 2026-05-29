#!/usr/bin/env python3
"""Iterative sine-fit detrending for strong stellar variability.

For each iteration, fits the dominant periodogram peak as a sine model and
divides it out. Repeat to remove multiple periodic components (e.g.,
stellar rotation + harmonics).

WARNING — destructive to ANY periodic signal in the light curve.
Do NOT use ahead of a periodogram-based transit search unless the transit
signal is shallow enough to survive sine-fit subtraction (rare). Prefer
preprocess.py's flatten() (Savitzky-Golay) for transit detection; it is
local and preserves short-duration dips.

Use this script when:
  - The dominant signal is high-frequency stellar variability (rotation,
    pulsation) whose periodogram peak is well-separated from any planetary
    period, AND
  - You explicitly want to subtract that variability before another type of
    analysis (NOT a periodogram search for the planet).
"""
import argparse
import sys

import lightkurve as lk
import numpy as np


def sine_fit_iteration(lc):
    pg = lc.to_periodogram()
    model = pg.model(time=lc.time, frequency=pg.frequency_at_max_power)
    out = lc.copy()
    out.flux = out.flux / model.flux
    return out, model


def main():
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("input", help="Input .npz with arrays: time, flux, flux_err")
    p.add_argument(
        "--output", required=True, help="Output .npz with detrended arrays"
    )
    p.add_argument(
        "--iterations",
        type=int,
        default=50,
        help="Sine-fit iterations (default 50). More iterations = more periodic content removed.",
    )
    args = p.parse_args()

    z = np.load(args.input)
    lc = lk.LightCurve(time=z["time"], flux=z["flux"], flux_err=z["flux_err"])

    for _ in range(args.iterations):
        lc, _ = sine_fit_iteration(lc)
    print(f"ran {args.iterations} sine-fit iterations", file=sys.stderr)

    np.savez(
        args.output,
        time=np.asarray(lc.time.value),
        flux=np.asarray(lc.flux.value),
        flux_err=np.asarray(lc.flux_err.value),
    )
    print(args.output)


if __name__ == "__main__":
    main()

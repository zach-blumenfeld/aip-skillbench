#!/usr/bin/env python3
"""Quick light-curve plot for visual preprocessing verification.

Reads an .npz with time, flux, flux_err and writes a PNG. Use to compare
raw vs. cleaned, before/after flatten, etc. Run after each preprocessing
stage so you can confirm: outliers gone, trend removed, transit dips
preserved (NOT smoothed flat).
"""
import argparse

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("input", help="Input .npz with arrays: time, flux, flux_err")
    p.add_argument("--output", required=True, help="PNG output path")
    p.add_argument("--title", default="Light curve")
    args = p.parse_args()

    z = np.load(args.input)
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.errorbar(
        z["time"],
        z["flux"],
        yerr=z["flux_err"],
        fmt=".",
        ms=1,
        ecolor="0.7",
        elinewidth=0.5,
    )
    ax.set_xlabel("Time")
    ax.set_ylabel("Flux")
    ax.set_title(args.title)
    fig.tight_layout()
    fig.savefig(args.output, dpi=120)
    print(args.output)


if __name__ == "__main__":
    main()

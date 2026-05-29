#!/usr/bin/env python3
"""Plot all candidate points with the Pareto frontier highlighted.

Optional companion to ``compute_pareto.py``. Two-objective case only —
higher-dimension frontiers require pairwise plots the caller chooses.

Usage::

    python visualize_pareto.py --all results.csv --frontier pareto.csv \\
        --x-col delta --y-col F1 \\
        --x-label "delta (minimize)" --y-label "F1 (maximize)" \\
        --output pareto.png
"""
import argparse
import sys


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all", required=True, help="CSV of all candidate points.")
    parser.add_argument(
        "--frontier", required=True, help="CSV of Pareto-optimal points."
    )
    parser.add_argument("--x-col", required=True)
    parser.add_argument("--y-col", required=True)
    parser.add_argument("--x-label", default=None)
    parser.add_argument("--y-label", default=None)
    parser.add_argument("--output", required=True, help="Output image path.")
    args = parser.parse_args(argv)

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import pandas as pd

    all_df = pd.read_csv(args.all)
    front_df = pd.read_csv(args.frontier)

    fig, ax = plt.subplots(figsize=(8, 6))
    ax.scatter(
        all_df[args.x_col], all_df[args.y_col], alpha=0.4, label="All candidates"
    )
    ax.scatter(
        front_df[args.x_col],
        front_df[args.y_col],
        color="red",
        s=80,
        marker="s",
        label="Pareto frontier",
    )
    ax.set_xlabel(args.x_label or args.x_col)
    ax.set_ylabel(args.y_label or args.y_col)
    ax.legend()
    fig.tight_layout()
    fig.savefig(args.output, dpi=120)
    print(f"Saved plot -> {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

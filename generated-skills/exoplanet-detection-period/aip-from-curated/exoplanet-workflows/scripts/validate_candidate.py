#!/usr/bin/env python3
"""Apply the workflow's signal-strength and false-positive thresholds.

Encodes the deterministic rules from the curated workflow:
  - SDE thresholds: <6 weak, 6-9 strong, >9 very strong
  - SNR threshold: >=7 reliable
  - Odd/even mismatch: > 3 * depth_err is a red flag (not planetary)
  - Period aliasing warning when n_transits_with_data is unusually low

Usage:
  python validate_candidate.py --sde 11.2 --snr 9.4 --depth 0.012 \
      [--depth-odd 0.011 --depth-even 0.012 --depth-err 0.0008] \
      [--n-transits 7 --n-transits-with-data 7] [--period 3.41]

Prints a JSON verdict {classification, confidence, issues, recommendations,
ok_to_report}. Exit code is 0 unless the input itself is malformed.
"""

from __future__ import annotations

import argparse
import json
import sys

SDE_VERY_STRONG = 9.0
SDE_STRONG = 6.0
SNR_RELIABLE = 7.0
ODD_EVEN_SIGMA = 3.0


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Validate a TLS/BLS transit candidate.")
    p.add_argument("--sde", type=float, required=True, help="Signal Detection Efficiency.")
    p.add_argument("--snr", type=float, required=True, help="Signal-to-noise ratio.")
    p.add_argument("--depth", type=float, default=None, help="Transit depth (fractional).")
    p.add_argument("--depth-odd", type=float, default=None,
                   help="Depth measured from odd-numbered transits.")
    p.add_argument("--depth-even", type=float, default=None,
                   help="Depth measured from even-numbered transits.")
    p.add_argument("--depth-err", type=float, default=None,
                   help="Uncertainty on the depth (for odd-even mismatch test).")
    p.add_argument("--n-transits", type=int, default=None,
                   help="Total transits expected in the time baseline.")
    p.add_argument("--n-transits-with-data", type=int, default=None,
                   help="Transits with on-source data (vs falling in gaps).")
    p.add_argument("--period", type=float, default=None, help="Candidate period (days).")
    return p.parse_args(argv)


def classify_sde(sde: float) -> tuple[str, str]:
    if sde > SDE_VERY_STRONG:
        return "very_strong", f"SDE {sde:.2f} > {SDE_VERY_STRONG}: very strong candidate."
    if sde > SDE_STRONG:
        return "strong", f"SDE {sde:.2f} > {SDE_STRONG}: strong candidate."
    return "weak", (
        f"SDE {sde:.2f} <= {SDE_STRONG}: weak signal, may be false positive. "
        "Re-check preprocessing (over-flattening?), data gaps over transits, or signal depth."
    )


def main(argv: list[str]) -> int:
    args = _parse_args(argv)
    issues: list[str] = []
    recommendations: list[str] = []

    classification, sde_msg = classify_sde(args.sde)
    if classification == "weak":
        issues.append(sde_msg)
        recommendations.append("Try less aggressive outlier removal or a longer flatten window.")
        recommendations.append("Check for data gaps coinciding with expected transit times.")
    else:
        recommendations.append(sde_msg)

    if args.snr < SNR_RELIABLE:
        issues.append(f"SNR {args.snr:.2f} < {SNR_RELIABLE}: needs additional validation.")
        recommendations.append("Visually inspect the phase-folded light curve at this period.")

    if (args.depth_odd is not None and args.depth_even is not None
            and args.depth_err is not None and args.depth_err > 0):
        diff = abs(args.depth_odd - args.depth_even)
        if diff > ODD_EVEN_SIGMA * args.depth_err:
            issues.append(
                f"Odd-even depth mismatch {diff:.4g} > {ODD_EVEN_SIGMA} * depth_err "
                f"({args.depth_err:.4g}). Likely eclipsing binary or artifact, not a planet."
            )
            recommendations.append(
                "Test the candidate period at 2x — the true orbital period may be double."
            )

    if (args.n_transits is not None and args.n_transits_with_data is not None
            and args.n_transits > 0):
        missing = args.n_transits - args.n_transits_with_data
        if missing >= 1 and args.n_transits_with_data < args.n_transits * 0.7:
            issues.append(
                f"{missing}/{args.n_transits} transits fall in data gaps. "
                "Period may be aliased."
            )
            recommendations.append(
                "Check the same target with period * 2 and period / 2 to rule out aliasing."
            )

    if args.period is not None and args.period > 0:
        recommendations.append(
            f"For final reporting, refine over [{args.period * 0.95:.4f}, "
            f"{args.period * 1.05:.4f}] days to improve precision."
        )

    ok_to_report = (
        args.sde > SDE_STRONG
        and args.snr >= SNR_RELIABLE
        and not any("Odd-even" in i for i in issues)
    )

    verdict = {
        "classification": classification,
        "ok_to_report": ok_to_report,
        "sde": args.sde,
        "snr": args.snr,
        "issues": issues,
        "recommendations": recommendations,
        "thresholds": {
            "sde_strong": SDE_STRONG,
            "sde_very_strong": SDE_VERY_STRONG,
            "snr_reliable": SNR_RELIABLE,
            "odd_even_sigma": ODD_EVEN_SIGMA,
        },
    }
    print(json.dumps(verdict, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

"""Compute powerlifting score-normalization coefficients.

Supports Dots, Wilks, and IPF GoodLift. Glossbrenner is documented in
references/formulas.md but not implemented here (depends on Schwartz/Malone
coefficients that are not in the curated source).

CLI:
  uv run scripts/score.py --system dots  --sex M --bodyweight-kg 92.04 --total-kg 1035
  uv run scripts/score.py --system wilks --sex F --bodyweight-kg 60    --total-kg 500
  uv run scripts/score.py --system ipf-gl --sex M --bodyweight-kg 92.04 --total-kg 1035 \
      --equipment Single --event SBD
"""

from __future__ import annotations

import argparse
import math
import sys

# Dots polynomial: a*bw^4 + b*bw^3 + c*bw^2 + d*bw + e, points = total * 500 / poly
DOTS_M = (-0.0000010930, 0.0007391293, -0.1918759221, 24.0900756, -307.75076)
DOTS_F = (-0.0000010706, 0.0005158568, -0.1126655495, 13.6175032, -57.96288)
DOTS_M_BOUNDS = (40.0, 210.0)
DOTS_F_BOUNDS = (40.0, 150.0)

# Wilks polynomial (ascending): a + b*x + c*x^2 + d*x^3 + e*x^4 + f*x^5
WILKS_M = (-216.0475144, 16.2606339, -0.002388645, -0.00113732, 7.01863e-06, -1.291e-08)
WILKS_F = (594.31747775582, -27.23842536447, 0.82112226871, -0.00930733913, 4.731582e-05, -9.054e-08)
WILKS_M_BOUNDS = (40.0, 201.9)
WILKS_F_BOUNDS = (26.51, 154.53)

# IPF GoodLift: points = total * max(0, 100 / (A - B * exp(-C * bw)))
# Parameters keyed by (sex, equipment, event).
IPF_GL: dict[tuple[str, str, str], tuple[float, float, float]] = {
    ("M", "Raw",    "SBD"): (1199.72839, 1025.18162, 0.009210),
    ("M", "Single", "SBD"): (1236.25115, 1449.21864, 0.01644),
    ("F", "Raw",    "SBD"): (610.32796,  1045.59282, 0.03048),
    ("F", "Single", "SBD"): (758.63878,  949.31382,  0.02435),
    ("M", "Raw",    "B"):   (320.98041,  281.40258,  0.01008),
    ("M", "Single", "B"):   (381.22073,  733.79378,  0.02398),
    ("F", "Raw",    "B"):   (142.40398,  442.52671,  0.04724),
    ("F", "Single", "B"):   (221.82209,  357.00377,  0.02937),
}


def _normalize_sex(sex: str) -> str:
    s = sex.strip().upper()
    if s in ("M", "MX"):
        return "M"
    if s == "F":
        return "F"
    raise ValueError(f"unknown sex: {sex!r} (expected M, F, or Mx)")


def _normalize_equipment(equip: str) -> str:
    e = equip.strip().lower()
    if e in ("raw", "wraps", "straps"):
        return "Raw"
    if e in ("single", "single-ply", "multi", "multi-ply", "unlimited"):
        return "Single"
    raise ValueError(f"unknown equipment: {equip!r}")


def _normalize_event(event: str) -> str:
    e = event.strip().upper()
    if e == "SBD":
        return "SBD"
    if e == "B":
        return "B"
    raise ValueError(f"unknown event: {event!r} (expected SBD or B)")


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _poly_ascending(coeffs: tuple[float, ...], x: float) -> float:
    """Evaluate coeffs[0] + coeffs[1]*x + coeffs[2]*x^2 + ... at x."""
    total = 0.0
    for i, c in enumerate(coeffs):
        total += c * (x ** i)
    return total


def dots(sex: str, bodyweight_kg: float, total_kg: float) -> float:
    if bodyweight_kg <= 0 or total_kg <= 0:
        return 0.0
    s = _normalize_sex(sex)
    if s == "M":
        bw = _clamp(bodyweight_kg, *DOTS_M_BOUNDS)
        a, b, c, d, e = DOTS_M
    else:
        bw = _clamp(bodyweight_kg, *DOTS_F_BOUNDS)
        a, b, c, d, e = DOTS_F
    denom = a * bw**4 + b * bw**3 + c * bw**2 + d * bw + e
    return total_kg * (500.0 / denom)


def wilks(sex: str, bodyweight_kg: float, total_kg: float) -> float:
    if bodyweight_kg <= 0 or total_kg <= 0:
        return 0.0
    s = _normalize_sex(sex)
    if s == "M":
        bw = _clamp(bodyweight_kg, *WILKS_M_BOUNDS)
        coeffs = WILKS_M
    else:
        bw = _clamp(bodyweight_kg, *WILKS_F_BOUNDS)
        coeffs = WILKS_F
    denom = _poly_ascending(coeffs, bw)
    return total_kg * (500.0 / denom)


def ipf_gl(sex: str, equipment: str, event: str, bodyweight_kg: float, total_kg: float) -> float:
    # IPF GL is undefined below 35 kg and treats zero total as no result.
    if bodyweight_kg < 35.0 or total_kg <= 0:
        return 0.0
    params = IPF_GL.get((_normalize_sex(sex), _normalize_equipment(equipment), _normalize_event(event)))
    if params is None:
        return 0.0
    A, B, C = params
    denom = A - B * math.exp(-C * bodyweight_kg)
    if denom == 0:
        return 0.0
    return total_kg * max(0.0, 100.0 / denom)


def main() -> int:
    p = argparse.ArgumentParser(description="Compute a powerlifting score-normalization coefficient.")
    p.add_argument("--system", required=True, choices=["dots", "wilks", "ipf-gl"])
    p.add_argument("--sex", required=True, help="M, F, or Mx")
    p.add_argument("--bodyweight-kg", type=float, required=True)
    p.add_argument("--total-kg", type=float, required=True)
    p.add_argument("--equipment", help="Raw / Wraps / Straps / Single / Multi / Unlimited (required for ipf-gl)")
    p.add_argument("--event", help="SBD or B (required for ipf-gl)")
    p.add_argument("--round", type=int, default=3, help="decimal places; use -1 to skip rounding")
    args = p.parse_args()

    try:
        if args.system == "dots":
            v = dots(args.sex, args.bodyweight_kg, args.total_kg)
        elif args.system == "wilks":
            v = wilks(args.sex, args.bodyweight_kg, args.total_kg)
        elif args.system == "ipf-gl":
            if args.equipment is None or args.event is None:
                print("ipf-gl requires --equipment and --event", file=sys.stderr)
                return 2
            v = ipf_gl(args.sex, args.equipment, args.event, args.bodyweight_kg, args.total_kg)
        else:
            return 2
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if args.round >= 0:
        v = round(v, args.round)
    print(v)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

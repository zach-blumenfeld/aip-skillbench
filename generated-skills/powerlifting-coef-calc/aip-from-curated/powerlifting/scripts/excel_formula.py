"""Generate Excel formula strings for powerlifting score-normalization coefficients.

Outputs `=ROUND(IF(sex_cell="M", <male branch>, <female branch>), n)` style
formulas that reference per-row sex / bodyweight / total cells. Use when the
deliverable is a live spreadsheet formula rather than a precomputed number.

CLI:
  uv run scripts/excel_formula.py --system dots  --sex-cell B2 --bw-cell C2 --total-cell G2
  uv run scripts/excel_formula.py --system wilks --sex-cell B2 --bw-cell C2 --total-cell G2
  uv run scripts/excel_formula.py --system ipf-gl --sex-cell B2 --bw-cell C2 --total-cell G2 \
      --equipment Single --event SBD
"""

from __future__ import annotations

import argparse
import sys

DOTS_M = (-0.0000010930, 0.0007391293, -0.1918759221, 24.0900756, -307.75076)
DOTS_F = (-0.0000010706, 0.0005158568, -0.1126655495, 13.6175032, -57.96288)
DOTS_M_BOUNDS = (40.0, 210.0)
DOTS_F_BOUNDS = (40.0, 150.0)

WILKS_M = (-216.0475144, 16.2606339, -0.002388645, -0.00113732, 7.01863e-06, -1.291e-08)
WILKS_F = (594.31747775582, -27.23842536447, 0.82112226871, -0.00930733913, 4.731582e-05, -9.054e-08)
WILKS_M_BOUNDS = (40.0, 201.9)
WILKS_F_BOUNDS = (26.51, 154.53)

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


def _clamp_expr(cell: str, lo: float, hi: float) -> str:
    return f"MAX({lo},MIN({hi},{cell}))"


def _dots_branch(bw_cell: str, total_cell: str,
                 coeffs: tuple[float, float, float, float, float],
                 bounds: tuple[float, float]) -> str:
    a, b, c, d, e = coeffs
    bw = _clamp_expr(bw_cell, *bounds)
    poly = (
        f"({a}*POWER({bw},4)"
        f"+{b}*POWER({bw},3)"
        f"+{c}*POWER({bw},2)"
        f"+{d}*{bw}"
        f"+{e})"
    )
    return f"{total_cell}*(500/{poly})"


def dots_formula(sex_cell: str, bw_cell: str, total_cell: str, round_places: int = 3) -> str:
    male = _dots_branch(bw_cell, total_cell, DOTS_M, DOTS_M_BOUNDS)
    female = _dots_branch(bw_cell, total_cell, DOTS_F, DOTS_F_BOUNDS)
    body = f'IF({sex_cell}="M",{male},{female})'
    return f"=ROUND({body},{round_places})" if round_places >= 0 else f"={body}"


def _wilks_branch(bw_cell: str, total_cell: str,
                  coeffs: tuple[float, float, float, float, float, float],
                  bounds: tuple[float, float]) -> str:
    a, b, c, d, e, f = coeffs
    bw = _clamp_expr(bw_cell, *bounds)
    poly = (
        f"({a}"
        f"+{b}*{bw}"
        f"+{c}*POWER({bw},2)"
        f"+{d}*POWER({bw},3)"
        f"+{e}*POWER({bw},4)"
        f"+{f}*POWER({bw},5))"
    )
    return f"{total_cell}*(500/{poly})"


def wilks_formula(sex_cell: str, bw_cell: str, total_cell: str, round_places: int = 3) -> str:
    male = _wilks_branch(bw_cell, total_cell, WILKS_M, WILKS_M_BOUNDS)
    female = _wilks_branch(bw_cell, total_cell, WILKS_F, WILKS_F_BOUNDS)
    body = f'IF({sex_cell}="M",{male},{female})'
    return f"=ROUND({body},{round_places})" if round_places >= 0 else f"={body}"


def _normalize_equipment_key(equip: str) -> str:
    e = equip.strip().lower()
    if e in ("raw", "wraps", "straps"):
        return "Raw"
    if e in ("single", "single-ply", "multi", "multi-ply", "unlimited"):
        return "Single"
    raise SystemExit(f"unknown equipment: {equip!r}")


def _normalize_event_key(event: str) -> str:
    ev = event.strip().upper()
    if ev not in ("SBD", "B"):
        raise SystemExit(f"unknown event: {event!r} (expected SBD or B)")
    return ev


def ipf_gl_formula(sex_cell: str, bw_cell: str, total_cell: str,
                   equipment: str, event: str, round_places: int = 2) -> str:
    eq_key = _normalize_equipment_key(equipment)
    ev_key = _normalize_event_key(event)
    m_params = IPF_GL[("M", eq_key, ev_key)]
    f_params = IPF_GL[("F", eq_key, ev_key)]

    def branch(params: tuple[float, float, float]) -> str:
        A, B, C = params
        denom = f"({A}-{B}*EXP(-{C}*{bw_cell}))"
        return f"{total_cell}*MAX(0,100/{denom})"

    body = f'IF({sex_cell}="M",{branch(m_params)},{branch(f_params)})'
    return f"=ROUND({body},{round_places})" if round_places >= 0 else f"={body}"


def main() -> int:
    p = argparse.ArgumentParser(description="Build an Excel formula for a powerlifting coefficient.")
    p.add_argument("--system", required=True, choices=["dots", "wilks", "ipf-gl"])
    p.add_argument("--sex-cell", required=True, help="cell holding the sex character, e.g. B2")
    p.add_argument("--bw-cell", required=True, help="cell holding the bodyweight in kg")
    p.add_argument("--total-cell", required=True, help="cell holding the total lifted in kg")
    p.add_argument("--equipment", help="Raw / Wraps / Straps / Single / Multi / Unlimited (for ipf-gl)")
    p.add_argument("--event", help="SBD or B (for ipf-gl)")
    p.add_argument("--round", type=int, default=3, help="decimal places; use -1 to skip ROUND()")
    args = p.parse_args()

    if args.system == "dots":
        print(dots_formula(args.sex_cell, args.bw_cell, args.total_cell, args.round))
    elif args.system == "wilks":
        print(wilks_formula(args.sex_cell, args.bw_cell, args.total_cell, args.round))
    elif args.system == "ipf-gl":
        if not args.equipment or not args.event:
            print("ipf-gl requires --equipment and --event", file=sys.stderr)
            return 2
        print(ipf_gl_formula(args.sex_cell, args.bw_cell, args.total_cell,
                             args.equipment, args.event, args.round))
    else:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

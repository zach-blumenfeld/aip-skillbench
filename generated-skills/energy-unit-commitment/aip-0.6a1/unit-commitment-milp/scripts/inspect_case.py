"""Start step: parse the UC case, run parser-level checks, profile it for later steps."""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # find uc_core under any launcher
import uc_core as U  # noqa: E402


def main():
    st = U.read_stdin()
    path = st["network_path"]
    if not os.path.isfile(path):
        sys.exit(f"network_path not found: {path}")
    rdir = os.path.dirname(os.path.abspath(st["report_path"])) or "."
    if not os.path.isdir(rdir):
        sys.exit(f"report directory does not exist: {rdir}")
    if float(st["time_limit_s"]) <= 0 or not (0 <= float(st["mip_rel_gap"]) < 1):
        sys.exit("time_limit_s must be > 0 and 0 <= mip_rel_gap < 1")
    case, issues = U.load_case(path)
    T = case["T"]
    th, rn = case["thermal"], case["renewable"]
    cap = sum(g["pmax"] for g in th)
    rmax = np.sum([r["max"] for r in rn], axis=0) if rn else np.zeros(T)
    rmin = np.sum([r["min"] for r in rn], axis=0) if rn else np.zeros(T)
    must = sum(g["pmin"] for g in th if g["must_run"])
    peak = float(np.max(case["demand"] + case["reserves"]))
    if cap + float(np.max(rmax)) < peak:
        issues.append(f"peak demand+reserve {peak:.1f} exceeds total thermal capacity + max renewable; likely infeasible")
    if np.any(rmin + must > case["demand"] + U.TOL):
        issues.append("renewable minimum plus must-run minimum exceeds demand in some hour (over-generation risk)")
    nonconvex = [g["name"] for g in th if not U.is_convex(g)]
    profile = {
        "time_periods": T,
        "report_hour_labels": f"1..{T}",
        "num_thermal_generators": len(th),
        "num_renewable_generators": len(rn),
        "demand_MW_min_max": [float(case["demand"].min()), float(case["demand"].max())],
        "reserve_MW_min_max": [float(case["reserves"].min()), float(case["reserves"].max())],
        "thermal_capacity_MW": cap,
        "must_run_units": [g["name"] for g in th if g["must_run"]],
        "units_on_at_t0": sum(g["on0"] for g in th),
        "units_with_initial_min_up_obligation": [g["name"] for g in th if g["on0"] and g["ut"] > g["up0"]],
        "units_with_initial_min_down_obligation": [g["name"] for g in th if not g["on0"] and g["dt"] > g["down0"]],
        "renewables_with_min_below_max": int(sum(bool(np.any(r["min"] < r["max"] - U.TOL)) for r in rn)),
        "renewable_hourly_max_total_MW_peak": float(np.max(rmax)),
        "renewable_hourly_min_total_MW_peak": float(np.max(rmin)),
        "startup_tier_counts": sorted({len(g["startup"]) for g in th}),
        "nonconvex_cost_units": nonconvex,
        "cost_curve_convention": "total cost at MW breakpoints; first point = cost at minimum output while online",
    }
    U.emit({"case_profile": profile, "parse_issues": issues})


if __name__ == "__main__":
    main()

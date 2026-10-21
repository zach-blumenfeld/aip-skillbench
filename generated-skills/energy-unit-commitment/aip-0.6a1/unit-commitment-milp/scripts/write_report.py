"""Re-validate the extracted schedule, recompute cost and summaries, write the report JSON,
then read it back and check it against the required format."""
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # find uc_core under any launcher
import uc_core as U  # noqa: E402

CHECK_KEYS = ["demand_balance", "spinning_reserve", "reserve_deliverability", "generator_limits", "must_run",
              "ramping", "minimum_up_down", "startup_shutdown_logic", "initial_conditions", "renewable_limits",
              "cost_consistency"]
STATUSES = {"optimal", "feasible", "time_limit_feasible", "suboptimal_feasible", "heuristic_feasible"}


def main():
    st = U.read_stdin()
    opts = {k: bool(st[k]) for k in ("renewables_curtailable", "renewable_reserve_allowed", "enforce_post_horizon")}
    case, _ = U.load_case(st["network_path"])
    with open(st["schedule_path"]) as f:
        blob = json.load(f)
    sched, info = blob["schedule"], blob["solve_info"]
    val = U.validate(case, sched, opts, info.get("model_objective"))
    if not val["ok"]:
        sys.exit(f"schedule failed re-validation; not writing report: {val['failures']}")
    status = info["solver_status"]
    if status not in STATUSES:
        sys.exit(f"solver status {status!r} has no incumbent; not writing report")
    gap = info.get("reported_mip_gap")
    T = case["T"]
    order_t = {g["name"]: i for i, g in enumerate(case["thermal"])}
    order_r = {r["name"]: i for i, r in enumerate(case["renewable"])}
    hourly = val["hourly"]
    report = {
        "case_name": "unit_commitment_schedule",
        "summary": {
            "solver_status": status,
            "objective_cost": round(val["recomputed_cost"], 4),
            "reported_mip_gap": None if gap is None else max(0.0, float(gap)),
            "time_periods": T,
            "num_thermal_generators": len(case["thermal"]),
            "num_renewable_generators": len(case["renewable"]),
            "total_startups": val["total_startups"],
            "total_shutdowns": val["total_shutdowns"],
            "max_demand_balance_violation_MW": round(val["max_demand_balance_violation_MW"], 6),
            "max_reserve_shortfall_MW": round(val["max_reserve_shortfall_MW"], 6),
        },
        "thermal_generators": sorted(sched["thermal"], key=lambda s: order_t[s["name"]]),
        "renewable_generators": sorted(sched["renewable"], key=lambda s: order_r[s["name"]]),
        "hourly_summary": [{
            "hour": t + 1,
            "demand_MW": float(case["demand"][t]),
            "thermal_generation_MW": round(hourly["thermal"][t], 6),
            "renewable_generation_MW": round(hourly["renewable"][t], 6),
            "reserve_requirement_MW": float(case["reserves"][t]),
            "scheduled_spinning_reserve_MW": round(hourly["reserve"][t], 6),
        } for t in range(T)],
        "constraint_check": {k: val["checks"][k] for k in CHECK_KEYS},
    }
    with open(st["report_path"], "w") as f:
        json.dump(report, f, indent=2)
    # read back and check the written file
    with open(st["report_path"]) as f:
        back = json.load(f)
    problems = []
    if set(back) != {"case_name", "summary", "thermal_generators", "renewable_generators", "hourly_summary", "constraint_check"}:
        problems.append("top-level keys differ from the required format")
    if len(back["hourly_summary"]) != T or back["hourly_summary"][0]["hour"] != 1:
        problems.append("hourly_summary length/labels wrong")
    for s in back["thermal_generators"]:
        if any(len(s[k]) != T for k in ("commitment", "production_MW", "reserve_MW", "startup", "shutdown")):
            problems.append(f"{s['name']}: array length != {T}")
    if any(not math.isfinite(x) for s in back["thermal_generators"] for x in s["production_MW"] + s["reserve_MW"]):
        problems.append("non-finite numbers in thermal arrays")
    if any(v != "pass" for v in back["constraint_check"].values()):
        problems.append("a constraint_check is not pass")
    if problems:
        sys.exit("report read-back failed: " + "; ".join(problems))
    U.emit({"report_summary": {"report_path": st["report_path"], **back["summary"],
                               "constraint_check": back["constraint_check"]}})


if __name__ == "__main__":
    main()

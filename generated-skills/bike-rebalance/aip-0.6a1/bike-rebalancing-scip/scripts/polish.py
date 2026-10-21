"""Restart route search from the written report, re-solve SCIP warm-started with both plans
under a longer limit, and keep the better report."""
import json
from pathlib import Path

import rebalance_core as rc


def main():
    state = rc.read_stdin()
    radius = float(state["earth_radius_miles"])
    rules = rc.rules_from_state(state)
    try:
        inst = rc.load_instance(state["data_path"])
        current = json.loads(Path(state["report_path"]).read_text())
        m, h = rc.build_model(inst, radius, rules)
        rc.add_subtour_separator(m, h)
        current_plan = rc.plan_from_report(inst, current)
        rc.add_plan_as_solution(m, h, current_plan)
        start = [[i for i, _ in veh["stops"]] for veh in current_plan]
        left = rc.warm_start(m, h, inst, radius, rules, min(float(state["polish_time_limit_seconds"]), 840.0),
                             seed=1, start_routes=start)
        status, _, gap = rc.solve(m, left)
        report = rc.build_report(inst, radius, rc.plan_from_model(m, h))
    except Exception as exc:
        rc.fail(f"polish failed: {type(exc).__name__}: {exc}")
    if report["summary"]["objective"] <= current["summary"]["objective"] + 1e-9:
        rc.write_report(state["report_path"], report)
    else:
        report = current
    rc.emit({"polish_status": status,
             "polish_objective": report["summary"]["objective"],
             "polish_gap": gap})


if __name__ == "__main__":
    main()

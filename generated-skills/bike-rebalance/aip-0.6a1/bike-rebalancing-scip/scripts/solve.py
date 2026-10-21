"""Route-search warm start, then the rebalancing MIP in SCIP; write report.json from the incumbent.

time_limit_seconds covers both: about a tenth (3-15 s) goes to route search, the rest to SCIP.
"""
import rebalance_core as rc


def main():
    state = rc.read_stdin()
    radius = float(state["earth_radius_miles"])
    rules = rc.rules_from_state(state)
    try:
        inst = rc.load_instance(state["data_path"])
        m, h = rc.build_model(inst, radius, rules)
        rc.add_subtour_separator(m, h)
        left = rc.warm_start(m, h, inst, radius, rules, min(float(state["time_limit_seconds"]), 540.0))
        status, objective, gap = rc.solve(m, left)
        report = rc.build_report(inst, radius, rc.plan_from_model(m, h))
    except Exception as exc:
        rc.fail(f"solve failed: {type(exc).__name__}: {exc}")
    if abs(report["summary"]["objective"] - objective) > 1e-4 * max(1.0, abs(objective)):
        rc.fail(f"report objective {report['summary']['objective']} != SCIP objective {objective}")
    rc.write_report(state["report_path"], report)
    rc.emit({"solve_status": status,
             "solve_objective": report["summary"]["objective"],
             "solve_gap": gap})


if __name__ == "__main__":
    main()

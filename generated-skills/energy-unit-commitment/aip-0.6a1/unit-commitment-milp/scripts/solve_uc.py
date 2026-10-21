"""Build and solve the UC MILP with HiGHS (scipy.optimize.milp), extract actual-MW arrays,
and validate them independently against the input data."""
import json
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # find uc_core under any launcher
import uc_core as U  # noqa: E402

MAX_TIME_LIMIT_S = 780.0  # leaves room for build + polish inside the step's 900 s timeout


def main():
    st = U.read_stdin()
    opts = {k: bool(st[k]) for k in ("renewables_curtailable", "renewable_reserve_allowed", "enforce_post_horizon")}
    case, _ = U.load_case(st["network_path"])
    t0 = time.time()
    sched, info = U.build_and_solve(case, opts, min(float(st["time_limit_s"]), MAX_TIME_LIMIT_S),
                                   float(st["mip_rel_gap"]))
    info["solve_seconds"] = round(time.time() - t0, 2)
    info["solver"] = "HiGHS via scipy.optimize.milp"
    info["solver_status"] = U.status_label(info)
    info["reported_mip_gap"] = U.reported_gap(info)
    info["options"] = opts
    if sched is None:
        val = {"ok": False, "checks": {}, "failures": {"no_incumbent": [info["milp_message"]]}}
        path = ""
    else:
        val = U.validate(case, sched, opts, info.get("model_objective"))
        fd, path = tempfile.mkstemp(prefix="uc_schedule_", suffix=".json")
        with os.fdopen(fd, "w") as f:
            json.dump({"schedule": sched, "solve_info": info}, f)
    U.emit({
        "schedule_path": path,
        "solve_summary": info,
        "validation": {k: val[k] for k in val if k != "hourly"},
        "schedule_valid": bool(val["ok"]),
    })


if __name__ == "__main__":
    main()

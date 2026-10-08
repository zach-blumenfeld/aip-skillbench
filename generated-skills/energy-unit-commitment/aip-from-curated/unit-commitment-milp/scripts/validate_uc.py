"""Independently validate a UC solution file against the case data; recompute cost from the arrays.

Reads only the case file and the extracted solution arrays (never the model). Writes the result into
the solution file under "validation" and "recomputed_cost" so the report is built from checked values.
"""
import json
import sys

from uc_common import curve_cost, load_case, offline_durations_at_starts, read_stdin, startup_tier_index

TOL = 1e-4


def main():
    state = read_stdin(sys.stdin)
    with open(state["solution_path"], "r", encoding="utf-8") as f:
        sol = json.load(f)
    case, errors, _ = load_case(state["data_path"])
    opts = sol.get("conventions", {}).get("options", {})
    shutdown_rule = bool(state.get("enforce_shutdown_capability", opts.get("enforce_shutdown_capability", True)))
    post_horizon = bool(state.get("post_horizon_min_updown", opts.get("post_horizon_min_updown", False)))
    ren_reserve = bool(state.get("renewable_reserve_allowed", opts.get("renewable_reserve_allowed", False)))
    T = case["T"]
    fams = ["coverage", "binary", "transition_linking", "offline_zero", "online_limits", "must_run",
            "min_up_down", "initial_conditions", "demand_balance", "renewable_bounds", "system_reserve",
            "reserve_deliverability", "startup_capability", "shutdown_capability", "ramping", "cost_recomputed"]
    viol = {k: [] for k in fams}

    def bad(fam, msg):
        if len(viol[fam]) < 5:
            viol[fam].append(msg)
        else:
            viol[fam].append(None)

    th, rn = case["thermal"], case["renewable"]
    names = [g["name"] for g in th]
    rnames = [r["name"] for r in rn]
    for key, ids in (("commitment", names), ("startup", names), ("shutdown", names), ("thermal_dispatch_mw", names),
                     ("thermal_reserve_mw", names), ("renewable_dispatch_mw", rnames)):
        got = sol.get(key, {})
        if list(got.keys()) != ids:
            bad("coverage", f"{key}: resource IDs/order differ from data ({len(got)} vs {len(ids)})")
        for n in ids:
            if len(got.get(n, [])) != T:
                bad("coverage", f"{key}[{n}] length != {T}")
    if viol["coverage"]:
        out = {"validation_passed": False, "violations": [m for m in viol["coverage"] if m], "checks": {"coverage": "fail"}}
        print(json.dumps(out))
        return

    prod_cost = start_cost = 0.0
    tot_res = [0.0] * T
    tot_gen = [0.0] * T
    for g in th:
        n = g["name"]
        u = sol["commitment"][n]
        su, sd = sol["startup"][n], sol["shutdown"][n]
        q, r = sol["thermal_dispatch_mw"][n], sol["thermal_reserve_mw"][n]
        pmin, pmax = g["power_output_minimum"], g["power_output_maximum"]
        on0, p0 = g["unit_on_t0"], g["power_output_t0"]
        for arr, lab in ((u, "u"), (su, "startup"), (sd, "shutdown")):
            if any(x not in (0, 1) for x in arr):
                bad("binary", f"{n}: {lab} not binary")
        prev = on0
        for t in range(T):
            if su[t] != int(u[t] == 1 and prev == 0) or sd[t] != int(u[t] == 0 and prev == 1):
                bad("transition_linking", f"{n} t={t}: startup/shutdown do not match status change")
            prev = u[t]
        for t in range(T):
            tot_gen[t] += q[t]
            tot_res[t] += r[t]
            if r[t] < -TOL:
                bad("system_reserve", f"{n} t={t}: negative reserve")
            if u[t] == 0:
                if abs(q[t]) > TOL or abs(r[t]) > TOL:
                    bad("offline_zero", f"{n} t={t}: offline but output {q[t]:.4f} / reserve {r[t]:.4f}")
                continue
            if q[t] < pmin - TOL or q[t] > pmax + TOL:
                bad("online_limits", f"{n} t={t}: output {q[t]:.4f} outside [{pmin},{pmax}]")
            if q[t] + r[t] > pmax + TOL:
                bad("reserve_deliverability", f"{n} t={t}: output+reserve {q[t] + r[t]:.4f} > pmax {pmax}")
            if su[t] == 1 and q[t] + r[t] > g["ramp_startup_limit"] + TOL and g["ramp_startup_limit"] < pmax:
                bad("startup_capability", f"{n} t={t}: startup output+reserve {q[t] + r[t]:.4f} > {g['ramp_startup_limit']}")
            if shutdown_rule and t + 1 < T and sd[t + 1] == 1 and q[t] + r[t] > g["ramp_shutdown_limit"] + TOL \
                    and g["ramp_shutdown_limit"] < pmax:
                bad("shutdown_capability", f"{n} t={t}: output+reserve {q[t] + r[t]:.4f} before shutdown > {g['ramp_shutdown_limit']}")
        if shutdown_rule and on0 == 1 and sd[0] == 1 and p0 > g["ramp_shutdown_limit"] + TOL:
            bad("shutdown_capability", f"{n}: shuts down at t=0 from power_output_t0 {p0} > ramp_shutdown_limit")
        if g["must_run"] and any(x == 0 for x in u):
            bad("must_run", f"{n}: must-run unit offline")
        # ramping on above-minimum output, reserve included in ramp-up
        prev_above = on0 * (p0 - pmin)
        for t in range(T):
            above = q[t] - pmin * u[t]
            if above + r[t] - prev_above > g["ramp_up_limit"] + TOL:
                bad("ramping", f"{n} t={t}: ramp-up {above + r[t] - prev_above:.4f} > {g['ramp_up_limit']}")
            if prev_above - above > g["ramp_down_limit"] + TOL:
                bad("ramping", f"{n} t={t}: ramp-down {prev_above - above:.4f} > {g['ramp_down_limit']}")
            prev_above = above
        # initial obligations
        if on0 == 1:
            for t in range(min(T, max(0, g["time_up_minimum"] - g["time_up_t0"]))):
                if u[t] != 1:
                    bad("initial_conditions", f"{n} t={t}: must stay on (time_up_t0={g['time_up_t0']})")
        else:
            for t in range(min(T, max(0, g["time_down_minimum"] - g["time_down_t0"]))):
                if u[t] != 0:
                    bad("initial_conditions", f"{n} t={t}: must stay off (time_down_t0={g['time_down_t0']})")
        for t in range(T):
            if su[t] == 1:
                if post_horizon and t + g["time_up_minimum"] > T:
                    bad("min_up_down", f"{n} t={t}: start cannot complete min up within horizon")
                for k in range(t, min(T, t + g["time_up_minimum"])):
                    if u[k] != 1:
                        bad("min_up_down", f"{n}: started t={t} but off at t={k} (min up {g['time_up_minimum']})")
                        break
            if sd[t] == 1:
                if post_horizon and t + g["time_down_minimum"] > T:
                    bad("min_up_down", f"{n} t={t}: stop cannot complete min down within horizon")
                for k in range(t, min(T, t + g["time_down_minimum"])):
                    if u[k] != 0:
                        bad("min_up_down", f"{n}: stopped t={t} but on at t={k} (min down {g['time_down_minimum']})")
                        break
        # cost from arrays: total-cost curve at actual output + startup tier by prior offline duration
        offd = offline_durations_at_starts(g, u)
        for t in range(T):
            if u[t] == 1:
                prod_cost += curve_cost(g["curve"], q[t])
            if su[t] == 1:
                start_cost += g["startup"][startup_tier_index(g["startup"], offd[t])][1]

    ren = sol["renewable_dispatch_mw"]
    rres = sol.get("renewable_reserve_mw", {})
    for rec in rn:
        x = ren[rec["name"]]
        for t in range(T):
            tot_gen[t] += x[t]
            if x[t] < rec["min"][t] - TOL or x[t] > rec["max"][t] + TOL:
                bad("renewable_bounds", f"{rec['name']} t={t}: {x[t]:.4f} outside [{rec['min'][t]},{rec['max'][t]}]")
            if ren_reserve and rec["name"] in rres:
                rv = rres[rec["name"]][t]
                tot_res[t] += rv
                if x[t] + rv > rec["max"][t] + TOL:
                    bad("renewable_bounds", f"{rec['name']} t={t}: output+reserve > max")
    for t in range(T):
        if abs(tot_gen[t] - case["demand"][t]) > max(TOL, 1e-7 * case["demand"][t]):
            bad("demand_balance", f"t={t}: generation {tot_gen[t]:.5f} != demand {case['demand'][t]}")
        if tot_res[t] < case["reserves"][t] - TOL:
            bad("system_reserve", f"t={t}: reserve {tot_res[t]:.5f} < requirement {case['reserves'][t]}")

    total = prod_cost + start_cost
    obj = sol.get("solver", {}).get("objective")
    if obj is not None and abs(total - obj) > max(1e-3, 1e-6 * abs(total)):
        bad("cost_recomputed", f"recomputed {total:.4f} != solver objective {obj:.4f} (check tiers/curve convention)")
    checks = {k: ("pass" if not viol[k] else "fail") for k in fams}
    passed = all(v == "pass" for v in checks.values())
    flat = []
    for k in fams:
        msgs = [x for x in viol[k] if x]
        extra = len(viol[k]) - len(msgs)
        flat += [f"[{k}] {x}" for x in msgs] + ([f"[{k}] ... {extra} more"] if extra else [])
    recomputed = {"total_cost": total, "production_cost": prod_cost, "startup_cost": start_cost}
    sol["validation"] = {"passed": passed, "checks": checks, "violations": flat}
    sol["recomputed_cost"] = recomputed
    sol["system_totals"] = {"generation_mw": tot_gen, "reserve_mw": tot_res,
                            "demand_mw": case["demand"], "reserve_requirement_mw": case["reserves"]}
    with open(state["solution_path"], "w", encoding="utf-8") as f:
        json.dump(sol, f)
    print(json.dumps({"validation_passed": passed, "violations": flat[:40], "checks": checks,
                      "recomputed_cost": recomputed}))


if __name__ == "__main__":
    main()

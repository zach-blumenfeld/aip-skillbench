"""Load the case file, summarize its schema, and run parser-level checks before modeling."""
import json
import os
import sys

from uc_common import load_case, read_stdin


def main():
    state = read_stdin(sys.stdin)
    path = state.get("data_path", "")
    out = {"data_ready": False, "data_errors": [], "data_warnings": [], "schema_summary": {}}
    if not path or not os.path.isfile(path):
        out["data_errors"] = [f"data_path not found: {path!r}"]
        print(json.dumps(out))
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception as e:  # not JSON: needs normalization
        out["data_errors"] = [f"not parseable as JSON: {e}"]
        print(json.dumps(out))
        return
    summary = {"top_level_keys": sorted(raw.keys()) if isinstance(raw, dict) else type(raw).__name__}
    case, errors, warnings = load_case(path)
    if case is not None:
        th = case["thermal"]
        summary.update({
            "time_periods": case["T"],
            "n_thermal": len(th),
            "n_renewable": len(case["renewable"]),
            "demand_range_mw": [min(case["demand"]), max(case["demand"])],
            "reserve_range_mw": [min(case["reserves"]), max(case["reserves"])],
            "thermal_pmax_total_mw": sum(g["power_output_maximum"] for g in th),
            "renewable_max_peak_mw": max(sum(r["max"][t] for r in case["renewable"]) for t in range(case["T"])) if case["renewable"] else 0.0,
            "must_run_units": [g["name"] for g in th if g["must_run"]],
            "units_on_at_t0": sum(g["unit_on_t0"] for g in th),
            "startup_tier_counts": sorted({len(g["startup"]) for g in th}),
            "all_cost_curves_convex": all(g["convex"] for g in th),
            "renewables_fixed_periods": sum(1 for r in case["renewable"] for a, b in zip(r["min"], r["max"]) if a == b),
        })
        # minimum generation that cannot be avoided: renewable minimums + pmin of units forced online
        nocurt = []
        for t in range(case["T"]):
            forced = 0.0
            for g in th:
                init_up = g["unit_on_t0"] == 1 and t < g["time_up_minimum"] - g["time_up_t0"]
                if g["must_run"] or init_up:
                    forced += g["power_output_minimum"]
            rmin = sum(r["min"][t] for r in case["renewable"])
            rmax = sum(r["max"][t] for r in case["renewable"])
            if forced + rmin > case["demand"][t] + 1e-6:
                errors.append(f"period {t}: forced minimum generation {forced + rmin:.1f} > demand {case['demand'][t]}")
            if forced + rmax > case["demand"][t] + 1e-6:
                nocurt.append(t)
        if nocurt:
            warnings.append(f"renewable max + forced thermal minimum exceeds demand in periods {nocurt}: "
                            "curtailment is required there; a no-curtailment rule would be infeasible")
        summary["periods_requiring_curtailment"] = nocurt
        cap = summary["thermal_pmax_total_mw"]
        for t in range(case["T"]):
            rmax = sum(r["max"][t] for r in case["renewable"])
            if cap + rmax < case["demand"][t] + case["reserves"][t] - 1e-6:
                errors.append(f"period {t}: total capacity {cap + rmax:.1f} < demand+reserve")
                break
    out.update({
        "data_ready": case is not None and not errors,
        "data_errors": errors,
        "data_warnings": warnings[:50],
        "schema_summary": summary,
    })
    print(json.dumps(out))


if __name__ == "__main__":
    main()

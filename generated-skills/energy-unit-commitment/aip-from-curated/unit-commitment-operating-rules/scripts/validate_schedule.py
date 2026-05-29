#!/usr/bin/env python3
"""Independently validate a unit-commitment schedule against the operating rules.

Usage:
    python validate_schedule.py <network.json> <report.json> [--out <verdict.json>]

Mirrors the feasibility, transition, and cost checks the task grader runs.
Tolerances match the grader (TOL_* constants below). Outputs a JSON verdict to
stdout with per-check pass/fail, top diagnostics, and recomputed summary
fields the agent should copy into the final report.

Exit codes:
    0 if every check passes
    1 if any check fails or inputs are unparseable
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

import numpy as np

TOL_POWER_BALANCE_MW = 1e-2
TOL_RESERVE_MW = 1e-2
TOL_GENERATOR_MW = 1e-3
TOL_RAMP_MW = 1e-3
TOL_BINARY = 1e-5
TOL_COST_REL = 1e-4
TOL_COST_ABS = 1e-2

ACCEPTED_STATUSES = {
    "optimal",
    "feasible",
    "time_limit_feasible",
    "suboptimal_feasible",
    "heuristic_feasible",
}

REQUIRED_CONSTRAINT_CHECKS = [
    "demand_balance",
    "spinning_reserve",
    "reserve_deliverability",
    "generator_limits",
    "must_run",
    "ramping",
    "minimum_up_down",
    "startup_shutdown_logic",
    "initial_conditions",
    "renewable_limits",
    "cost_consistency",
]

MAX_DIAGNOSTICS_PER_CHECK = 10


class Verdict:
    """Accumulates per-check violations without short-circuiting."""

    def __init__(self) -> None:
        self.checks: dict[str, list[str]] = {k: [] for k in REQUIRED_CONSTRAINT_CHECKS}
        self.schema_errors: list[str] = []
        self.parse_errors: list[str] = []

    def fail(self, check: str, msg: str) -> None:
        bucket = self.checks.setdefault(check, [])
        if len(bucket) < MAX_DIAGNOSTICS_PER_CHECK:
            bucket.append(msg)

    def schema(self, msg: str) -> None:
        self.schema_errors.append(msg)

    def parse(self, msg: str) -> None:
        self.parse_errors.append(msg)

    def overall_pass(self) -> bool:
        if self.parse_errors or self.schema_errors:
            return False
        return all(len(v) == 0 for v in self.checks.values())


def _load_json(path: Path, verdict: Verdict, label: str) -> dict | None:
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        verdict.parse(f"{label} could not be loaded from {path}: {exc}")
        return None
    if not isinstance(data, dict):
        verdict.parse(f"{label} at {path} must be a JSON object")
        return None
    return data


def _as_float_array(values: Any, length: int, label: str, verdict: Verdict) -> np.ndarray | None:
    try:
        arr = np.asarray(values, dtype=float)
    except (TypeError, ValueError) as exc:
        verdict.schema(f"{label} not numeric: {exc}")
        return None
    if arr.shape != (length,):
        verdict.schema(f"{label} must have length {length}, got shape {arr.shape}")
        return None
    if not np.all(np.isfinite(arr)):
        verdict.schema(f"{label} contains non-finite values")
        return None
    return arr


def _as_binary_array(values: Any, length: int, label: str, verdict: Verdict) -> np.ndarray | None:
    arr = _as_float_array(values, length, label, verdict)
    if arr is None:
        return None
    rounded = np.rint(arr).astype(int)
    if not np.all(np.abs(arr - rounded) <= TOL_BINARY):
        verdict.schema(f"{label} not binary within tolerance {TOL_BINARY}")
    bad = (rounded != 0) & (rounded != 1)
    if np.any(bad):
        verdict.schema(f"{label} contains values other than 0/1")
    return rounded


def parse_case(case: dict, verdict: Verdict) -> dict | None:
    required = {"time_periods", "demand", "reserves", "thermal_generators", "renewable_generators"}
    missing = required - set(case)
    if missing:
        verdict.parse(f"network.json missing keys: {sorted(missing)}")
        return None

    try:
        T = int(case["time_periods"])
    except (TypeError, ValueError):
        verdict.parse("time_periods is not an integer")
        return None
    if T <= 0:
        verdict.parse("time_periods must be positive")
        return None

    demand = _as_float_array(case["demand"], T, "demand", verdict)
    reserves = _as_float_array(case["reserves"], T, "reserves", verdict)
    if demand is None or reserves is None:
        return None

    thermal: list[dict] = []
    thermal_names: list[str] = []
    thermal_items = case["thermal_generators"]
    if not isinstance(thermal_items, dict) or not thermal_items:
        verdict.parse("thermal_generators must be a non-empty object")
        return None

    thermal_required = {
        "power_output_minimum",
        "power_output_maximum",
        "ramp_up_limit",
        "ramp_down_limit",
        "ramp_startup_limit",
        "ramp_shutdown_limit",
        "time_up_minimum",
        "time_down_minimum",
        "power_output_t0",
        "unit_on_t0",
        "time_down_t0",
        "time_up_t0",
        "startup",
        "piecewise_production",
    }

    for key, gen in thermal_items.items():
        if not isinstance(gen, dict):
            verdict.parse(f"thermal generator {key} not an object")
            continue
        miss = thermal_required - set(gen)
        if miss:
            verdict.parse(f"thermal generator {key} missing keys: {sorted(miss)}")
            continue
        name = str(gen.get("name", key))
        thermal_names.append(name)
        try:
            pmin = float(gen["power_output_minimum"])
            pmax = float(gen["power_output_maximum"])
            curve = sorted(
                ((float(p["mw"]), float(p["cost"])) for p in gen["piecewise_production"]),
                key=lambda x: x[0],
            )
            startups = sorted(
                ((int(item["lag"]), float(item["cost"])) for item in gen["startup"]),
                key=lambda x: x[0],
            )
        except (KeyError, TypeError, ValueError) as exc:
            verdict.parse(f"thermal generator {name} malformed: {exc}")
            continue
        if not (pmax >= pmin >= 0):
            verdict.parse(f"{name} has invalid output range [{pmin},{pmax}]")
            continue
        if len(curve) < 2:
            verdict.parse(f"{name} must have >=2 piecewise cost points")
            continue
        if abs(curve[0][0] - pmin) > TOL_GENERATOR_MW:
            verdict.parse(f"{name} first piecewise MW {curve[0][0]} != pmin {pmin}")
        if abs(curve[-1][0] - pmax) > TOL_GENERATOR_MW:
            verdict.parse(f"{name} last piecewise MW {curve[-1][0]} != pmax {pmax}")
        if not all(curve[i + 1][0] > curve[i][0] for i in range(len(curve) - 1)):
            verdict.parse(f"{name} piecewise MW points not strictly increasing")
        if not startups or not all(lag > 0 for lag, _ in startups):
            verdict.parse(f"{name} startup tiers invalid")
            continue
        thermal.append(
            {
                "name": name,
                "pmin": pmin,
                "pmax": pmax,
                "cap": pmax - pmin,
                "ru": float(gen["ramp_up_limit"]),
                "rd": float(gen["ramp_down_limit"]),
                "su": float(gen["ramp_startup_limit"]),
                "sd": float(gen["ramp_shutdown_limit"]),
                "min_up": int(gen["time_up_minimum"]),
                "min_down": int(gen["time_down_minimum"]),
                "p0": float(gen["power_output_t0"]),
                "u0": int(round(float(gen["unit_on_t0"]))),
                "time_down_t0": int(gen["time_down_t0"]),
                "time_up_t0": int(gen["time_up_t0"]),
                "must_run": int(gen.get("must_run", 0)),
                "startup": startups,
                "piecewise": curve,
            }
        )

    if len(set(thermal_names)) != len(thermal_names):
        verdict.parse("thermal generator names are not unique")

    renewable: list[dict] = []
    renewable_names: list[str] = []
    ren_items = case["renewable_generators"]
    if not isinstance(ren_items, dict):
        verdict.parse("renewable_generators must be an object")
        return None

    for key, gen in ren_items.items():
        if not isinstance(gen, dict):
            verdict.parse(f"renewable generator {key} not an object")
            continue
        if "power_output_minimum" not in gen or "power_output_maximum" not in gen:
            verdict.parse(f"renewable generator {key} missing min/max")
            continue
        name = str(gen.get("name", key))
        renewable_names.append(name)
        pmin = _as_float_array(gen["power_output_minimum"], T, f"{name} renewable minimum", verdict)
        pmax = _as_float_array(gen["power_output_maximum"], T, f"{name} renewable maximum", verdict)
        if pmin is None or pmax is None:
            continue
        if not np.all(pmax + TOL_GENERATOR_MW >= pmin):
            verdict.parse(f"{name} renewable max below min in some period")
        renewable.append({"name": name, "pmin": pmin, "pmax": pmax})

    if len(set(renewable_names)) != len(renewable_names):
        verdict.parse("renewable generator names are not unique")

    return {
        "T": T,
        "demand": demand,
        "reserves": reserves,
        "thermal": thermal,
        "renewable": renewable,
        "thermal_names": thermal_names,
        "renewable_names": renewable_names,
    }


def extract_arrays(report: dict, case: dict, verdict: Verdict) -> dict | None:
    required = {"case_name", "summary", "thermal_generators", "renewable_generators", "hourly_summary", "constraint_check"}
    miss = required - set(report)
    if miss:
        verdict.schema(f"report missing keys: {sorted(miss)}")
        return None
    if not isinstance(report["summary"], dict):
        verdict.schema("summary must be an object")
        return None
    if not isinstance(report["thermal_generators"], list):
        verdict.schema("thermal_generators must be a list")
        return None
    if not isinstance(report["renewable_generators"], list):
        verdict.schema("renewable_generators must be a list")
        return None
    if not isinstance(report["hourly_summary"], list):
        verdict.schema("hourly_summary must be a list")
        return None
    if not isinstance(report["constraint_check"], dict):
        verdict.schema("constraint_check must be an object")
        return None

    T = case["T"]

    thermal_entries: dict[str, dict] = {}
    for entry in report["thermal_generators"]:
        if not isinstance(entry, dict):
            verdict.schema("each thermal_generators entry must be an object")
            continue
        name = entry.get("name")
        if not isinstance(name, str):
            verdict.schema("thermal generator entry missing string name")
            continue
        if name in thermal_entries:
            verdict.schema(f"duplicate thermal generator {name}")
            continue
        thermal_entries[name] = entry

    expected_thermal = set(case["thermal_names"])
    if set(thermal_entries) != expected_thermal:
        extra = set(thermal_entries) - expected_thermal
        missing = expected_thermal - set(thermal_entries)
        if extra:
            verdict.schema(f"thermal_generators contains unknown names: {sorted(extra)}")
        if missing:
            verdict.schema(f"thermal_generators missing names: {sorted(missing)}")

    renewable_entries: dict[str, dict] = {}
    for entry in report["renewable_generators"]:
        if not isinstance(entry, dict):
            verdict.schema("each renewable_generators entry must be an object")
            continue
        name = entry.get("name")
        if not isinstance(name, str):
            verdict.schema("renewable generator entry missing string name")
            continue
        if name in renewable_entries:
            verdict.schema(f"duplicate renewable generator {name}")
            continue
        renewable_entries[name] = entry

    expected_ren = set(case["renewable_names"])
    if set(renewable_entries) != expected_ren:
        extra = set(renewable_entries) - expected_ren
        missing = expected_ren - set(renewable_entries)
        if extra:
            verdict.schema(f"renewable_generators contains unknown names: {sorted(extra)}")
        if missing:
            verdict.schema(f"renewable_generators missing names: {sorted(missing)}")

    G = len(case["thermal"])
    R = len(case["renewable"])
    commitment = np.zeros((G, T), dtype=int)
    startup = np.zeros((G, T), dtype=int)
    shutdown = np.zeros((G, T), dtype=int)
    production = np.zeros((G, T), dtype=float)
    reserve = np.zeros((G, T), dtype=float)

    for g, gen in enumerate(case["thermal"]):
        entry = thermal_entries.get(gen["name"])
        if entry is None:
            continue
        missing_fields = {"commitment", "production_MW", "reserve_MW", "startup", "shutdown"} - set(entry)
        if missing_fields:
            verdict.schema(f"{gen['name']} missing fields: {sorted(missing_fields)}")
            continue
        u = _as_binary_array(entry["commitment"], T, f"{gen['name']} commitment", verdict)
        v = _as_binary_array(entry["startup"], T, f"{gen['name']} startup", verdict)
        w = _as_binary_array(entry["shutdown"], T, f"{gen['name']} shutdown", verdict)
        p = _as_float_array(entry["production_MW"], T, f"{gen['name']} production_MW", verdict)
        r = _as_float_array(entry["reserve_MW"], T, f"{gen['name']} reserve_MW", verdict)
        if any(x is None for x in (u, v, w, p, r)):
            continue
        commitment[g] = u
        startup[g] = v
        shutdown[g] = w
        production[g] = p
        reserve[g] = r

    renewable_production = np.zeros((R, T), dtype=float)
    for i, gen in enumerate(case["renewable"]):
        entry = renewable_entries.get(gen["name"])
        if entry is None:
            continue
        if "production_MW" not in entry:
            verdict.schema(f"{gen['name']} missing production_MW")
            continue
        p = _as_float_array(entry["production_MW"], T, f"{gen['name']} production_MW", verdict)
        if p is None:
            continue
        renewable_production[i] = p

    if len(report["hourly_summary"]) != T:
        verdict.schema(f"hourly_summary must have {T} entries, got {len(report['hourly_summary'])}")
    for t, row in enumerate(report["hourly_summary"]):
        if not isinstance(row, dict):
            verdict.schema(f"hourly_summary[{t}] must be an object")
            continue
        miss = {"hour", "demand_MW", "thermal_generation_MW", "renewable_generation_MW",
                "reserve_requirement_MW", "scheduled_spinning_reserve_MW"} - set(row)
        if miss:
            verdict.schema(f"hourly_summary[{t}] missing: {sorted(miss)}")
            continue
        try:
            if int(row["hour"]) != t + 1:
                verdict.schema(f"hourly_summary[{t}].hour must be {t + 1}")
        except (TypeError, ValueError):
            verdict.schema(f"hourly_summary[{t}].hour not an integer")

    return {
        "commitment": commitment,
        "startup": startup,
        "shutdown": shutdown,
        "thermal_production": production,
        "thermal_reserve": reserve,
        "renewable_production": renewable_production,
    }


def check_summary_schema(report: dict, case: dict, verdict: Verdict) -> None:
    summary = report["summary"]
    required = {
        "solver_status", "objective_cost", "reported_mip_gap", "time_periods",
        "num_thermal_generators", "num_renewable_generators", "total_startups",
        "total_shutdowns", "max_demand_balance_violation_MW", "max_reserve_shortfall_MW",
    }
    miss = required - set(summary)
    if miss:
        verdict.schema(f"summary missing keys: {sorted(miss)}")
    status = summary.get("solver_status")
    if status not in ACCEPTED_STATUSES:
        verdict.schema(f"solver_status {status!r} not in {sorted(ACCEPTED_STATUSES)}")
    gap = summary.get("reported_mip_gap")
    if gap is not None:
        try:
            gap_f = float(gap)
            if not math.isfinite(gap_f) or gap_f < 0:
                verdict.schema("reported_mip_gap must be null or finite nonnegative")
        except (TypeError, ValueError):
            verdict.schema("reported_mip_gap not numeric or null")
    try:
        if int(summary["time_periods"]) != case["T"]:
            verdict.schema("summary.time_periods does not match case")
    except (KeyError, TypeError, ValueError):
        pass
    try:
        if int(summary["num_thermal_generators"]) != len(case["thermal"]):
            verdict.schema("summary.num_thermal_generators does not match case")
    except (KeyError, TypeError, ValueError):
        pass
    try:
        if int(summary["num_renewable_generators"]) != len(case["renewable"]):
            verdict.schema("summary.num_renewable_generators does not match case")
    except (KeyError, TypeError, ValueError):
        pass
    cc = report["constraint_check"]
    miss_cc = set(REQUIRED_CONSTRAINT_CHECKS) - set(cc)
    if miss_cc:
        verdict.schema(f"constraint_check missing keys: {sorted(miss_cc)}")
    for k in REQUIRED_CONSTRAINT_CHECKS:
        if k in cc and cc[k] != "pass":
            verdict.schema(f"constraint_check.{k} is {cc[k]!r}, must be 'pass'")


def check_transitions(arrays: dict, case: dict, verdict: Verdict) -> tuple[np.ndarray, np.ndarray]:
    u = arrays["commitment"]
    G, T = u.shape
    exp_v = np.zeros_like(u)
    exp_w = np.zeros_like(u)
    for g, gen in enumerate(case["thermal"]):
        prev = gen["u0"]
        for t in range(T):
            exp_v[g, t] = max(u[g, t] - prev, 0)
            exp_w[g, t] = max(prev - u[g, t], 0)
            prev = u[g, t]
    bad_v = arrays["startup"] != exp_v
    bad_w = arrays["shutdown"] != exp_w
    for g, gen in enumerate(case["thermal"]):
        for t in range(T):
            if bad_v[g, t]:
                verdict.fail(
                    "startup_shutdown_logic",
                    f"{gen['name']} startup[t={t + 1}] reported={arrays['startup'][g, t]} expected={exp_v[g, t]}",
                )
            if bad_w[g, t]:
                verdict.fail(
                    "startup_shutdown_logic",
                    f"{gen['name']} shutdown[t={t + 1}] reported={arrays['shutdown'][g, t]} expected={exp_w[g, t]}",
                )
    simultaneous = arrays["startup"] + arrays["shutdown"] > 1
    if np.any(simultaneous):
        gs, ts = np.where(simultaneous)
        for g, t in zip(gs.tolist(), ts.tolist()):
            verdict.fail(
                "startup_shutdown_logic",
                f"{case['thermal'][g]['name']} starts and shuts down in same hour t={t + 1}",
            )
    return exp_v, exp_w


def check_summary_counts(report: dict, arrays: dict, verdict: Verdict) -> None:
    summary = report["summary"]
    try:
        reported_su = int(summary["total_startups"])
    except (KeyError, TypeError, ValueError):
        reported_su = None
    try:
        reported_sd = int(summary["total_shutdowns"])
    except (KeyError, TypeError, ValueError):
        reported_sd = None
    actual_su = int(arrays["startup"].sum())
    actual_sd = int(arrays["shutdown"].sum())
    if reported_su is not None and reported_su != actual_su:
        verdict.fail("startup_shutdown_logic", f"summary.total_startups={reported_su} != {actual_su}")
    if reported_sd is not None and reported_sd != actual_sd:
        verdict.fail("startup_shutdown_logic", f"summary.total_shutdowns={reported_sd} != {actual_sd}")


def check_must_run(arrays: dict, case: dict, verdict: Verdict) -> None:
    for g, gen in enumerate(case["thermal"]):
        if gen["must_run"] == 1 and not np.all(arrays["commitment"][g] == 1):
            offs = np.where(arrays["commitment"][g] == 0)[0]
            verdict.fail("must_run", f"{gen['name']} must-run but offline at hours {(offs + 1).tolist()[:10]}")


def check_generator_limits(arrays: dict, case: dict, verdict: Verdict) -> None:
    u = arrays["commitment"]
    p = arrays["thermal_production"]
    r = arrays["thermal_reserve"]
    for g, gen in enumerate(case["thermal"]):
        neg = r[g] < -TOL_GENERATOR_MW
        if np.any(neg):
            ts = (np.where(neg)[0] + 1).tolist()[:10]
            verdict.fail("generator_limits", f"{gen['name']} negative reserve at hours {ts}")
        offline = u[g] == 0
        bad_p = offline & (np.abs(p[g]) > TOL_GENERATOR_MW)
        bad_r = offline & (np.abs(r[g]) > TOL_GENERATOR_MW)
        if np.any(bad_p):
            ts = (np.where(bad_p)[0] + 1).tolist()[:10]
            verdict.fail("generator_limits", f"{gen['name']} production while offline at hours {ts}")
        if np.any(bad_r):
            ts = (np.where(bad_r)[0] + 1).tolist()[:10]
            verdict.fail("generator_limits", f"{gen['name']} reserve while offline at hours {ts}")
        below_min = p[g] + TOL_GENERATOR_MW < gen["pmin"] * u[g]
        above_max = p[g] > gen["pmax"] * u[g] + TOL_GENERATOR_MW
        if np.any(below_min):
            ts = (np.where(below_min)[0] + 1).tolist()[:10]
            verdict.fail("generator_limits", f"{gen['name']} below minimum at hours {ts}")
        if np.any(above_max):
            ts = (np.where(above_max)[0] + 1).tolist()[:10]
            verdict.fail("generator_limits", f"{gen['name']} above maximum at hours {ts}")


def check_reserve_deliverability_and_ramping(arrays: dict, case: dict, verdict: Verdict) -> None:
    u = arrays["commitment"]
    v = arrays["startup"]
    w = arrays["shutdown"]
    p = arrays["thermal_production"]
    r = arrays["thermal_reserve"]
    T = case["T"]
    for g, gen in enumerate(case["thermal"]):
        p_above = p[g] - gen["pmin"] * u[g]
        p0_above = gen["u0"] * (gen["p0"] - gen["pmin"])
        cap = gen["cap"]
        startup_reduction = max(gen["pmax"] - gen["su"], 0.0)
        shutdown_reduction = max(gen["pmax"] - gen["sd"], 0.0)
        neg_above = p_above < -TOL_GENERATOR_MW
        if np.any(neg_above):
            ts = (np.where(neg_above)[0] + 1).tolist()[:10]
            verdict.fail("generator_limits", f"{gen['name']} negative above-min production at hours {ts}")
        for t in range(T):
            lhs = p_above[t] + r[g, t]
            cap_rhs = cap * u[g, t] - startup_reduction * v[g, t]
            if lhs > cap_rhs + TOL_GENERATOR_MW:
                verdict.fail(
                    "reserve_deliverability",
                    f"{gen['name']} t={t + 1}: p_above+reserve={lhs:.4f} > cap*u - startup_reduction*v = {cap_rhs:.4f}",
                )
            if t < T - 1:
                shut_rhs = cap * u[g, t] - shutdown_reduction * w[g, t + 1]
                if lhs > shut_rhs + TOL_GENERATOR_MW:
                    verdict.fail(
                        "reserve_deliverability",
                        f"{gen['name']} t={t + 1}: p_above+reserve={lhs:.4f} > cap*u - shutdown_reduction*w[t+1] = {shut_rhs:.4f}",
                    )
            previous = p0_above if t == 0 else p_above[t - 1]
            if lhs - previous > gen["ru"] + TOL_RAMP_MW:
                verdict.fail(
                    "ramping",
                    f"{gen['name']} t={t + 1}: ramp-up with reserve = {lhs - previous:.4f} > ru={gen['ru']:.4f}",
                )
            if previous - p_above[t] > gen["rd"] + TOL_RAMP_MW:
                verdict.fail(
                    "ramping",
                    f"{gen['name']} t={t + 1}: ramp-down = {previous - p_above[t]:.4f} > rd={gen['rd']:.4f}",
                )


def check_system_balance(arrays: dict, case: dict, verdict: Verdict) -> dict:
    thermal_gen = arrays["thermal_production"].sum(axis=0)
    renew_gen = arrays["renewable_production"].sum(axis=0)
    reserve_total = arrays["thermal_reserve"].sum(axis=0)
    balance_err = thermal_gen + renew_gen - case["demand"]
    abs_balance = np.abs(balance_err)
    max_balance = float(np.max(abs_balance)) if abs_balance.size else 0.0
    reserve_short = np.maximum(case["reserves"] - reserve_total, 0.0)
    max_short = float(np.max(reserve_short)) if reserve_short.size else 0.0
    bad_b = abs_balance > TOL_POWER_BALANCE_MW
    if np.any(bad_b):
        ts = np.where(bad_b)[0]
        for t in ts[:MAX_DIAGNOSTICS_PER_CHECK]:
            verdict.fail(
                "demand_balance",
                f"t={int(t) + 1}: thermal+renewable - demand = {balance_err[t]:.4f} (|err| > {TOL_POWER_BALANCE_MW})",
            )
    bad_r = reserve_total < case["reserves"] - TOL_RESERVE_MW
    if np.any(bad_r):
        ts = np.where(bad_r)[0]
        for t in ts[:MAX_DIAGNOSTICS_PER_CHECK]:
            verdict.fail(
                "spinning_reserve",
                f"t={int(t) + 1}: sum(reserve)={reserve_total[t]:.4f} < requirement={case['reserves'][t]:.4f}",
            )
    return {
        "thermal_generation_MW": thermal_gen,
        "renewable_generation_MW": renew_gen,
        "scheduled_spinning_reserve_MW": reserve_total,
        "max_demand_balance_violation_MW": max_balance,
        "max_reserve_shortfall_MW": max_short,
    }


def check_renewable_limits(arrays: dict, case: dict, verdict: Verdict) -> None:
    production = arrays["renewable_production"]
    for i, gen in enumerate(case["renewable"]):
        below = production[i] + TOL_GENERATOR_MW < gen["pmin"]
        above = production[i] > gen["pmax"] + TOL_GENERATOR_MW
        if np.any(below):
            ts = (np.where(below)[0] + 1).tolist()[:10]
            verdict.fail("renewable_limits", f"{gen['name']} below minimum at hours {ts}")
        if np.any(above):
            ts = (np.where(above)[0] + 1).tolist()[:10]
            verdict.fail("renewable_limits", f"{gen['name']} above maximum at hours {ts}")
        fixed = np.abs(gen["pmax"] - gen["pmin"]) <= TOL_GENERATOR_MW
        if np.any(fixed):
            bad = fixed & (np.abs(production[i] - gen["pmin"]) > TOL_GENERATOR_MW)
            if np.any(bad):
                ts = (np.where(bad)[0] + 1).tolist()[:10]
                verdict.fail("renewable_limits", f"{gen['name']} fixed output not respected at hours {ts}")


def check_hourly_summary(report: dict, case: dict, recomputed: dict, verdict: Verdict) -> None:
    rows = report.get("hourly_summary", [])
    for t, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        try:
            if abs(float(row["demand_MW"]) - case["demand"][t]) > TOL_POWER_BALANCE_MW:
                verdict.fail("demand_balance", f"hourly_summary[{t + 1}].demand_MW disagrees with case demand")
            if abs(float(row["reserve_requirement_MW"]) - case["reserves"][t]) > TOL_RESERVE_MW:
                verdict.fail("spinning_reserve", f"hourly_summary[{t + 1}].reserve_requirement_MW disagrees with case")
            if abs(float(row["thermal_generation_MW"]) - recomputed["thermal_generation_MW"][t]) > TOL_POWER_BALANCE_MW:
                verdict.fail("demand_balance", f"hourly_summary[{t + 1}].thermal_generation_MW disagrees with sum of arrays")
            if abs(float(row["renewable_generation_MW"]) - recomputed["renewable_generation_MW"][t]) > TOL_POWER_BALANCE_MW:
                verdict.fail("demand_balance", f"hourly_summary[{t + 1}].renewable_generation_MW disagrees with sum of arrays")
            if abs(float(row["scheduled_spinning_reserve_MW"]) - recomputed["scheduled_spinning_reserve_MW"][t]) > TOL_RESERVE_MW:
                verdict.fail("spinning_reserve", f"hourly_summary[{t + 1}].scheduled_spinning_reserve_MW disagrees with sum of arrays")
        except (KeyError, TypeError, ValueError):
            pass
    summary = report.get("summary", {})
    try:
        if abs(float(summary["max_demand_balance_violation_MW"]) - recomputed["max_demand_balance_violation_MW"]) > TOL_POWER_BALANCE_MW:
            verdict.fail("demand_balance", "summary.max_demand_balance_violation_MW disagrees with recomputed value")
    except (KeyError, TypeError, ValueError):
        pass
    try:
        if abs(float(summary["max_reserve_shortfall_MW"]) - recomputed["max_reserve_shortfall_MW"]) > TOL_RESERVE_MW:
            verdict.fail("spinning_reserve", "summary.max_reserve_shortfall_MW disagrees with recomputed value")
    except (KeyError, TypeError, ValueError):
        pass


def check_min_up_down(arrays: dict, case: dict, verdict: Verdict) -> None:
    u = arrays["commitment"]
    v = arrays["startup"]
    w = arrays["shutdown"]
    T = case["T"]
    for g, gen in enumerate(case["thermal"]):
        if gen["u0"] == 1 and gen["time_up_t0"] < gen["min_up"]:
            remaining = min(T, gen["min_up"] - gen["time_up_t0"])
            if not np.all(u[g, :remaining] == 1):
                offs = np.where(u[g, :remaining] == 0)[0]
                verdict.fail(
                    "initial_conditions",
                    f"{gen['name']} initial min-up window 0..{remaining - 1} violated at hours {(offs + 1).tolist()[:10]}",
                )
        if gen["u0"] == 0 and gen["time_down_t0"] < gen["min_down"]:
            remaining = min(T, gen["min_down"] - gen["time_down_t0"])
            if not np.all(u[g, :remaining] == 0):
                ons = np.where(u[g, :remaining] == 1)[0]
                verdict.fail(
                    "initial_conditions",
                    f"{gen['name']} initial min-down window 0..{remaining - 1} violated at hours {(ons + 1).tolist()[:10]}",
                )
        for t in range(T):
            if v[g, t] == 1:
                end = min(T, t + gen["min_up"])
                if not np.all(u[g, t:end] == 1):
                    offs = np.where(u[g, t:end] == 0)[0]
                    verdict.fail(
                        "minimum_up_down",
                        f"{gen['name']} min-up after startup t={t + 1} violated at offsets {offs.tolist()[:10]}",
                    )
            if w[g, t] == 1:
                end = min(T, t + gen["min_down"])
                if not np.all(u[g, t:end] == 0):
                    ons = np.where(u[g, t:end] == 1)[0]
                    verdict.fail(
                        "minimum_up_down",
                        f"{gen['name']} min-down after shutdown t={t + 1} violated at offsets {ons.tolist()[:10]}",
                    )


def startup_cost_for_duration(startups: list[tuple[int, float]], offline_duration: int) -> float:
    chosen = startups[0][1]
    for lag, cost in startups:
        if lag <= offline_duration:
            chosen = cost
        else:
            break
    return chosen


def piecewise_total_cost(curve: list[tuple[float, float]], output_mw: float, name: str) -> float:
    if output_mw < curve[0][0] - TOL_GENERATOR_MW:
        raise ValueError(f"{name} production {output_mw} below first cost point {curve[0][0]}")
    if output_mw > curve[-1][0] + TOL_GENERATOR_MW:
        raise ValueError(f"{name} production {output_mw} above last cost point {curve[-1][0]}")
    if output_mw <= curve[0][0]:
        return curve[0][1]
    for (mw0, c0), (mw1, c1) in zip(curve, curve[1:]):
        if output_mw <= mw1 + TOL_GENERATOR_MW:
            if output_mw >= mw1:
                return c1
            slope = (c1 - c0) / (mw1 - mw0)
            return c0 + slope * (output_mw - mw0)
    return curve[-1][1]


def recompute_total_cost(arrays: dict, case: dict, verdict: Verdict) -> float:
    u = arrays["commitment"]
    v = arrays["startup"]
    production = arrays["thermal_production"]
    total = 0.0
    for g, gen in enumerate(case["thermal"]):
        offline = gen["time_down_t0"] if gen["u0"] == 0 else 0
        for t in range(case["T"]):
            if v[g, t] == 1:
                total += startup_cost_for_duration(gen["startup"], offline)
            if u[g, t] == 1:
                try:
                    total += piecewise_total_cost(gen["piecewise"], float(production[g, t]), gen["name"])
                except ValueError as exc:
                    verdict.fail("cost_consistency", str(exc))
                offline = 0
            else:
                offline += 1
    return float(total)


def check_cost(report: dict, recomputed_cost: float, verdict: Verdict) -> None:
    summary = report.get("summary", {})
    try:
        reported = float(summary["objective_cost"])
    except (KeyError, TypeError, ValueError):
        verdict.fail("cost_consistency", "summary.objective_cost not numeric")
        return
    if not math.isfinite(reported) or reported <= 0:
        verdict.fail("cost_consistency", f"summary.objective_cost={reported} must be positive finite")
        return
    tol = max(TOL_COST_ABS, TOL_COST_REL * max(1.0, abs(recomputed_cost)))
    if abs(reported - recomputed_cost) > tol:
        verdict.fail(
            "cost_consistency",
            f"summary.objective_cost={reported:.4f} vs recomputed={recomputed_cost:.4f} (tol={tol:.4f})",
        )


def run_validation(network_path: Path, report_path: Path) -> tuple[Verdict, dict]:
    verdict = Verdict()
    network = _load_json(network_path, verdict, "network.json")
    report = _load_json(report_path, verdict, "report.json")
    if network is None or report is None:
        return verdict, {}

    case = parse_case(network, verdict)
    if case is None:
        return verdict, {}

    check_summary_schema(report, case, verdict)
    arrays = extract_arrays(report, case, verdict)
    if arrays is None:
        return verdict, {}

    check_transitions(arrays, case, verdict)
    check_summary_counts(report, arrays, verdict)
    check_must_run(arrays, case, verdict)
    check_generator_limits(arrays, case, verdict)
    check_reserve_deliverability_and_ramping(arrays, case, verdict)
    recomputed_hourly = check_system_balance(arrays, case, verdict)
    check_renewable_limits(arrays, case, verdict)
    check_hourly_summary(report, case, recomputed_hourly, verdict)
    check_min_up_down(arrays, case, verdict)
    recomputed_cost = recompute_total_cost(arrays, case, verdict)
    check_cost(report, recomputed_cost, verdict)

    recomputed_summary = {
        "time_periods": case["T"],
        "num_thermal_generators": len(case["thermal"]),
        "num_renewable_generators": len(case["renewable"]),
        "total_startups": int(arrays["startup"].sum()),
        "total_shutdowns": int(arrays["shutdown"].sum()),
        "max_demand_balance_violation_MW": recomputed_hourly["max_demand_balance_violation_MW"],
        "max_reserve_shortfall_MW": recomputed_hourly["max_reserve_shortfall_MW"],
        "objective_cost": recomputed_cost,
    }
    recomputed_hourly_rows = [
        {
            "hour": t + 1,
            "demand_MW": float(case["demand"][t]),
            "thermal_generation_MW": float(recomputed_hourly["thermal_generation_MW"][t]),
            "renewable_generation_MW": float(recomputed_hourly["renewable_generation_MW"][t]),
            "reserve_requirement_MW": float(case["reserves"][t]),
            "scheduled_spinning_reserve_MW": float(recomputed_hourly["scheduled_spinning_reserve_MW"][t]),
        }
        for t in range(case["T"])
    ]
    return verdict, {"summary": recomputed_summary, "hourly_summary": recomputed_hourly_rows}


def emit(verdict: Verdict, recomputed: dict, out_path: Path | None) -> int:
    result: dict[str, Any] = {
        "overall": "pass" if verdict.overall_pass() else "fail",
        "schema_errors": verdict.schema_errors,
        "parse_errors": verdict.parse_errors,
        "constraint_checks": {
            k: {"status": "pass" if not violations else "fail", "violations": violations}
            for k, violations in verdict.checks.items()
        },
        "recomputed": recomputed,
    }
    text = json.dumps(result, indent=2, default=float)
    print(text)
    if out_path is not None:
        out_path.write_text(text, encoding="utf-8")
    return 0 if result["overall"] == "pass" else 1


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Validate a unit-commitment schedule.")
    parser.add_argument("network", type=Path, help="Path to network.json (pglib-uc style)")
    parser.add_argument("report", type=Path, help="Path to report.json produced by the agent")
    parser.add_argument("--out", type=Path, default=None, help="Optional path to also write the verdict JSON")
    args = parser.parse_args(argv)
    verdict, recomputed = run_validation(args.network, args.report)
    return emit(verdict, recomputed, args.out)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

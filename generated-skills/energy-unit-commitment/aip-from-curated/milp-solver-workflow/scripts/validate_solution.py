"""Independent post-solve validation for the extracted report arrays.

This framework supports the discipline the skill body requires:

* Validation reads ONLY the original input data and the extracted/report
  arrays. It does not touch solver internals, variable indices, or
  constraint matrices. A bug in the solver-wiring code therefore cannot
  fool the validator.
* Every constraint family judged by the final report must have a
  validator entry. The matching checklist sits in `SKILL.md` § Match
  Model Rows To Validation and `references/modeling-patterns.md`.
* Validation recomputes the objective from inputs plus report arrays.
  A drift between solver objective and recomputed objective is the
  loudest possible signal that internal-vs-report convention conversion
  is wrong.

The bundled helpers cover the families common to most time-expanded
MILPs:

* `check_binary_integrality` — every binary array is within tolerance
  of 0/1.
* `check_balance` — system-wide balance per period
  (`sum_g production - demand == 0`).
* `check_capacity_bounds` — per-resource per-period
  `pmin * u <= production <= pmax * u`.
* `check_ramp_limits` — `|production[t] - production[t-1]| <= ramp`
  with separate startup/shutdown ramps when supplied.
* `check_min_up_down` — minimum on/off duration windows around
  transitions.
* `check_transitions` — startup/shutdown indicators consistent with
  `u[t] - u[t-1]`.
* `check_reserve` — production + reserve <= pmax * u, reserve <= ramp.

Each check returns a list of violation dicts. The aggregator
`run_all_checks` collects them by family and recomputes the objective
from the report arrays via a caller-supplied closure.

The validator is intentionally lenient on what is *NOT* present: a
problem without a reserve concept passes `check_reserve` vacuously when
the corresponding array is omitted. Callers should compose the checks
appropriate to their model and assert that every family judged by the
final report has a corresponding entry — silent absence of a family is
the failure mode this skill is meant to prevent.
"""

from __future__ import annotations

import math
from typing import Callable

import numpy as np

DEFAULT_INT_TOL = 1e-6
DEFAULT_NUMERIC_TOL = 1e-4


def check_binary_integrality(
    arrays: dict[str, np.ndarray],
    tol: float = DEFAULT_INT_TOL,
) -> list[dict]:
    """Each value in every supplied array must be within `tol` of 0 or 1.

    Pass `{"commitment": u, "startup": start, ...}`. Returns one entry
    per offending value with its position and distance from the nearer
    integer.
    """
    out: list[dict] = []
    for name, arr in arrays.items():
        a = np.asarray(arr, dtype=float)
        dist = np.minimum(np.abs(a), np.abs(a - 1.0))
        bad = np.argwhere(dist > tol)
        for pos in bad:
            out.append(
                {
                    "array": name,
                    "index": tuple(int(p) for p in pos),
                    "value": float(a[tuple(pos)]),
                    "distance": float(dist[tuple(pos)]),
                }
            )
    return out


def check_balance(
    production: np.ndarray,
    demand: np.ndarray,
    other_supply: np.ndarray | None = None,
    tol: float = DEFAULT_NUMERIC_TOL,
) -> list[dict]:
    """Per-period balance: `sum_g production[g, t] (+ other_supply[t]) == demand[t]`.

    `other_supply` is optional renewable/storage discharge contribution.
    """
    p = np.asarray(production, dtype=float)
    d = np.asarray(demand, dtype=float)
    total = p.sum(axis=0)
    if other_supply is not None:
        total = total + np.asarray(other_supply, dtype=float).reshape(total.shape)
    diff = total - d
    out: list[dict] = []
    for t in np.where(np.abs(diff) > tol)[0]:
        out.append(
            {
                "period": int(t),
                "supply": float(total[t]),
                "demand": float(d[t]),
                "imbalance": float(diff[t]),
            }
        )
    return out


def check_capacity_bounds(
    production: np.ndarray,
    commitment: np.ndarray,
    pmin: np.ndarray,
    pmax: np.ndarray,
    tol: float = DEFAULT_NUMERIC_TOL,
) -> list[dict]:
    """`pmin[g] * u[g, t] <= production[g, t] <= pmax[g] * u[g, t]`.

    `production` and `commitment` may use either actual-MW or
    above-minimum convention — pass `pmin = 0` for the above-minimum
    case.
    """
    p = np.asarray(production, dtype=float)
    u = np.asarray(commitment, dtype=float)
    pmn = np.asarray(pmin, dtype=float).reshape(-1, 1)
    pmx = np.asarray(pmax, dtype=float).reshape(-1, 1)
    low = pmn * u - p
    high = p - pmx * u
    out: list[dict] = []
    for g, t in np.argwhere(low > tol):
        out.append(
            {
                "kind": "below-pmin",
                "resource": int(g),
                "period": int(t),
                "production": float(p[g, t]),
                "min_required": float(pmn[g, 0] * u[g, t]),
            }
        )
    for g, t in np.argwhere(high > tol):
        out.append(
            {
                "kind": "above-pmax",
                "resource": int(g),
                "period": int(t),
                "production": float(p[g, t]),
                "max_allowed": float(pmx[g, 0] * u[g, t]),
            }
        )
    return out


def check_ramp_limits(
    production: np.ndarray,
    commitment: np.ndarray,
    ramp_up: np.ndarray,
    ramp_down: np.ndarray,
    startup_ramp: np.ndarray | None = None,
    shutdown_ramp: np.ndarray | None = None,
    initial_production: np.ndarray | None = None,
    tol: float = DEFAULT_NUMERIC_TOL,
) -> list[dict]:
    """`p[g, t] - p[g, t-1] <= ramp_up[g]` (and symmetric for ramp-down).

    When `startup_ramp` is supplied, the limit when `u[t-1]=0, u[t]=1`
    is `startup_ramp` instead of `ramp_up`. Symmetric for shutdown.

    `initial_production` (length G) anchors `p[g, -1]`. Defaults to 0.
    """
    p = np.asarray(production, dtype=float)
    u = np.asarray(commitment, dtype=float)
    g_count, t_count = p.shape
    ru = np.asarray(ramp_up, dtype=float)
    rd = np.asarray(ramp_down, dtype=float)
    su = np.asarray(startup_ramp, dtype=float) if startup_ramp is not None else None
    sd = np.asarray(shutdown_ramp, dtype=float) if shutdown_ramp is not None else None
    p_init = (
        np.asarray(initial_production, dtype=float)
        if initial_production is not None
        else np.zeros(g_count)
    )
    out: list[dict] = []
    for g in range(g_count):
        prev_p = float(p_init[g])
        prev_u = 1.0 if prev_p > 0 else 0.0
        for t in range(t_count):
            curr_p = float(p[g, t])
            curr_u = float(u[g, t])
            up_limit = float(ru[g])
            dn_limit = float(rd[g])
            if su is not None and prev_u < 0.5 and curr_u > 0.5:
                up_limit = float(su[g])
            if sd is not None and prev_u > 0.5 and curr_u < 0.5:
                dn_limit = float(sd[g])
            if curr_p - prev_p > up_limit + tol:
                out.append(
                    {
                        "kind": "ramp-up",
                        "resource": g,
                        "period": t,
                        "delta": curr_p - prev_p,
                        "limit": up_limit,
                    }
                )
            if prev_p - curr_p > dn_limit + tol:
                out.append(
                    {
                        "kind": "ramp-down",
                        "resource": g,
                        "period": t,
                        "delta": prev_p - curr_p,
                        "limit": dn_limit,
                    }
                )
            prev_p = curr_p
            prev_u = curr_u
    return out


def check_transitions(
    commitment: np.ndarray,
    startup: np.ndarray,
    shutdown: np.ndarray,
    initial_on: np.ndarray | None = None,
    tol: float = DEFAULT_NUMERIC_TOL,
) -> list[dict]:
    """`u[g, t] - u[g, t-1] == start[g, t] - stop[g, t]` and
    `start + stop <= 1`. `initial_on` (length G, {0,1}) anchors
    `u[g, -1]`. Defaults to 0.
    """
    u = np.asarray(commitment, dtype=float)
    s = np.asarray(startup, dtype=float)
    d = np.asarray(shutdown, dtype=float)
    g_count, t_count = u.shape
    u_prev_init = (
        np.asarray(initial_on, dtype=float)
        if initial_on is not None
        else np.zeros(g_count)
    )
    out: list[dict] = []
    for g in range(g_count):
        prev_u = float(u_prev_init[g])
        for t in range(t_count):
            curr_u = float(u[g, t])
            expected = curr_u - prev_u
            actual = float(s[g, t] - d[g, t])
            if abs(expected - actual) > tol:
                out.append(
                    {
                        "kind": "linking",
                        "resource": g,
                        "period": t,
                        "u_delta": expected,
                        "start_minus_stop": actual,
                    }
                )
            if s[g, t] + d[g, t] > 1 + tol:
                out.append(
                    {
                        "kind": "simultaneous-start-stop",
                        "resource": g,
                        "period": t,
                        "value": float(s[g, t] + d[g, t]),
                    }
                )
            prev_u = curr_u
    return out


def check_min_up_down(
    commitment: np.ndarray,
    startup: np.ndarray,
    shutdown: np.ndarray,
    min_up: np.ndarray,
    min_down: np.ndarray,
    tol: float = DEFAULT_NUMERIC_TOL,
) -> list[dict]:
    """After a startup at `t`, `u` must remain 1 for `min_up` periods;
    after a shutdown, 0 for `min_down`. Windows that extend past the
    horizon are NOT enforced (post-horizon obligations are out of scope
    unless the prompt explicitly extends them).
    """
    u = np.asarray(commitment, dtype=float)
    s = np.asarray(startup, dtype=float)
    d = np.asarray(shutdown, dtype=float)
    mu = np.asarray(min_up, dtype=int)
    md = np.asarray(min_down, dtype=int)
    g_count, t_count = u.shape
    out: list[dict] = []
    for g in range(g_count):
        for t in range(t_count):
            if s[g, t] > 0.5:
                window_end = min(t + int(mu[g]), t_count)
                for tau in range(t, window_end):
                    if u[g, tau] < 1 - tol:
                        out.append(
                            {
                                "kind": "min-up",
                                "resource": g,
                                "start_period": t,
                                "violating_period": tau,
                                "u": float(u[g, tau]),
                            }
                        )
            if d[g, t] > 0.5:
                window_end = min(t + int(md[g]), t_count)
                for tau in range(t, window_end):
                    if u[g, tau] > tol:
                        out.append(
                            {
                                "kind": "min-down",
                                "resource": g,
                                "stop_period": t,
                                "violating_period": tau,
                                "u": float(u[g, tau]),
                            }
                        )
    return out


def check_reserve(
    production: np.ndarray,
    reserve: np.ndarray,
    commitment: np.ndarray,
    pmax: np.ndarray,
    ramp_up: np.ndarray,
    reserve_requirement: np.ndarray,
    tol: float = DEFAULT_NUMERIC_TOL,
) -> list[dict]:
    """Joint capacity: `p + reserve <= pmax * u`. Deliverability:
    `reserve <= ramp_up`. System requirement: `sum_g reserve >=
    requirement[t]`.
    """
    p = np.asarray(production, dtype=float)
    r = np.asarray(reserve, dtype=float)
    u = np.asarray(commitment, dtype=float)
    pmx = np.asarray(pmax, dtype=float).reshape(-1, 1)
    ru = np.asarray(ramp_up, dtype=float).reshape(-1, 1)
    req = np.asarray(reserve_requirement, dtype=float)
    out: list[dict] = []
    over_cap = p + r - pmx * u
    for g, t in np.argwhere(over_cap > tol):
        out.append(
            {
                "kind": "joint-capacity",
                "resource": int(g),
                "period": int(t),
                "excess": float(over_cap[g, t]),
            }
        )
    over_ramp = r - ru
    for g, t in np.argwhere(over_ramp > tol):
        out.append(
            {
                "kind": "ramp-deliverability",
                "resource": int(g),
                "period": int(t),
                "reserve": float(r[g, t]),
                "ramp_up": float(ru[g, 0]),
            }
        )
    shortfall = req - r.sum(axis=0)
    for t in np.where(shortfall > tol)[0]:
        out.append(
            {
                "kind": "reserve-shortfall",
                "period": int(t),
                "delivered": float(r.sum(axis=0)[t]),
                "required": float(req[t]),
            }
        )
    return out


def run_all_checks(
    checks: dict[str, list[dict]],
    objective_recomputer: Callable[[], float] | None = None,
    solver_objective: float | None = None,
    objective_tol: float = 1e-2,
) -> dict:
    """Aggregate per-family check results into a single report.

    Parameters
    ----------
    checks
        `{family_name: [violation_dict, ...]}` from the individual
        check functions. Empty lists are passing families.
    objective_recomputer
        Optional zero-arg callable that recomputes the objective from
        inputs and report arrays. When provided, the recomputed value
        is compared to `solver_objective` (if also provided) and any
        drift larger than `objective_tol` is recorded as an error.
    solver_objective
        The objective the solver reported. Compared against the
        recomputed objective.

    Returns
    -------
    `{"ok": bool, "families": {name: {"ok": bool, "violations": [...]}},
      "objective": {"recomputed": float, "solver": float, "drift": float}}`
    """
    family_report: dict[str, dict] = {}
    ok = True
    for fam, violations in checks.items():
        fam_ok = len(violations) == 0
        family_report[fam] = {
            "ok": fam_ok,
            "violation_count": len(violations),
            "violations": violations,
        }
        if not fam_ok:
            ok = False
    obj_report: dict | None = None
    if objective_recomputer is not None:
        recomputed = float(objective_recomputer())
        obj_report = {"recomputed": recomputed}
        if solver_objective is not None:
            drift = recomputed - float(solver_objective)
            obj_report["solver"] = float(solver_objective)
            obj_report["drift"] = drift
            if abs(drift) > objective_tol * max(1.0, abs(recomputed)):
                ok = False
                obj_report["drift_exceeds_tolerance"] = True
    if obj_report and not math.isfinite(obj_report["recomputed"]):
        ok = False
    return {"ok": ok, "families": family_report, "objective": obj_report}

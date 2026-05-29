"""Independent recompute helpers for the validation step.

Every function in this module reads only the original input case plus the
extracted report-units arrays — never the solver internals — and returns a
max-violation magnitude plus a pass/fail flag. Compose them in
`validate-independently` so the set of checks mirrors the constraint
families the model encoded (see `references/patterns.md` § Validation Map).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable

import numpy as np


@dataclass
class CheckResult:
    name: str
    passed: bool
    max_violation: float
    detail: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


def _max_pos(arr: np.ndarray) -> float:
    arr = np.asarray(arr, dtype=float)
    if arr.size == 0:
        return 0.0
    return float(np.maximum(arr, 0.0).max())


def balance_check(
    supply_arrays: Iterable[np.ndarray],
    demand: np.ndarray,
    tol: float = 1e-4,
    name: str = "demand_balance",
) -> CheckResult:
    """Check sum(supply) == demand per period (equality)."""
    total = np.zeros_like(np.asarray(demand, dtype=float))
    for s in supply_arrays:
        total = total + np.asarray(s, dtype=float)
    diff = total - np.asarray(demand, dtype=float)
    worst = float(np.max(np.abs(diff)))
    return CheckResult(name, worst <= tol, worst, f"max |supply - demand| = {worst:.4g}")


def reserve_adequacy_check(
    scheduled_reserve_total: np.ndarray,
    requirement: np.ndarray,
    tol: float = 1e-4,
    name: str = "spinning_reserve",
) -> CheckResult:
    diff = np.asarray(requirement, dtype=float) - np.asarray(scheduled_reserve_total, dtype=float)
    worst = _max_pos(diff)
    return CheckResult(name, worst <= tol, worst, f"max (req - scheduled) = {worst:.4g}")


def online_capacity_check(
    commitment: np.ndarray,
    production: np.ndarray,
    min_out: np.ndarray,
    max_out: np.ndarray,
    tol: float = 1e-4,
    name: str = "generator_limits",
) -> CheckResult:
    """Production stays inside [min_out, max_out] when committed, and ==0 when offline."""
    u = np.asarray(commitment, dtype=float)
    p = np.asarray(production, dtype=float)
    pmin = np.broadcast_to(np.asarray(min_out, dtype=float)[:, None], p.shape)
    pmax = np.broadcast_to(np.asarray(max_out, dtype=float)[:, None], p.shape)
    lower_viol = pmin * u - p
    upper_viol = p - pmax * u
    off_viol = np.where(u <= 0.5, np.abs(p), 0.0)
    worst = float(
        max(_max_pos(lower_viol), _max_pos(upper_viol), float(off_viol.max() if off_viol.size else 0.0))
    )
    return CheckResult(name, worst <= tol, worst, f"max bound violation = {worst:.4g}")


def joint_reserve_capacity_check(
    commitment: np.ndarray,
    production: np.ndarray,
    reserve: np.ndarray,
    max_out: np.ndarray,
    tol: float = 1e-4,
    name: str = "reserve_deliverability",
) -> CheckResult:
    """Production + reserve <= max_out * commitment."""
    u = np.asarray(commitment, dtype=float)
    p = np.asarray(production, dtype=float)
    r = np.asarray(reserve, dtype=float)
    pmax = np.broadcast_to(np.asarray(max_out, dtype=float)[:, None], p.shape)
    viol = p + r - pmax * u
    worst = _max_pos(viol)
    return CheckResult(name, worst <= tol, worst, f"max (p+r - pmax*u) = {worst:.4g}")


def ramp_check(
    commitment: np.ndarray,
    production: np.ndarray,
    reserve: np.ndarray,
    startup: np.ndarray,
    shutdown: np.ndarray,
    ramp_up: np.ndarray,
    ramp_down: np.ndarray,
    startup_capability: np.ndarray,
    shutdown_capability: np.ndarray,
    min_out: np.ndarray,
    initial_commitment: np.ndarray,
    initial_production: np.ndarray,
    tol: float = 1e-4,
    name: str = "ramping",
) -> CheckResult:
    """Period-to-period ramp limit, with startup/shutdown capability surcharges.

    Up:    p[t] + r[t] - p[t-1] <= ramp_up * u[t-1] + startup_capability * start[t]
    Down:  p[t-1] - p[t]        <= ramp_down * u[t] + shutdown_capability * shutdown[t]
    """
    p = np.asarray(production, dtype=float)
    r = np.asarray(reserve, dtype=float)
    u = np.asarray(commitment, dtype=float)
    st = np.asarray(startup, dtype=float)
    sd = np.asarray(shutdown, dtype=float)
    G, T = p.shape
    ru = np.broadcast_to(np.asarray(ramp_up, dtype=float)[:, None], p.shape)
    rd = np.broadcast_to(np.asarray(ramp_down, dtype=float)[:, None], p.shape)
    suc = np.broadcast_to(np.asarray(startup_capability, dtype=float)[:, None], p.shape)
    sdc = np.broadcast_to(np.asarray(shutdown_capability, dtype=float)[:, None], p.shape)
    u_prev = np.empty_like(u)
    u_prev[:, 0] = np.asarray(initial_commitment, dtype=float)
    u_prev[:, 1:] = u[:, :-1]
    p_prev = np.empty_like(p)
    p_prev[:, 0] = np.asarray(initial_production, dtype=float)
    p_prev[:, 1:] = p[:, :-1]
    up_viol = (p + r) - p_prev - ru * u_prev - suc * st
    down_viol = p_prev - p - rd * u - sdc * sd
    worst = float(max(_max_pos(up_viol), _max_pos(down_viol)))
    return CheckResult(name, worst <= tol, worst, f"max ramp violation = {worst:.4g}")


def startup_shutdown_logic_check(
    commitment: np.ndarray,
    startup: np.ndarray,
    shutdown: np.ndarray,
    initial_commitment: np.ndarray,
    tol: float = 1e-4,
    name: str = "startup_shutdown_logic",
) -> CheckResult:
    """u[t] - u[t-1] == start[t] - shutdown[t], and start+shutdown <= 1."""
    u = np.asarray(commitment, dtype=float)
    st = np.asarray(startup, dtype=float)
    sd = np.asarray(shutdown, dtype=float)
    u_prev = np.empty_like(u)
    u_prev[:, 0] = np.asarray(initial_commitment, dtype=float)
    u_prev[:, 1:] = u[:, :-1]
    eq_viol = np.abs(u - u_prev - (st - sd))
    excl_viol = (st + sd) - 1.0
    worst = float(max(eq_viol.max() if eq_viol.size else 0.0, _max_pos(excl_viol)))
    return CheckResult(name, worst <= tol, worst, f"max linking violation = {worst:.4g}")


def min_up_down_check(
    commitment: np.ndarray,
    startup: np.ndarray,
    shutdown: np.ndarray,
    min_up: np.ndarray,
    min_down: np.ndarray,
    initial_commitment: np.ndarray,
    initial_uptime: np.ndarray,
    initial_downtime: np.ndarray,
    tol: float = 1e-4,
    name: str = "minimum_up_down",
) -> CheckResult:
    """For each (g, t): start[t]==1 forces u[t..t+min_up-1]=1; shutdown[t]==1 forces u=0 over min_down."""
    u = np.asarray(commitment, dtype=float)
    st = np.asarray(startup, dtype=float)
    sd = np.asarray(shutdown, dtype=float)
    G, T = u.shape
    up = np.asarray(min_up, dtype=int)
    dn = np.asarray(min_down, dtype=int)
    u_init = np.asarray(initial_commitment, dtype=float)
    init_up = np.asarray(initial_uptime, dtype=int)
    init_dn = np.asarray(initial_downtime, dtype=int)
    worst = 0.0
    for g in range(G):
        for t in range(T):
            if st[g, t] > 0.5:
                end = min(T, t + int(up[g]))
                missing = (1.0 - u[g, t:end]).max() if end > t else 0.0
                worst = max(worst, float(missing))
            if sd[g, t] > 0.5:
                end = min(T, t + int(dn[g]))
                excess = u[g, t:end].max() if end > t else 0.0
                worst = max(worst, float(excess))
        if u_init[g] > 0.5 and init_up[g] < up[g]:
            need = int(up[g] - init_up[g])
            end = min(T, need)
            if end > 0:
                worst = max(worst, float((1.0 - u[g, :end]).max()))
        if u_init[g] < 0.5 and init_dn[g] < dn[g]:
            need = int(dn[g] - init_dn[g])
            end = min(T, need)
            if end > 0:
                worst = max(worst, float(u[g, :end].max()))
    return CheckResult(name, worst <= tol, worst, f"max min-up/down violation = {worst:.4g}")


def must_run_check(
    commitment: np.ndarray,
    must_run_mask: np.ndarray,
    tol: float = 1e-4,
    name: str = "must_run",
) -> CheckResult:
    """For generators flagged must-run, u==1 in every period."""
    u = np.asarray(commitment, dtype=float)
    mask = np.asarray(must_run_mask, dtype=bool)
    if not mask.any():
        return CheckResult(name, True, 0.0, "no must-run generators")
    viol = 1.0 - u[mask, :]
    worst = float(viol.max() if viol.size else 0.0)
    return CheckResult(name, worst <= tol, worst, f"max (1 - u) on must-run = {worst:.4g}")


def initial_conditions_check(
    commitment: np.ndarray,
    initial_commitment: np.ndarray,
    initial_uptime: np.ndarray,
    initial_downtime: np.ndarray,
    min_up: np.ndarray,
    min_down: np.ndarray,
    tol: float = 1e-4,
    name: str = "initial_conditions",
) -> CheckResult:
    """Initial obligations carried from t=0 are respected by u[:, :need]."""
    u = np.asarray(commitment, dtype=float)
    u_init = np.asarray(initial_commitment, dtype=float)
    init_up = np.asarray(initial_uptime, dtype=int)
    init_dn = np.asarray(initial_downtime, dtype=int)
    up = np.asarray(min_up, dtype=int)
    dn = np.asarray(min_down, dtype=int)
    G, T = u.shape
    worst = 0.0
    for g in range(G):
        if u_init[g] > 0.5 and init_up[g] < up[g]:
            need = min(T, int(up[g] - init_up[g]))
            if need > 0:
                worst = max(worst, float((1.0 - u[g, :need]).max()))
        if u_init[g] < 0.5 and init_dn[g] < dn[g]:
            need = min(T, int(dn[g] - init_dn[g]))
            if need > 0:
                worst = max(worst, float(u[g, :need].max()))
    return CheckResult(name, worst <= tol, worst, f"max initial-obligation violation = {worst:.4g}")


def renewable_limits_check(
    production: np.ndarray,
    max_available: np.ndarray,
    tol: float = 1e-4,
    name: str = "renewable_limits",
) -> CheckResult:
    p = np.asarray(production, dtype=float)
    cap = np.asarray(max_available, dtype=float)
    upper_viol = p - cap
    lower_viol = -p
    worst = float(max(_max_pos(upper_viol), _max_pos(lower_viol)))
    return CheckResult(name, worst <= tol, worst, f"max bound violation = {worst:.4g}")


def cost_consistency_check(
    reported_objective: float,
    recomputed_objective: float,
    abs_tol: float = 1e-3,
    rel_tol: float = 1e-3,
    name: str = "cost_consistency",
) -> CheckResult:
    diff = abs(float(reported_objective) - float(recomputed_objective))
    scale = max(1.0, abs(float(recomputed_objective)))
    passed = diff <= abs_tol or diff / scale <= rel_tol
    return CheckResult(
        name,
        passed,
        diff,
        f"|reported - recomputed| = {diff:.6g}; recomputed = {recomputed_objective:.6g}",
    )


def recompute_thermal_cost(
    commitment: np.ndarray,
    startup: np.ndarray,
    production: np.ndarray,
    cost_curves: list,
    startup_cost: np.ndarray,
    no_load_cost: np.ndarray | None = None,
) -> float:
    """Total thermal cost from report-units arrays + input case.

    `cost_curves` is a list (one per thermal generator) where each entry is a
    list of (output_breakpoint, total_cost_at_breakpoint) pairs sorted by
    output. Cost between breakpoints is linear interpolation. When the
    generator is offline (u==0) its cost contribution is 0. `no_load_cost`
    is added per online period if supplied.
    """
    u = np.asarray(commitment, dtype=float)
    st = np.asarray(startup, dtype=float)
    p = np.asarray(production, dtype=float)
    G, T = p.shape
    total = 0.0
    for g in range(G):
        curve = cost_curves[g]
        xs = np.asarray([pt[0] for pt in curve], dtype=float)
        ys = np.asarray([pt[1] for pt in curve], dtype=float)
        for t in range(T):
            if u[g, t] > 0.5:
                total += float(np.interp(p[g, t], xs, ys))
                if no_load_cost is not None:
                    total += float(no_load_cost[g])
            if st[g, t] > 0.5:
                total += float(startup_cost[g])
    return total


def assemble_report(checks: Iterable[CheckResult]) -> dict:
    """Aggregate per-family checks into a single validation report.

    Returns a dict with `all_pass`, per-family `pass`/`max_violation`, and
    `failing` (list of family names that failed). This is the artifact
    `write-final-output` gates on.
    """
    families: dict[str, dict] = {}
    failing: list[str] = []
    overall = True
    for c in checks:
        families[c.name] = {
            "pass": bool(c.passed),
            "max_violation": float(c.max_violation),
            "detail": c.detail,
        }
        if not c.passed:
            failing.append(c.name)
            overall = False
    return {"all_pass": overall, "families": families, "failing": failing}

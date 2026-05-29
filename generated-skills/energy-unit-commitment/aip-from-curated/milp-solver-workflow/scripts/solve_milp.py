"""Open-source MILP solve via HiGHS through `scipy.optimize.milp`.

HiGHS is the default open-source MILP solver shipped with SciPy. This
helper wraps the solver call with the discipline the skill body
requires:

* Always set an explicit `time_limit` and `mip_rel_gap`. Defaults are
  10 minutes wall clock and 1% relative gap — appropriate for a
  24-period unit-commitment instance. Pass smaller values for tight
  budgets, larger for harder instances.
* Always silence solver output (`disp=False`). Solver chatter clobbers
  agent logs and obscures the structured result.
* Always check `result.x is not None` before reading the incumbent. A
  time-limit hit with a feasible incumbent is usable; a failure with
  no incumbent is not a solution and must surface as an error.
* Always capture a reliable gap/bound when the solver provides one.
  Time-limited runs report the best bound separately from the
  incumbent — keep them distinct in the final report. Never
  back-compute a "gap" from the incumbent alone.

Returns a `SolveResult` dataclass with structured fields rather than the
raw SciPy result object, so downstream code does not couple to SciPy's
attribute layout.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np


@dataclass
class SolveResult:
    """Structured outcome of a MILP solve.

    Attributes
    ----------
    status
        SciPy status code (0 success, 1 iter/time limit, 2 infeasible,
        etc.). Use `feasible` and `has_incumbent` for decisions; status
        is kept for the final report.
    message
        Solver-supplied human-readable message.
    has_incumbent
        True when `x` is a feasible (per the solver) point.
    feasible
        True when the solver reports a feasible status AND `x` is not
        None. A "time-limit with incumbent" is feasible from the
        solver's view — re-check with independent validation regardless.
    x
        Incumbent variable vector (length n_vars) or None.
    objective
        Objective value at `x`, or `inf` when no incumbent.
    best_bound
        Best dual bound (lower bound for a minimization) when the
        solver reports one. None when not available.
    mip_gap
        Relative gap `(obj - bound) / max(|obj|, eps)` when both are
        available. None when the bound is missing. Keep this distinct
        from feasibility — a solver may report 0% gap on an infeasible
        problem if the relaxation is also infeasible.
    raw
        The full SciPy result object for callers that need fields not
        promoted to dataclass attributes.
    """

    status: int
    message: str
    has_incumbent: bool
    feasible: bool
    x: np.ndarray | None
    objective: float
    best_bound: float | None
    mip_gap: float | None
    raw: Any = field(repr=False, default=None)


def solve(
    *,
    c: np.ndarray,
    integrality: np.ndarray,
    lb: np.ndarray,
    ub: np.ndarray,
    A,
    row_lb: np.ndarray,
    row_ub: np.ndarray,
    time_limit: float = 600.0,
    mip_rel_gap: float = 0.01,
    extra_options: dict | None = None,
) -> SolveResult:
    """Solve the MILP and return a structured result.

    Parameters
    ----------
    c
        Cost vector (length n_vars).
    integrality
        Per-variable integrality flag from `VariableMap.integrality`.
    lb, ub
        Per-variable bounds from `VariableMap.lb` and `.ub`.
    A, row_lb, row_ub
        Sparse constraint matrix and per-row bounds from
        `ConstraintBuilder.to_scipy()`.
    time_limit, mip_rel_gap
        Solver stopping criteria. Defaults: 600s wall, 1% relative gap.
    extra_options
        Optional extra HiGHS options merged on top of the defaults.

    Raises
    ------
    RuntimeError
        When the solver returns no incumbent (status >= 2 with `x is
        None`). The caller should classify this as infeasible or
        unbounded based on `status` and surface the message.
    """
    from scipy.optimize import LinearConstraint, Bounds, milp

    options = {
        "time_limit": float(time_limit),
        "mip_rel_gap": float(mip_rel_gap),
        "disp": False,
    }
    if extra_options:
        options.update(extra_options)

    constraints = LinearConstraint(A, row_lb, row_ub)
    bounds = Bounds(lb, ub)

    raw = milp(
        c=np.asarray(c, dtype=float),
        integrality=np.asarray(integrality, dtype=int),
        bounds=bounds,
        constraints=constraints,
        options=options,
    )

    status = int(getattr(raw, "status", -1))
    message = str(getattr(raw, "message", "") or "")
    x = getattr(raw, "x", None)
    has_incumbent = x is not None
    # SciPy reports feasibility via status==0; time-limit status (1) still
    # may carry an incumbent that's feasible by the solver's view.
    feasible = has_incumbent and status in (0, 1)
    objective = float(getattr(raw, "fun", math.inf)) if has_incumbent else math.inf

    # `mip_dual_bound` is the HiGHS best-bound field on recent SciPy.
    best_bound = getattr(raw, "mip_dual_bound", None)
    if best_bound is not None:
        try:
            best_bound = float(best_bound)
        except (TypeError, ValueError):
            best_bound = None

    gap = None
    if best_bound is not None and has_incumbent:
        denom = max(abs(objective), 1e-12)
        gap = (objective - best_bound) / denom

    if not has_incumbent:
        # Surface the no-incumbent case loudly. Callers that want to
        # tolerate this (e.g. to retry with relaxed bounds) should catch
        # the exception and inspect `status`/`message`.
        raise RuntimeError(
            f"No incumbent returned: status={status}, message={message!r}"
        )

    return SolveResult(
        status=status,
        message=message,
        has_incumbent=has_incumbent,
        feasible=feasible,
        x=np.asarray(x, dtype=float),
        objective=objective,
        best_bound=best_bound,
        mip_gap=gap,
        raw=raw,
    )

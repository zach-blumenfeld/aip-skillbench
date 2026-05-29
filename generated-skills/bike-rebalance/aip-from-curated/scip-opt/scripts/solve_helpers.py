"""Solver-side helpers for SCIP models: limits, status, and extraction.

Bundles the small fixed routines the curated SKILL.md repeats around
every solve:

* ``set_default_limits`` — apply the curated default time / gap limits
  (300 s, 1% MIP gap). Override per-call if a task demands tighter or
  looser bounds.
* ``require_incumbent`` — fail loudly when SCIP returns no feasible
  solution; the original explicitly requires "at least one incumbent
  before extracting a solution".
* ``is_selected`` — read a binary variable with the conventional
  0.5 threshold (SCIP returns floats even for binaries).
* ``approx_equal`` — assert that a reconstructed objective component
  matches the solver's reported value within numeric tolerance.

Treat solver feasibility as necessary but NOT sufficient. The final
output still needs problem-specific schema and rule checks; that logic
belongs in a task-specific validator, not here.
"""

from __future__ import annotations


DEFAULT_TIME_LIMIT_SECONDS = 300.0
DEFAULT_MIP_GAP = 0.01
BINARY_THRESHOLD = 0.5


def set_default_limits(
    model,
    *,
    time_limit: float = DEFAULT_TIME_LIMIT_SECONDS,
    mip_gap: float = DEFAULT_MIP_GAP,
) -> None:
    """Apply the curated default ``limits/time`` and ``limits/gap``."""
    model.setParam("limits/time", float(time_limit))
    model.setParam("limits/gap", float(mip_gap))


def require_incumbent(model) -> str:
    """Raise if SCIP found no feasible solution; return the status string.

    Run this immediately after ``model.optimize()`` and before pulling
    variable values. The curated source treats "no incumbent" as a hard
    failure — extracting variables from an infeasible model produces
    meaningless numbers.
    """
    status = str(model.getStatus()).lower()
    if model.getNSols() == 0:
        raise RuntimeError(f"SCIP found no feasible solution; status={status}")
    return status


def is_selected(model, var) -> bool:
    """True when a binary variable rounds to 1.

    SCIP returns floats even for binary vars (numerical noise around 0
    and 1). The curated convention is the 0.5 threshold.
    """
    return model.getVal(var) > BINARY_THRESHOLD


def approx_equal(a: float, b: float, *, tol: float = 1e-6) -> bool:
    """Numeric-equality check for objective-component reconstruction."""
    return abs(float(a) - float(b)) <= tol


def assert_objective_component(name: str, reported: float, recomputed: float,
                               *, tol: float = 1e-6) -> None:
    """Fail when a reconstructed objective component disagrees with SCIP.

    Use after extracting a solution to confirm the reported objective
    actually corresponds to the variables you read out. Catches
    indexing / sign / scaling drift between model construction and
    post-processing.
    """
    if not approx_equal(reported, recomputed, tol=tol):
        raise AssertionError(
            f"objective component '{name}' mismatch: "
            f"reported={reported!r}, recomputed={recomputed!r}, tol={tol}"
        )

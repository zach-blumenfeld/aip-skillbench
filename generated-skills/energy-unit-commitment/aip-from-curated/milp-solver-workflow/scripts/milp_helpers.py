"""MILP plumbing: variable map, sparse constraint builder, solver wrapper, extractor.

All four are deterministic, task-agnostic boilerplate the source skill embeds as
inline Python. Centralizing them here keeps the per-task code focused on the
actual constraint algebra.

Designed to compose without imposing a class hierarchy: instantiate `VarMap` and
`SparseModel`, push variables/rows, call `build()`, hand the pieces to
`solve_milp()`, then read out blocks with `extract()`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import csr_matrix

INF = math.inf


@dataclass
class VarMap:
    """Allocate named blocks of decision variables in a single dense vector.

    Each `alloc(name, shape, lb, ub, integer)` reserves a contiguous slice
    and returns an ndarray of column indices with the requested shape.
    `build()` materializes the `(c, lb, ub, integrality)` vectors aligned to
    those indices. `c` is filled by `set_obj()` calls; unset positions stay 0.
    """

    n: int = 0
    offsets: dict[str, np.ndarray] = field(default_factory=dict)
    _lb: list[float] = field(default_factory=list)
    _ub: list[float] = field(default_factory=list)
    _integer: list[bool] = field(default_factory=list)
    _obj: list[float] = field(default_factory=list)

    def alloc(
        self,
        name: str,
        shape: int | tuple[int, ...],
        lb: float = 0.0,
        ub: float = INF,
        integer: bool = False,
    ) -> np.ndarray:
        if name in self.offsets:
            raise ValueError(f"variable block already allocated: {name!r}")
        shape_t = (shape,) if isinstance(shape, int) else tuple(shape)
        size = int(np.prod(shape_t)) if shape_t else 0
        if size == 0:
            raise ValueError(f"empty allocation for {name!r}: shape={shape_t}")
        idx = np.arange(self.n, self.n + size).reshape(shape_t)
        self.offsets[name] = idx
        self.n += size
        self._lb.extend([float(lb)] * size)
        self._ub.extend([float(ub)] * size)
        self._integer.extend([bool(integer)] * size)
        self._obj.extend([0.0] * size)
        return idx

    def set_obj(self, idx: np.ndarray | int, coeff: np.ndarray | float) -> None:
        """Assign objective coefficients for an already-allocated block (or single var)."""
        flat_idx = np.atleast_1d(np.asarray(idx)).ravel()
        flat_coef = np.broadcast_to(np.asarray(coeff, dtype=float), flat_idx.shape).ravel()
        for j, c in zip(flat_idx.tolist(), flat_coef.tolist()):
            if j < 0 or j >= self.n:
                raise IndexError(f"variable index {j} out of range [0, {self.n})")
            self._obj[j] = float(c)

    def add_obj(self, idx: np.ndarray | int, coeff: np.ndarray | float) -> None:
        """Accumulate objective coefficients (use when assembling cost in pieces)."""
        flat_idx = np.atleast_1d(np.asarray(idx)).ravel()
        flat_coef = np.broadcast_to(np.asarray(coeff, dtype=float), flat_idx.shape).ravel()
        for j, c in zip(flat_idx.tolist(), flat_coef.tolist()):
            if j < 0 or j >= self.n:
                raise IndexError(f"variable index {j} out of range [0, {self.n})")
            self._obj[j] += float(c)

    def build(self) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        return (
            np.asarray(self._obj, dtype=float),
            np.asarray(self._lb, dtype=float),
            np.asarray(self._ub, dtype=float),
            np.asarray(self._integer, dtype=int),
        )


@dataclass
class SparseModel:
    """Accumulate constraint rows in COO form, then assemble into a SciPy `LinearConstraint`.

    Always write the intended inequality first, then move variable terms to the
    LHS. `add_row(terms, lo, hi)` takes `terms = [(col_index, coefficient), ...]`
    and the row's lower/upper bound. Use `lo=-INF` for `≤ hi`, `hi=INF` for `≥ lo`,
    and `lo == hi` for equality. Zero coefficients are silently dropped.
    """

    n_vars: int
    rows: list[int] = field(default_factory=list)
    cols: list[int] = field(default_factory=list)
    vals: list[float] = field(default_factory=list)
    lb: list[float] = field(default_factory=list)
    ub: list[float] = field(default_factory=list)
    _row: int = 0

    def add_row(
        self,
        terms: Iterable[tuple[int, float]],
        lo: float = -INF,
        hi: float = INF,
    ) -> int:
        any_term = False
        for j, a in terms:
            if a == 0.0:
                continue
            j_int = int(j)
            if j_int < 0 or j_int >= self.n_vars:
                raise IndexError(f"col {j_int} out of range [0, {self.n_vars})")
            self.rows.append(self._row)
            self.cols.append(j_int)
            self.vals.append(float(a))
            any_term = True
        if not any_term:
            if not (lo <= 0.0 <= hi):
                raise ValueError(
                    f"empty row with infeasible bounds: lo={lo}, hi={hi} (no LHS terms)"
                )
            return -1
        self.lb.append(float(lo))
        self.ub.append(float(hi))
        added = self._row
        self._row += 1
        return added

    def build(self) -> LinearConstraint:
        if not self.lb:
            raise ValueError("no constraint rows added")
        A = csr_matrix(
            (self.vals, (self.rows, self.cols)),
            shape=(len(self.lb), self.n_vars),
        )
        return LinearConstraint(A, np.asarray(self.lb), np.asarray(self.ub))


@dataclass
class SolverResult:
    status: int
    message: str
    objective: float
    x: np.ndarray
    reported_gap: float | None
    raw: object


def solve_milp(
    c: np.ndarray,
    constraints: LinearConstraint,
    integrality: np.ndarray,
    lb: np.ndarray,
    ub: np.ndarray,
    time_limit: float = 600.0,
    mip_rel_gap: float = 0.01,
    disp: bool = False,
) -> SolverResult:
    """Solve via HiGHS through SciPy. Raise if no incumbent is returned.

    A ``time_limit`` status (status==1 in HiGHS via SciPy) is acceptable
    iff ``result.x`` is populated — a feasible incumbent with no proof of
    optimality is still a usable schedule. Status without an incumbent
    means the solver gave up before finding one and the caller must treat
    that as infeasibility.
    """
    result = milp(
        c=np.asarray(c, dtype=float),
        integrality=np.asarray(integrality, dtype=int),
        bounds=Bounds(np.asarray(lb, dtype=float), np.asarray(ub, dtype=float)),
        constraints=constraints,
        options={
            "time_limit": float(time_limit),
            "mip_rel_gap": float(mip_rel_gap),
            "disp": bool(disp),
        },
    )
    if result.x is None:
        raise RuntimeError(
            f"No incumbent returned: status={result.status}, message={result.message!r}"
        )
    reported_gap = _extract_gap(result, mip_rel_gap)
    return SolverResult(
        status=int(result.status),
        message=str(result.message),
        objective=float(result.fun),
        x=np.asarray(result.x, dtype=float),
        reported_gap=reported_gap,
        raw=result,
    )


def _extract_gap(result, fallback_rel_gap: float) -> float | None:
    """Best-effort MIP gap extraction. Return None when no reliable bound exists."""
    mip_dual = getattr(result, "mip_dual_bound", None)
    fun = getattr(result, "fun", None)
    if mip_dual is None or fun is None or not math.isfinite(mip_dual) or not math.isfinite(fun):
        return None
    if abs(fun) < 1e-12:
        if abs(mip_dual) < 1e-12:
            return 0.0
        return None
    gap = abs(fun - mip_dual) / max(1e-12, abs(fun))
    return float(gap)


def extract(
    name: str,
    x: np.ndarray,
    var_map: VarMap,
    round_binary_tol: float = 1e-6,
) -> np.ndarray:
    """Pull a named block from the incumbent. Round binaries iff within tolerance.

    Any binary outside the tolerance bubble of {0, 1} raises — that is a
    solver/modeling signal, not a rounding question.
    """
    if name not in var_map.offsets:
        raise KeyError(f"variable block not found: {name!r}")
    idx = var_map.offsets[name]
    block = x[idx]
    flat = idx.ravel()
    is_int = np.array([var_map._integer[j] for j in flat.tolist()], dtype=bool).reshape(idx.shape)
    if not is_int.any():
        return block
    lb_arr = np.array([var_map._lb[j] for j in flat.tolist()], dtype=float).reshape(idx.shape)
    ub_arr = np.array([var_map._ub[j] for j in flat.tolist()], dtype=float).reshape(idx.shape)
    is_binary = is_int & (lb_arr >= 0.0 - 1e-12) & (ub_arr <= 1.0 + 1e-12)
    if is_binary.any():
        b = block[is_binary]
        gap = np.minimum(np.abs(b - 0.0), np.abs(b - 1.0))
        if (gap > round_binary_tol).any():
            worst = float(gap.max())
            raise ValueError(
                f"binary block {name!r} has values far from 0/1 "
                f"(max distance {worst:.3e} > tol {round_binary_tol:.0e}); "
                "investigate the model before rounding"
            )
        rounded = np.where(b >= 0.5, 1.0, 0.0)
        block = block.copy()
        block[is_binary] = rounded
    integer_nonbinary = is_int & ~is_binary
    if integer_nonbinary.any():
        b = block[integer_nonbinary]
        gap = np.abs(b - np.round(b))
        if (gap > round_binary_tol).any():
            worst = float(gap.max())
            raise ValueError(
                f"integer block {name!r} has non-integral values "
                f"(max distance {worst:.3e} > tol {round_binary_tol:.0e})"
            )
        block = block.copy()
        block[integer_nonbinary] = np.round(b)
    return block

"""Sparse constraint-row builder with sign-safe row encoding.

`scipy.optimize.milp` accepts constraints as `LinearConstraint(A, lb, ub)`
where `A` can be a dense matrix or any scipy.sparse matrix. For
time-expanded MILPs, rows reach the tens of thousands while each row
touches a handful of variables — the dense matrix is mostly zeros.
`ConstraintBuilder` accumulates row/column/value triples and emits a
`scipy.sparse.csr_matrix` at the end. Memory and solve time both drop
sharply versus dense assembly.

The class also enforces the *sign-safe* row pattern documented in the
skill body: when adding a row, supply the variable-index, coefficient
pairs explicitly with the bounds as separate `lo` / `hi` arguments. The
caller writes the inequality in its natural form on scratch paper, moves
all variable terms to the left-hand side, then encodes the LHS as
`terms` and the RHS as `lo`/`hi`. This eliminates the entire class of
"is `<=` or `>=`?" sign errors.

Special bounds:

* `lo=-INF, hi=value` — upper-bound row (`Ax <= value`).
* `lo=value, hi=+INF` — lower-bound row (`Ax >= value`).
* `lo=value, hi=value` — equality (`Ax == value`).
* `lo=hi=0.0` — equality at zero, the natural form after moving terms.

A row label (`family`) is attached to every row so debugging output can
group violations by constraint family (balance, capacity, ramp, reserve,
min up/down, transition). After solve, the per-row labels make it
trivial to compute "largest violation per family" — the single most
useful diagnostic when a model returns infeasible or visibly wrong.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable

import numpy as np

INF = math.inf


@dataclass
class ConstraintBuilder:
    """Accumulate sparse constraint rows in (row, col, val) form.

    Attributes
    ----------
    rows, cols, vals
        Parallel lists building up the sparse matrix in COO form.
    lb, ub
        Per-row lower and upper bounds. Use `-INF` and `+INF` for
        one-sided rows.
    families
        Per-row label (e.g. "balance", "capacity", "ramp") for
        debugging. Aligned 1:1 with `lb`/`ub`.
    n_rows
        Current row count.
    """

    rows: list[int] = field(default_factory=list)
    cols: list[int] = field(default_factory=list)
    vals: list[float] = field(default_factory=list)
    lb: list[float] = field(default_factory=list)
    ub: list[float] = field(default_factory=list)
    families: list[str] = field(default_factory=list)
    n_rows: int = 0

    def add_row(
        self,
        terms: Iterable[tuple[int, float]],
        lo: float,
        hi: float,
        family: str = "",
    ) -> int:
        """Add a single row `lo <= sum(a_j * x_j) <= hi`.

        Parameters
        ----------
        terms
            Iterable of `(variable_index, coefficient)` tuples. Terms
            with coefficient 0 are dropped silently — keeping zeros
            wastes memory and confuses debugging.
        lo, hi
            Row bounds. Use `-INF` / `+INF` for one-sided rows. Use
            equal `lo` and `hi` for equality rows.
        family
            Optional label for grouping in diagnostics.

        Returns
        -------
        The new row index.
        """
        if lo > hi:
            raise ValueError(f"add_row: lo={lo} > hi={hi} for family={family!r}")
        row = self.n_rows
        added = False
        for j, a in terms:
            if a == 0.0:
                continue
            self.rows.append(row)
            self.cols.append(int(j))
            self.vals.append(float(a))
            added = True
        if not added:
            # A bound-only row with no LHS terms means 0 must lie in [lo, hi].
            # Allow it (sometimes useful as a sanity check) but record nothing
            # in the matrix — scipy will treat the row as `0 <= 0`.
            pass
        self.lb.append(float(lo))
        self.ub.append(float(hi))
        self.families.append(family)
        self.n_rows += 1
        return row

    def add_rows_vectorized(
        self,
        idx_arrays: dict[str, np.ndarray],
        coefs: dict[str, float | np.ndarray],
        lo: float | np.ndarray,
        hi: float | np.ndarray,
        family: str = "",
    ) -> tuple[int, int]:
        """Add many rows in one call when the structure is regular.

        Use when a constraint family is "for every `(g, t)`, do X". Pass
        same-shaped index arrays in `idx_arrays` (e.g. `dispatch[g, t]`,
        `u[g, t]`) and matching scalar or same-shaped coefficient arrays
        in `coefs`. The arrays are flattened in C order; each flattened
        position becomes one row.

        Returns the half-open row range `[first, last)` covering the
        rows added.
        """
        shapes = {k: np.asarray(v).shape for k, v in idx_arrays.items()}
        if len({s for s in shapes.values()}) != 1:
            raise ValueError(f"add_rows_vectorized: inconsistent shapes {shapes}")
        shape = next(iter(shapes.values()))
        size = int(np.prod(shape))
        flat_idx = {k: np.asarray(v, dtype=int).ravel() for k, v in idx_arrays.items()}
        flat_coef: dict[str, np.ndarray] = {}
        for k, c in coefs.items():
            arr = np.asarray(c, dtype=float)
            if arr.ndim == 0:
                flat_coef[k] = np.full(size, float(arr))
            else:
                if arr.shape != shape:
                    raise ValueError(
                        f"coef {k!r} expects shape {shape}, got {arr.shape}"
                    )
                flat_coef[k] = arr.ravel()
        lo_arr = np.full(size, float(lo)) if np.ndim(lo) == 0 else np.asarray(lo, dtype=float).ravel()
        hi_arr = np.full(size, float(hi)) if np.ndim(hi) == 0 else np.asarray(hi, dtype=float).ravel()
        first = self.n_rows
        for i in range(size):
            terms = [(int(flat_idx[k][i]), float(flat_coef[k][i])) for k in idx_arrays]
            self.add_row(terms, lo=lo_arr[i], hi=hi_arr[i], family=family)
        return first, self.n_rows

    def to_scipy(self, n_vars: int):
        """Return `(A_csr, lb_array, ub_array, families_array)`.

        `A_csr` is a `scipy.sparse.csr_matrix`. Hand it to
        `LinearConstraint(A_csr, lb_array, ub_array)`.
        """
        from scipy.sparse import csr_matrix  # local import keeps top-level light

        a = csr_matrix(
            (self.vals, (self.rows, self.cols)),
            shape=(self.n_rows, n_vars),
        )
        return (
            a,
            np.asarray(self.lb, dtype=float),
            np.asarray(self.ub, dtype=float),
            np.asarray(self.families, dtype=object),
        )

    def family_summary(self) -> dict[str, int]:
        """Return `{family: row_count}` for debugging.

        Lets the caller print "balance: 24 rows, capacity: 96 rows, ..."
        to spot a missing family before the solver runs.
        """
        counts: dict[str, int] = {}
        for fam in self.families:
            counts[fam] = counts.get(fam, 0) + 1
        return counts


def largest_violations(
    A,
    lb: np.ndarray,
    ub: np.ndarray,
    families: np.ndarray,
    x: np.ndarray,
    top_k: int = 5,
) -> dict[str, list[dict]]:
    """Per-family worst-violation diagnostic.

    Given the constraint matrix, bounds, family labels, and a candidate
    `x`, compute `A @ x` and report the top-`k` row violations per
    family. A row is violated by `max(lb - val, val - ub, 0)`. Use this
    when the solver returns infeasible or after a repair LP to confirm
    no family was silently dropped.

    Returns `{family: [{"row", "value", "lb", "ub", "violation"}, ...]}`.
    """
    Ax = np.asarray(A @ x).ravel()
    lo_vio = lb - Ax
    hi_vio = Ax - ub
    vio = np.maximum(np.maximum(lo_vio, hi_vio), 0.0)
    out: dict[str, list[dict]] = {}
    for fam in sorted(set(families.tolist())):
        mask = families == fam
        if not mask.any():
            continue
        rows = np.where(mask)[0]
        order = rows[np.argsort(-vio[rows])]
        out[fam] = [
            {
                "row": int(r),
                "value": float(Ax[r]),
                "lb": float(lb[r]),
                "ub": float(ub[r]),
                "violation": float(vio[r]),
            }
            for r in order[:top_k]
        ]
    return out

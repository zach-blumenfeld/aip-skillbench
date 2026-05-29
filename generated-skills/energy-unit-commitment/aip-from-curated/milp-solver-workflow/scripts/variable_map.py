"""Deterministic variable allocator for a flat MILP variable vector.

A MILP solved through `scipy.optimize.milp` consumes a single flat vector
`x` of length `n`. For time-expanded scheduling models (unit commitment,
lot-sizing, network flow), `n` is dominated by structured blocks shaped
like `(resource, period)` or `(resource, period, segment)`. Hand-rolled
index arithmetic over those blocks is the #1 source of silent indexing
bugs — off-by-one in `t`, wrong axis when reshaping, two variables sharing
an index after a refactor.

`VariableMap` solves this by being the single place where indices are
allocated. Every block has a name, a shape, lower and upper bounds, and
an integrality flag. The map records the start offset and reshapes the
contiguous index range into the requested shape, so callers index it as
`vm["commitment"][g, t]` and never compute offsets themselves.

Invariants the helper enforces:

* No two `alloc()` calls share indices — the next block starts at
  `self.n`.
* `lb`, `ub`, and `integrality` are aligned 1-D arrays of length `n` so
  they can be handed directly to `scipy.optimize.milp` via `Bounds(lb, ub)`
  and `integrality=integrality`.
* Integrality is encoded as scipy's per-variable flag: `0` continuous,
  `1` integer (binary if `lb=0, ub=1`).
* Bounds default to `[0, +inf)` — the unit-commitment default for
  dispatch, reserve, slack. Pass `ub=1.0` and `integer=True` for binaries
  (commitment, startup, shutdown).

Use the `report_layout()` helper after solving to convert the flat
incumbent into a `{name: ndarray}` dict shaped like the original
allocations — this is the natural input for `validate_solution.py`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

import numpy as np


@dataclass
class VariableMap:
    """Allocate named, shaped blocks of decision variables.

    Attributes
    ----------
    n
        Total variable count after all `alloc()` calls.
    offset
        `{name: ndarray}` mapping each block name to its index array
        reshaped to the requested shape.
    lb, ub
        Length-`n` 1-D arrays of lower/upper bounds. Hand to
        `scipy.optimize.Bounds(lb, ub)`.
    integrality
        Length-`n` 1-D integer array. `0` continuous, `1` integer. Hand
        directly to `scipy.optimize.milp(..., integrality=...)`.
    """

    n: int = 0
    offset: dict[str, np.ndarray] = field(default_factory=dict)
    _lb: list[float] = field(default_factory=list)
    _ub: list[float] = field(default_factory=list)
    _integrality: list[int] = field(default_factory=list)

    def alloc(
        self,
        name: str,
        shape: Iterable[int] | int,
        lb: float = 0.0,
        ub: float = float("inf"),
        integer: bool = False,
    ) -> np.ndarray:
        """Allocate a block of variables.

        Parameters
        ----------
        name
            Unique block name. Reused names raise ValueError.
        shape
            Tuple of integer dimensions, or a single int for a 1-D block.
        lb, ub
            Bounds applied to every variable in the block.
        integer
            True for integer/binary variables. Binaries use
            `lb=0, ub=1, integer=True`.

        Returns
        -------
        ndarray of int
            Index array shaped like `shape`. Use the indices to refer to
            specific variables when adding constraint rows or building
            the cost vector.
        """
        if name in self.offset:
            raise ValueError(f"variable block already allocated: {name!r}")
        shape_tuple = (int(shape),) if isinstance(shape, int) else tuple(int(d) for d in shape)
        size = 1
        for d in shape_tuple:
            size *= d
        if size == 0:
            raise ValueError(f"block {name!r} has zero size from shape {shape_tuple}")
        idx = np.arange(self.n, self.n + size).reshape(shape_tuple)
        self.offset[name] = idx
        self._lb.extend([float(lb)] * size)
        self._ub.extend([float(ub)] * size)
        self._integrality.extend([1 if integer else 0] * size)
        self.n += size
        return idx

    def __getitem__(self, name: str) -> np.ndarray:
        return self.offset[name]

    def __contains__(self, name: str) -> bool:
        return name in self.offset

    @property
    def lb(self) -> np.ndarray:
        return np.asarray(self._lb, dtype=float)

    @property
    def ub(self) -> np.ndarray:
        return np.asarray(self._ub, dtype=float)

    @property
    def integrality(self) -> np.ndarray:
        return np.asarray(self._integrality, dtype=int)

    def cost_vector(self, terms: dict[str, np.ndarray] | None = None) -> np.ndarray:
        """Build a length-`n` cost vector from per-block cost arrays.

        Pass a `{block_name: cost_array}` mapping where each cost array
        has the same shape the block was allocated with. Missing blocks
        cost zero. Use this instead of hand-indexing `c[g * T + t] = ...`.
        """
        c = np.zeros(self.n, dtype=float)
        if not terms:
            return c
        for name, arr in terms.items():
            if name not in self.offset:
                raise KeyError(f"cost_vector: unknown block {name!r}")
            idx = self.offset[name]
            arr_np = np.asarray(arr, dtype=float)
            if arr_np.shape != idx.shape:
                raise ValueError(
                    f"cost_vector: block {name!r} expects shape {idx.shape}, got {arr_np.shape}"
                )
            c[idx.ravel()] = arr_np.ravel()
        return c

    def report_layout(self, x: np.ndarray) -> dict[str, np.ndarray]:
        """Split a flat incumbent vector into `{block_name: ndarray}`.

        Each returned ndarray has the original allocation's shape. This
        is what `validate_solution.py` expects as input.
        """
        x_arr = np.asarray(x, dtype=float)
        if x_arr.shape != (self.n,):
            raise ValueError(f"expected incumbent of length {self.n}, got {x_arr.shape}")
        out: dict[str, np.ndarray] = {}
        for name, idx in self.offset.items():
            out[name] = x_arr[idx.ravel()].reshape(idx.shape)
        return out


def round_near_binary(values: np.ndarray, tol: float = 1e-6) -> np.ndarray:
    """Round values that are within `tol` of 0 or 1; raise otherwise.

    Use after solving to verify the solver's integer variables actually
    came back near-integral before treating them as discrete decisions.
    """
    arr = np.asarray(values, dtype=float)
    near_zero = np.abs(arr) <= tol
    near_one = np.abs(arr - 1.0) <= tol
    bad = ~(near_zero | near_one)
    if np.any(bad):
        worst = float(np.max(np.minimum(np.abs(arr[bad]), np.abs(arr[bad] - 1.0))))
        raise ValueError(
            f"{int(bad.sum())} binary values not near 0/1 (worst distance {worst:.3g})"
        )
    return np.where(near_one, 1.0, 0.0)


if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) != 2:
        print("usage: variable_map.py <spec.json>", file=sys.stderr)
        sys.exit(2)
    with open(sys.argv[1]) as f:
        spec = json.load(f)
    vm = VariableMap()
    for block in spec.get("blocks", []):
        vm.alloc(
            block["name"],
            block["shape"],
            lb=block.get("lb", 0.0),
            ub=block.get("ub", float("inf")),
            integer=bool(block.get("integer", False)),
        )
    print(json.dumps({"n": vm.n, "offsets": {k: v.tolist() for k, v in vm.offset.items()}}, indent=2))
    sys.exit(0)

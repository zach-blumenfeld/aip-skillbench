"""Confirm PySCIPOpt is importable before building an optimization model.

The curated SKILL.md is emphatic: do NOT start by installing another
solver. Verify pyscipopt is already available; if it is not, fail with a
clear error so the agent stops and re-plans instead of silently picking a
different solver.

Exit code is 0 when the import succeeds, non-zero otherwise. The
``ensure_pyscipopt`` helper is the in-process equivalent for scripts that
want to fail fast at the top of a model build.
"""

from __future__ import annotations

import sys


def ensure_pyscipopt():
    """Return ``(Model, quicksum)`` from pyscipopt or raise RuntimeError."""
    try:
        from pyscipopt import Model, quicksum
    except ImportError as exc:  # pragma: no cover - exercised by callers
        raise RuntimeError(
            "PySCIPOpt is required for this optimization approach"
        ) from exc
    return Model, quicksum


def main() -> int:
    try:
        ensure_pyscipopt()
    except RuntimeError as exc:
        print(f"NOT AVAILABLE: {exc}", file=sys.stderr)
        return 1
    print("pyscipopt: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())

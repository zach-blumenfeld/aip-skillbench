"""Probe that PySCIPOpt is importable before building a model.

Exit 0 and print the import line on success; exit 1 with a clear error on
failure so the calling step can surface the missing dependency rather than
silently fall back to a heuristic.
"""

from __future__ import annotations

import sys


def main() -> int:
    try:
        from pyscipopt import Model, quicksum  # noqa: F401
    except ImportError as exc:
        print(f"PySCIPOpt is not importable: {exc}", file=sys.stderr)
        return 1
    print("pyscipopt available: from pyscipopt import Model, quicksum")
    return 0


if __name__ == "__main__":
    sys.exit(main())

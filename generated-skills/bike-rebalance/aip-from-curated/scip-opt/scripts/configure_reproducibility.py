"""Apply SCIP reproducibility settings.

Fixed set of randomization / threading parameters that have to be applied with
graceful fallback (parameter names occasionally vary between SCIP versions).
The list of parameters and their values is deterministic, so it belongs in a
script rather than a prose checklist.

Usage from a modeling script:

    from configure_reproducibility import configure_reproducibility

    model = Model("my_model")
    configure_reproducibility(model, seed=0, threads=1)
"""

from __future__ import annotations

from typing import Any, Iterable


SEED_PARAMS: tuple[str, ...] = (
    "randomization/randomseedshift",
    "randomization/permutationseed",
    "randomization/lpseed",
)

PERMUTATION_FLAGS: tuple[str, ...] = (
    "randomization/permutevars",
    "randomization/permuteconss",
)

THREAD_PARAM = "parallel/maxnthreads"


def _set_if_available(model: Any, name: str, value: Any) -> bool:
    try:
        model.setParam(name, value)
    except Exception:
        return False
    return True


def configure_reproducibility(
    model: Any,
    seed: int = 0,
    threads: int = 1,
    extra_seed_params: Iterable[str] = (),
) -> list[str]:
    """Apply seed, permutation, and thread settings to ``model``.

    Returns the list of parameter names that were successfully applied so the
    caller can log what stuck.
    """
    applied: list[str] = []
    for name in (*SEED_PARAMS, *extra_seed_params):
        if _set_if_available(model, name, seed):
            applied.append(name)
    for name in PERMUTATION_FLAGS:
        if _set_if_available(model, name, False):
            applied.append(name)
    if _set_if_available(model, THREAD_PARAM, threads):
        applied.append(THREAD_PARAM)
    return applied


if __name__ == "__main__":
    import sys

    try:
        from pyscipopt import Model
    except ImportError as exc:
        print(f"PySCIPOpt is not importable: {exc}", file=sys.stderr)
        sys.exit(1)

    probe = Model("repro_probe")
    probe.hideOutput()
    applied = configure_reproducibility(probe)
    print(f"applied {len(applied)} reproducibility params: {applied}")

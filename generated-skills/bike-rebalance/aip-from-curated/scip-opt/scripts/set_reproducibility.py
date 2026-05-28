"""Pin SCIP randomization and threading so a run is repeatable.

The curated SKILL.md ships a fixed list of randomization parameters and a
``set_if_available`` helper that swallows ``setParam`` errors for params
the installed SCIP build does not expose. That list is reproduced here as
code so the agent does not have to retype it (and cannot drift the param
names).

Call ``set_reproducible(model)`` immediately after constructing the
``Model`` and before adding variables, so the seed-sensitive presolve and
branching steps see the pinned values.
"""

from __future__ import annotations


SEED_PARAMS = (
    "randomization/randomseedshift",
    "randomization/permutationseed",
    "randomization/lpseed",
)

PERMUTE_PARAMS = (
    "randomization/permutevars",
    "randomization/permuteconss",
)

SINGLE_THREAD_PARAM = "parallel/maxnthreads"


def set_if_available(model, name, value) -> bool:
    """Call ``model.setParam(name, value)``, swallowing unknown-param errors.

    Returns True when the param was set, False when this SCIP build does
    not expose it. SCIP versions vary in which randomization params are
    exposed; the curated source explicitly tolerates missing names rather
    than failing the run.
    """
    try:
        model.setParam(name, value)
        return True
    except Exception:
        return False


def set_reproducible(model, *, single_thread: bool = True) -> None:
    """Fix seeds and (optionally) force single-threaded solving."""
    for name in SEED_PARAMS:
        set_if_available(model, name, 0)
    for name in PERMUTE_PARAMS:
        set_if_available(model, name, False)
    if single_thread:
        set_if_available(model, SINGLE_THREAD_PARAM, 1)

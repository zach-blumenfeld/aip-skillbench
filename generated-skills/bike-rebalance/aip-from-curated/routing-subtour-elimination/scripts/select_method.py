"""Recommend a subtour-elimination method from problem characteristics.

Encodes the curated SKILL.md's method-choice table as a small function so
the agent does not have to re-derive the cutoff thresholds. Inputs are
structured problem features; output is one of:

  * "mtz"                       — Miller-Tucker-Zemlin
  * "single-commodity-flow"     — artificial connectivity flow
  * "static-dfj"                — full DFJ enumeration (tiny only)
  * "lazy-separation"           — iterative DFJ cut separation

Recommendations are heuristics from the curated source, not laws. The
returned `rationale` explains why so the agent can override on
solver-specific knowledge (e.g., callback availability) or task
constraints not captured here.
"""

from __future__ import annotations

from dataclasses import dataclass


STATIC_DFJ_HARD_CAP = 15           # curated: roughly 15-18 without filtering
SMALL_INSTANCE_MAX_STATIONS = 30   # MTZ is generally fine here
MEDIUM_INSTANCE_MAX_STATIONS = 60  # flow tends to outperform MTZ above this


@dataclass(frozen=True)
class MethodRecommendation:
    method: str
    rationale: str


def recommend_method(
    *,
    n_stations: int,
    n_vehicles: int = 1,
    optional_visits: bool = False,
    memory_tight: bool = False,
    debug_baseline: bool = False,
    weak_incumbents: bool = False,
) -> MethodRecommendation:
    """Pick a subtour-elimination method.

    Parameters
    ----------
    n_stations : Number of stations the model routes over.
    n_vehicles : Number of vehicles K (does not change the choice much
        but scales constraint count for static-dfj).
    optional_visits : True when some stations may legitimately be skipped.
        Single-commodity flow handles this naturally; MTZ needs care.
    memory_tight : True when the environment cannot afford the extra
        O(K n^2) continuous variables flow brings.
    debug_baseline : True when the caller wants the strongest static
        formulation for a small instance as a debugging baseline.
    weak_incumbents : True when MTZ was tried and produced weak bounds
        or slow MIP progress.

    Returns
    -------
    MethodRecommendation with `method` and a one-line `rationale`.
    """
    if n_stations <= 0:
        raise ValueError(f"n_stations must be positive, got {n_stations}")

    if debug_baseline and n_stations <= STATIC_DFJ_HARD_CAP:
        return MethodRecommendation(
            "static-dfj",
            (
                f"n={n_stations} <= {STATIC_DFJ_HARD_CAP}; "
                "static DFJ is the strongest static formulation and serves "
                "as a sanity baseline."
            ),
        )

    if n_stations > MEDIUM_INSTANCE_MAX_STATIONS:
        return MethodRecommendation(
            "lazy-separation",
            (
                f"n={n_stations} exceeds the comfort range for static "
                "formulations; iterative DFJ cut separation adds only the "
                "cuts the incumbent needs."
            ),
        )

    if weak_incumbents:
        return MethodRecommendation(
            "lazy-separation",
            (
                "MTZ already produced weak incumbents or slow progress; "
                "iterative DFJ separation typically tightens the formulation."
            ),
        )

    if optional_visits and not memory_tight:
        return MethodRecommendation(
            "single-commodity-flow",
            (
                "Optional station visits are present; single-commodity flow "
                "handles them cleanly without artificial order semantics."
            ),
        )

    if (
        n_stations <= MEDIUM_INSTANCE_MAX_STATIONS
        and not memory_tight
        and not optional_visits
    ):
        if n_stations <= SMALL_INSTANCE_MAX_STATIONS:
            return MethodRecommendation(
                "mtz",
                (
                    f"n={n_stations} is in the small-instance range; MTZ is "
                    "compact, easy to implement, and fast enough."
                ),
            )
        return MethodRecommendation(
            "single-commodity-flow",
            (
                f"n={n_stations} is in the medium range; flow-based "
                "connectivity tightens the LP relaxation versus MTZ at a "
                "modest memory cost."
            ),
        )

    return MethodRecommendation(
        "mtz",
        (
            "No stronger formulation is clearly indicated; MTZ is the "
            "compact default — correctness first, switch later if "
            "relaxation strength matters."
        ),
    )


def main() -> int:
    import argparse
    import json
    import sys

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n-stations", type=int, required=True)
    parser.add_argument("--n-vehicles", type=int, default=1)
    parser.add_argument("--optional-visits", action="store_true")
    parser.add_argument("--memory-tight", action="store_true")
    parser.add_argument("--debug-baseline", action="store_true")
    parser.add_argument("--weak-incumbents", action="store_true")
    args = parser.parse_args()

    rec = recommend_method(
        n_stations=args.n_stations,
        n_vehicles=args.n_vehicles,
        optional_visits=args.optional_visits,
        memory_tight=args.memory_tight,
        debug_baseline=args.debug_baseline,
        weak_incumbents=args.weak_incumbents,
    )
    json.dump({"method": rec.method, "rationale": rec.rationale}, sys.stdout)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

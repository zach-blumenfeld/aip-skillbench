# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///
"""Seismic event-detection / phase-picking method selection.

Encodes the workshop tradeoff matrix (STA/LTA, Manual, Deep Learning, Template
Matching) plus the viability and selection rules from the curated
`seismic-picker-selection` guide as a single structured source of truth, and
turns a project's constraints into a *ranked, explained* recommendation.

The ranking is decision support, not a mandate: it gates out non-viable methods
(hard rules stated in the guide) and scores the rest against the goal you weight.
Reason over the full ranking before committing.

Subcommands:
  show        Print the comparison matrix and per-method profiles.
  recommend   Rank methods for a goal + constraints (human table or --json).

Top-level:
  --self-test Run offline deterministic checks (stdlib only, no I/O).

Examples:
  python recommend_picker.py show
  python recommend_picker.py recommend --goal automatic-catalog --no-templates
  python recommend_picker.py recommend --requirements-json '{"goal":"max-sensitivity","have_templates":true}'
  python recommend_picker.py --self-test
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Dict, List, Optional

# --- Comparison matrix + method profiles (single source of truth) ------------
# Matrix levels are the qualitative ratings from the curated guide.
#   generalizability: ability to find arbitrary earthquake signals
#   sensitivity:      ability to find small earthquakes
#   speed_ease:       speed and ease of use / setup
#   false_positives:  rate of false detections (fewer is better)

METHODS: Dict[str, dict] = {
    "STA/LTA": {
        "generalizability": "High",
        "sensitivity": "Low",
        # sensitivity_score refines the coarse matrix label using the guide's prose
        # ordering of detector sensitivity: Template Matching is "optimally
        # sensitive (more than deep learning)"; STA/LTA is the least sensitive.
        "sensitivity_score": 0,
        "speed_ease": "Fast, Easy",
        "false_positives": "Many",
        "requires_templates": False,
        "requires_continuous_data": False,
        "real_time": True,
        "when_to_use": [
            "Fast, real-time amplitude-based detection of large earthquake signals.",
            "No prior knowledge of sources or waveforms is available.",
            "A quick, easy-to-implement first pass (tune window lengths and the ratio).",
        ],
        "advantages": [
            "Runs very fast; operates automatically in real-time.",
            "Easy to understand and implement; tunable window lengths and ratios.",
            "No prior knowledge needed about earthquake sources or waveforms.",
            "Amplitude-based detector: reliably detects large earthquake signals.",
        ],
        "limitations": [
            "High rate of false detections during active sequences.",
            "Automatic picks are not as precise.",
            "Requires manual review and refinement of picks for a quality catalog.",
        ],
    },
    "Manual": {
        "generalizability": "High",
        "sensitivity": "High",
        "sensitivity_score": 2,
        "speed_ease": "Slow, Difficult",
        "false_positives": "Few",
        "requires_templates": False,
        "requires_continuous_data": False,
        "real_time": False,
        "when_to_use": [
            "Highest-quality, most precise picks are needed and analyst time is available.",
            "A gold-standard reference catalog or careful review of automatic picks.",
        ],
        "advantages": [
            "High generalizability: can find arbitrary earthquake signals.",
            "High sensitivity to small earthquakes.",
            "Few false positives.",
        ],
        "limitations": [
            "Slow and difficult: labor-intensive expert review.",
            "Does not scale to large continuous datasets.",
        ],
    },
    "Deep Learning": {
        "generalizability": "High",
        "sensitivity": "High",
        "sensitivity_score": 2,
        "speed_ease": "Fast, Easy",
        "false_positives": "Medium",
        "requires_templates": False,
        "requires_continuous_data": True,
        "real_time": False,
        "when_to_use": [
            "Existing seismic networks are sparse or nonexistent (adds the most value here).",
            "Automatically and rapidly build a more complete catalog during active sequences.",
            "Temporary deployment of broadband or nodal stations wanting an automatic local catalog.",
            "Continuous seismic data is available; broadband best, but accelerometers, nodals, "
            "and Raspberry Shakes also produce usable picks.",
        ],
        "advantages": [
            "No prior knowledge needed about earthquake sources or waveforms.",
            "Finds many small local earthquakes (lower Mc) with fewer false detections than STA/LTA.",
            "Relatively easy to set up and run; reasonable runtime with parallel processing. "
            "SeisBench provides easy-to-use model APIs and pretrained models.",
        ],
        "limitations": [
            "Out-of-distribution data: larger automated pick errors (0.1-0.5 s) and missed picks.",
            "Cannot pick phases completely buried in noise; not quite as sensitive as template matching.",
            "Sometimes misses picks from larger earthquakes that are obvious to humans.",
        ],
    },
    "Template Matching": {
        "generalizability": "Low",
        "sensitivity": "High",
        # Optimally sensitive detector per the guide (more sensitive than deep
        # learning) -> scored strictly above the other "High" methods.
        "sensitivity_score": 3,
        "speed_ease": "Slow, Difficult",
        "false_positives": "Few",
        "requires_templates": True,
        "requires_continuous_data": False,
        "real_time": False,
        "when_to_use": [
            "Maximum sensitivity: find the smallest earthquakes buried in noise (most sensitive detector).",
            "Improving the temporal resolution of a known earthquake sequence.",
            "Template waveforms with good picks from a preexisting catalog are available.",
        ],
        "advantages": [
            "Optimally sensitive detector (more sensitive than deep learning) for events "
            "similar enough to a template waveform.",
            "Excellent for improving temporal resolution of earthquake sequences.",
            "False detections are not as concerning when using a high detection threshold.",
        ],
        "limitations": [
            "Requires prior knowledge: template waveforms with good picks from a preexisting catalog.",
            "Does not improve spatial resolution: sources not similar enough to templates cannot be found.",
            "Setup effort required: must extract template waveforms and configure processing.",
            "Computationally intensive.",
        ],
    },
}

DEFINITIONS = {
    "Generalizability": "Ability to find arbitrary earthquake signals.",
    "Sensitivity": "Ability to find small earthquakes.",
}

# Qualitative -> numeric maps used for scoring. Fewer false positives scores higher.
_LEVEL = {"High": 2, "Medium": 1, "Low": 0}
_SPEED = {"Fast, Easy": 2, "Medium": 1, "Slow, Difficult": 0}
_FALSE_POS = {"Few": 2, "Medium": 1, "Many": 0}

DIMENSIONS = ("generalizability", "sensitivity", "speed_ease", "low_false_positives")

# Goal presets weight the four dimensions (0-3). Reflect the guide's framing that
# purpose and resources should drive the choice.
GOAL_PRESETS: Dict[str, Dict[str, int]] = {
    "automatic-catalog": {
        "generalizability": 2, "sensitivity": 3, "speed_ease": 2, "low_false_positives": 2,
    },
    "real-time-monitoring": {
        "generalizability": 2, "sensitivity": 1, "speed_ease": 3, "low_false_positives": 1,
    },
    "max-sensitivity": {
        "generalizability": 1, "sensitivity": 3, "speed_ease": 0, "low_false_positives": 2,
    },
    "highest-precision": {
        "generalizability": 1, "sensitivity": 2, "speed_ease": 0, "low_false_positives": 3,
    },
    "balanced": {
        "generalizability": 1, "sensitivity": 1, "speed_ease": 1, "low_false_positives": 1,
    },
}
DEFAULT_GOAL = "automatic-catalog"


def _dim_scores(profile: dict) -> Dict[str, int]:
    return {
        "generalizability": _LEVEL[profile["generalizability"]],
        "sensitivity": profile["sensitivity_score"],
        "speed_ease": _SPEED[profile["speed_ease"]],
        "low_false_positives": _FALSE_POS[profile["false_positives"]],
    }


def _viability(name: str, profile: dict, constraints: dict) -> Optional[str]:
    """Return a disqualifying reason if the method is not viable, else None."""
    if profile["requires_templates"] and not constraints.get("have_templates", False):
        return ("Requires template waveforms with good picks from a preexisting "
                "catalog; none available.")
    if profile["requires_continuous_data"] and not constraints.get("continuous_data", True):
        return "Requires continuous seismic data, which is not available."
    return None


def _rationale(name: str, profile: dict, weights: Dict[str, int], constraints: dict) -> List[str]:
    dims = _dim_scores(profile)
    notes: List[str] = []
    label = {
        "generalizability": "generalizability",
        "sensitivity": "sensitivity",
        "speed_ease": "speed/ease of use",
        "low_false_positives": "low false-positive rate",
    }
    # Strengths: high-scoring dimensions the goal cares about.
    strengths = [label[d] for d in DIMENSIONS if weights.get(d, 0) >= 1 and dims[d] >= 2]
    weaknesses = [label[d] for d in DIMENSIONS if weights.get(d, 0) >= 1 and dims[d] == 0]
    if strengths:
        notes.append("Strong on " + ", ".join(strengths) + " (dimensions your goal weights).")
    if weaknesses:
        notes.append("Weak on " + ", ".join(weaknesses) + " (dimensions your goal weights).")
    # Contextual notes from the guide.
    if name == "Deep Learning" and constraints.get("sparse_network"):
        notes.append("Adds the most value when networks are sparse or nonexistent.")
    if name == "Template Matching" and constraints.get("find_novel_sources"):
        notes.append("Low generalizability: cannot find sources dissimilar to your templates "
                     "(no spatial-resolution improvement).")
    if name == "STA/LTA" and constraints.get("active_sequence"):
        notes.append("Expect a high false-detection rate during active sequences; plan for manual review.")
    return notes


def resolve_weights(goal: str, overrides: Dict[str, Optional[int]]) -> Dict[str, int]:
    if goal not in GOAL_PRESETS:
        raise ValueError(
            "Unknown goal %r. Choose one of: %s" % (goal, ", ".join(sorted(GOAL_PRESETS)))
        )
    weights = dict(GOAL_PRESETS[goal])
    for dim, val in overrides.items():
        if val is not None:
            if dim not in weights:
                raise ValueError("Unknown weight dimension %r" % dim)
            weights[dim] = val
    return weights


def recommend(constraints: dict) -> dict:
    """Rank methods. `constraints` keys (all optional):
    goal, have_templates, continuous_data, sparse_network, find_novel_sources,
    active_sequence, and weight_* overrides.
    """
    goal = constraints.get("goal", DEFAULT_GOAL)
    overrides = {d: constraints.get("weight_" + d) for d in DIMENSIONS}
    weights = resolve_weights(goal, overrides)

    ranking: List[dict] = []
    for name, profile in METHODS.items():
        dims = _dim_scores(profile)
        score = sum(weights[d] * dims[d] for d in DIMENSIONS)
        disq = _viability(name, profile, constraints)
        ranking.append({
            "method": name,
            "score": score,
            "viable": disq is None,
            "disqualified_reason": disq,
            "matrix": {
                "generalizability": profile["generalizability"],
                "sensitivity": profile["sensitivity"],
                "speed_ease": profile["speed_ease"],
                "false_positives": profile["false_positives"],
            },
            "rationale": ([disq] if disq else _rationale(name, profile, weights, constraints)),
            "watch_outs": profile["limitations"],
        })

    # Viable methods first, then by score (desc), then by name for stable ties.
    ranking.sort(key=lambda r: (not r["viable"], -r["score"], r["method"]))
    recommended = None
    for r in ranking:
        r["recommended"] = False
    for r in ranking:
        if r["viable"]:
            r["recommended"] = True
            recommended = r["method"]
            break

    return {
        "goal": goal,
        "weights": weights,
        "constraints": {k: v for k, v in constraints.items()
                        if not k.startswith("weight_") and k != "goal"},
        "recommended": recommended,
        "ranking": ranking,
    }


# --- CLI ---------------------------------------------------------------------

def _print_show() -> None:
    print("Seismic event-detection & phase-picking method comparison\n")
    header = ("Method", "Generalizability", "Sensitivity", "Speed/Ease", "False Positives")
    rows = [(n, p["generalizability"], p["sensitivity"], p["speed_ease"], p["false_positives"])
            for n, p in METHODS.items()]
    widths = [max(len(str(r[i])) for r in [header] + rows) for i in range(len(header))]
    fmt = "  ".join("{:<%d}" % w for w in widths)
    print(fmt.format(*header))
    print(fmt.format(*["-" * w for w in widths]))
    for r in rows:
        print(fmt.format(*r))
    print("\nDefinitions:")
    for k, v in DEFINITIONS.items():
        print("  - %s: %s" % (k, v))
    print("\nKey insight: each method has strengths and weaknesses; purpose and "
          "resources should guide your choice.\n")
    for name, p in METHODS.items():
        print("== %s ==" % name)
        print("  When to use:")
        for x in p["when_to_use"]:
            print("    - " + x)
        print("  Advantages:")
        for x in p["advantages"]:
            print("    - " + x)
        print("  Limitations:")
        for x in p["limitations"]:
            print("    - " + x)
        print()


def _print_recommendation(result: dict) -> None:
    print("Goal: %s    Recommended: %s" % (result["goal"], result["recommended"]))
    print("Weights: " + ", ".join("%s=%d" % (k, v) for k, v in result["weights"].items()))
    print()
    for i, r in enumerate(result["ranking"], 1):
        tag = "  [RECOMMENDED]" if r["recommended"] else ("  [not viable]" if not r["viable"] else "")
        print("%d. %s  (score %d)%s" % (i, r["method"], r["score"], tag))
        for note in r["rationale"]:
            print("     - " + note)
    rec = next((r for r in result["ranking"] if r["recommended"]), None)
    if rec:
        print("\nWatch-outs for %s:" % rec["method"])
        for w in rec["watch_outs"]:
            print("  - " + w)


def _add_recommend_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--goal", default=None,
                   help="Goal preset: " + ", ".join(sorted(GOAL_PRESETS)) +
                        " (default: %s)" % DEFAULT_GOAL)
    p.add_argument("--have-templates", dest="have_templates", action="store_true", default=None,
                   help="Template waveforms from a preexisting catalog are available.")
    p.add_argument("--no-templates", dest="have_templates", action="store_false",
                   help="No preexisting catalog / template waveforms available (default assumption).")
    p.add_argument("--continuous-data", dest="continuous_data", action="store_true", default=None,
                   help="Continuous seismic data is available (default assumption).")
    p.add_argument("--no-continuous-data", dest="continuous_data", action="store_false",
                   help="Continuous seismic data is NOT available.")
    p.add_argument("--sparse-network", action="store_true",
                   help="Existing seismic network is sparse or nonexistent (favors deep learning).")
    p.add_argument("--find-novel-sources", action="store_true",
                   help="Need to find previously-unknown / arbitrary earthquake sources.")
    p.add_argument("--active-sequence", action="store_true",
                   help="Processing an active aftershock/swarm sequence (STA/LTA false detections rise).")
    for dim in DIMENSIONS:
        p.add_argument("--weight-" + dim.replace("_", "-"), type=int, default=None,
                       help="Override goal weight for %s (0-3)." % dim)
    p.add_argument("--requirements-json", default=None,
                   help="JSON object of constraints; merged under explicit flags.")
    p.add_argument("--json", action="store_true", help="Emit JSON instead of a table.")


def _constraints_from_args(args: argparse.Namespace) -> dict:
    constraints: dict = {}
    if args.requirements_json:
        loaded = json.loads(args.requirements_json)
        if not isinstance(loaded, dict):
            raise ValueError("--requirements-json must be a JSON object")
        constraints.update(loaded)
    # Explicit flags override the JSON blob.
    if args.goal is not None:
        constraints["goal"] = args.goal
    if args.have_templates is not None:
        constraints["have_templates"] = args.have_templates
    if args.continuous_data is not None:
        constraints["continuous_data"] = args.continuous_data
    if args.sparse_network:
        constraints["sparse_network"] = True
    if args.find_novel_sources:
        constraints["find_novel_sources"] = True
    if args.active_sequence:
        constraints["active_sequence"] = True
    for dim in DIMENSIONS:
        val = getattr(args, "weight_" + dim)
        if val is not None:
            constraints["weight_" + dim] = val
    constraints.setdefault("goal", DEFAULT_GOAL)
    return constraints


def _self_test() -> int:
    failures: List[str] = []

    def check(cond: bool, msg: str) -> None:
        if not cond:
            failures.append(msg)

    # Matrix integrity: every level maps cleanly.
    for name, p in METHODS.items():
        check(p["generalizability"] in _LEVEL, "%s bad generalizability" % name)
        check(p["sensitivity"] in _LEVEL, "%s bad sensitivity" % name)
        check(p["speed_ease"] in _SPEED, "%s bad speed_ease" % name)
        check(p["false_positives"] in _FALSE_POS, "%s bad false_positives" % name)

    # Template Matching is not viable without templates, regardless of goal.
    r = recommend({"goal": "max-sensitivity", "have_templates": False})
    tm = next(x for x in r["ranking"] if x["method"] == "Template Matching")
    check(not tm["viable"], "Template Matching should be non-viable without templates")
    check(r["recommended"] != "Template Matching",
          "Template Matching must not be recommended without templates")

    # With templates and a max-sensitivity goal, Template Matching becomes viable
    # and should rank at the top (optimally sensitive detector).
    r2 = recommend({"goal": "max-sensitivity", "have_templates": True})
    check(r2["recommended"] == "Template Matching",
          "max-sensitivity + templates should recommend Template Matching, got %s" % r2["recommended"])

    # The task default: automatic catalog, no preexisting catalog, continuous data
    # available -> Deep Learning.
    r3 = recommend({"goal": "automatic-catalog", "have_templates": False, "continuous_data": True})
    check(r3["recommended"] == "Deep Learning",
          "automatic-catalog default should recommend Deep Learning, got %s" % r3["recommended"])

    # Deep Learning is not viable without continuous data.
    r4 = recommend({"goal": "automatic-catalog", "continuous_data": False})
    dl = next(x for x in r4["ranking"] if x["method"] == "Deep Learning")
    check(not dl["viable"], "Deep Learning should be non-viable without continuous data")

    # Real-time monitoring favors fast methods (STA/LTA or Deep Learning at top).
    r5 = recommend({"goal": "real-time-monitoring", "have_templates": False})
    check(r5["recommended"] in ("STA/LTA", "Deep Learning"),
          "real-time-monitoring should recommend a fast method, got %s" % r5["recommended"])

    # Ranking is always a full permutation of the four methods.
    check(sorted(x["method"] for x in r["ranking"]) == sorted(METHODS),
          "ranking must cover all methods exactly once")

    if failures:
        for f in failures:
            print("FAIL: " + f, file=sys.stderr)
        print("self-test: %d failure(s)" % len(failures))
        return 1
    print("self-test: OK (%d methods)" % len(METHODS))
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Seismic picker/detector method selection.")
    parser.add_argument("--self-test", action="store_true",
                        help="Run offline deterministic checks and exit.")
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("show", help="Print the comparison matrix and method profiles.")
    rec = sub.add_parser("recommend", help="Rank methods for a goal and constraints.")
    _add_recommend_args(rec)

    args = parser.parse_args(argv)

    if args.self_test:
        return _self_test()
    if args.cmd == "show":
        _print_show()
        return 0
    if args.cmd == "recommend":
        constraints = _constraints_from_args(args)
        result = recommend(constraints)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            _print_recommendation(result)
        return 0
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""PID tuning advisor.

Two modes:
  --procedure                  print the canonical manual-tuning order
  --symptom NAME               print the gain to adjust for an observed symptom

Symptoms are the closed-loop behaviors a tuner watches for. The table
captures the standard heuristic effects of each gain — see SKILL.md.
"""

import argparse
import json
import sys

SYMPTOM_TABLE = {
    "slow-response": {
        "adjust": "kp",
        "direction": "increase",
        "reason": "Higher Kp gives a faster response to current error.",
    },
    "sluggish-tracking": {
        "adjust": "kp",
        "direction": "increase",
        "reason": "Proportional term drives response speed; raise until stable.",
    },
    "steady-state-error": {
        "adjust": "ki",
        "direction": "increase",
        "reason": "Integral term accumulates residual error and removes it.",
    },
    "overshoot": {
        "adjust": "kd",
        "direction": "increase",
        "reason": "Derivative term damps the rate of change and reduces overshoot.",
    },
    "oscillation": {
        "adjust": "ki",
        "direction": "decrease",
        "reason": "Excess integral gain commonly drives sustained oscillation.",
    },
    "noise-amplification": {
        "adjust": "kd",
        "direction": "decrease",
        "reason": "Derivative on a raw noisy signal amplifies measurement noise.",
    },
    "windup": {
        "adjust": "ki",
        "direction": "anti-windup",
        "reason": "Output saturation with integration causes windup; gate the integral instead of just lowering Ki.",
    },
}

PROCEDURE = [
    "1. Set Ki = Kd = 0.",
    "2. Increase Kp until the response is fast enough but stable.",
    "3. Add Ki to eliminate steady-state error.",
    "4. Add Kd to reduce overshoot.",
]

GAIN_EFFECTS = {
    "kp": "Higher Kp -> faster response, more overshoot.",
    "ki": "Higher Ki -> removes steady-state error, can cause oscillation.",
    "kd": "Higher Kd -> reduces overshoot, sensitive to measurement noise.",
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--symptom",
        choices=sorted(SYMPTOM_TABLE),
        help="Observed closed-loop symptom; prints which gain to adjust.",
    )
    parser.add_argument(
        "--procedure",
        action="store_true",
        help="Print the canonical manual-tuning order.",
    )
    parser.add_argument(
        "--effects",
        action="store_true",
        help="Print the effect of each gain.",
    )
    args = parser.parse_args()

    if not (args.symptom or args.procedure or args.effects):
        parser.error("pass --symptom NAME, --procedure, and/or --effects")

    payload: dict = {}
    if args.procedure:
        payload["procedure"] = PROCEDURE
    if args.effects:
        payload["gain_effects"] = GAIN_EFFECTS
    if args.symptom:
        payload["advice"] = SYMPTOM_TABLE[args.symptom]

    json.dump(payload, sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()

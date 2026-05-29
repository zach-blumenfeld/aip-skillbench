"""Choose a startup tier from a unit's tier table and a prior offline duration.

A startup tier is `{"lag": int, "cost": float, ...}`: the cost the unit
incurs when restarted after being offline for at least `lag` periods.
The rule: pick the tier whose `lag` is the LARGEST not exceeding the
prior offline duration. If every tier's `lag` exceeds the duration
(rare; the bottom tier is normally 0 or 1), fall back to the
smallest-`lag` tier so the function always returns something. The full
tier dict is returned so callers can read auxiliary fields (e.g.,
`fuel`, `emissions`) the source data may attach beyond `lag`/`cost`.

The source tier list may arrive in any order; this helper sorts it
defensively.
"""

from __future__ import annotations

from typing import Iterable


def choose_startup_tier(
    tiers: Iterable[dict],
    prior_offline_duration: int,
) -> dict:
    """Return the tier dict whose `lag` is the largest <= prior_offline_duration.

    Raises ValueError if `tiers` is empty.
    """
    sorted_tiers = sorted(tiers, key=lambda t: int(t["lag"]))
    if not sorted_tiers:
        raise ValueError("no startup tiers supplied")
    chosen = sorted_tiers[0]
    for tier in sorted_tiers:
        if int(tier["lag"]) <= int(prior_offline_duration):
            chosen = tier
        else:
            break
    return dict(chosen)


if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) != 2:
        print("usage: startup_tier.py <input.json>", file=sys.stderr)
        sys.exit(2)
    with open(sys.argv[1]) as f:
        payload = json.load(f)
    if "tiers" not in payload or "prior_offline_duration" not in payload:
        print("input.json must contain 'tiers' and 'prior_offline_duration'", file=sys.stderr)
        sys.exit(2)
    tier = choose_startup_tier(payload["tiers"], int(payload["prior_offline_duration"]))
    print(json.dumps({"chosen_tier": tier}, indent=2))
    sys.exit(0)

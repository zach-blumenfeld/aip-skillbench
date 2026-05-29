"""Tier-based startup-cost lookup and offline-duration tracking.

A startup tier is a `{"lag": int, "cost": float}` pair: "if the unit has been
offline at least `lag` periods, the startup costs at least `cost`". The
applied tier is the one with the LARGEST `lag` not exceeding the offline
duration immediately before the startup period. The smallest lag (often 0)
is the fallback when offline_duration is below every tier threshold.

`offline_duration_before` tracks the trailing offline run for each unit
across the horizon, starting from the unit's pre-horizon initial state.
The duration reported for period t is the number of consecutive periods
the unit was offline JUST BEFORE t — that is the value the tier rule
applies to.
"""

from __future__ import annotations

from typing import Iterable


def choose_startup_cost(
    tiers: Iterable[dict],
    offline_duration: int,
) -> float:
    """Return the startup cost for a unit that was offline `offline_duration`
    periods before the startup.

    The largest lag not exceeding offline_duration wins. If the smallest
    lag still exceeds offline_duration (rare; the bottom tier is usually 0
    or 1), the smallest-lag tier is returned anyway as a fallback so the
    function always returns a number.
    """
    sorted_tiers = sorted(tiers, key=lambda z: z["lag"])
    if not sorted_tiers:
        raise ValueError("no startup tiers supplied")
    chosen = sorted_tiers[0]
    for tier in sorted_tiers:
        if tier["lag"] <= offline_duration:
            chosen = tier
        else:
            break
    return float(chosen["cost"])


def offline_durations(
    u: list[int],
    initial_on: int,
    initial_off_duration: int,
) -> list[int]:
    """Return a list of length len(u) giving the offline-duration BEFORE
    each period.

    `initial_on` is the pre-horizon commitment (0 or 1). `initial_off_duration`
    is the number of periods the unit has been continuously offline up to
    and including t = -1 (zero when the unit was online at t = -1).
    """
    durations: list[int] = []
    if initial_on == 1:
        running = 0
    else:
        running = int(initial_off_duration)
    for t in range(len(u)):
        durations.append(running)
        if int(u[t]) == 0:
            running += 1
        else:
            running = 0
    return durations


def schedule_startup_cost(
    u: list[int],
    start: list[int],
    tiers: Iterable[dict],
    initial_on: int,
    initial_off_duration: int,
) -> float:
    """Sum the startup cost over a unit's schedule.

    A startup at period t costs `choose_startup_cost(tiers, offline_before[t])`.
    """
    tiers = list(tiers)
    durations = offline_durations(u, initial_on, initial_off_duration)
    total = 0.0
    for t, s in enumerate(start):
        if int(s) == 1:
            total += choose_startup_cost(tiers, durations[t])
    return total


if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) != 2:
        print("usage: startup_cost.py <input.json>", file=sys.stderr)
        sys.exit(2)
    with open(sys.argv[1]) as f:
        payload = json.load(f)

    if "offline_duration" in payload and "tiers" in payload:
        cost = choose_startup_cost(payload["tiers"], int(payload["offline_duration"]))
        print(json.dumps({"startup_cost": cost}, indent=2))
        sys.exit(0)
    if all(k in payload for k in ("u", "start", "tiers", "initial_on", "initial_off_duration")):
        cost = schedule_startup_cost(
            payload["u"],
            payload["start"],
            payload["tiers"],
            int(payload["initial_on"]),
            int(payload["initial_off_duration"]),
        )
        print(json.dumps({"total_startup_cost": cost}, indent=2))
        sys.exit(0)
    print("input.json missing required keys", file=sys.stderr)
    sys.exit(2)

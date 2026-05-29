"""Deterministic helpers for parsing unit commitment input data.

Pure functions — no I/O, no globals. Import from your parser code:

    from uc_data_helpers import (
        choose_startup_tier,
        interpolate_total_cost,
        actual_from_above_min,
        above_min_from_actual,
    )

Functions are independent and can be used in any order. They make no
assumption about which package or benchmark the source data came from;
they expect already-parsed Python primitives.
"""

from __future__ import annotations

from typing import Iterable, Mapping, Sequence


def choose_startup_tier(
    tiers: Iterable[Mapping[str, float]],
    prior_offline_duration: float,
) -> Mapping[str, float]:
    """Pick the startup tier matching `prior_offline_duration`.

    Tiers are sorted by `lag` ascending; the chosen tier is the latest
    whose `lag <= prior_offline_duration`. If `prior_offline_duration`
    is below every tier's `lag`, the smallest-lag tier is returned.

    Each tier is a mapping with at least the key `lag`; additional keys
    such as `cost` pass through unchanged.

    Raises ValueError if `tiers` is empty.
    """
    sorted_tiers = sorted(tiers, key=lambda t: t["lag"])
    if not sorted_tiers:
        raise ValueError("startup tiers list is empty")
    chosen = sorted_tiers[0]
    for tier in sorted_tiers:
        if tier["lag"] <= prior_offline_duration:
            chosen = tier
        else:
            break
    return chosen


def interpolate_total_cost(
    points: Iterable[Mapping[str, float]],
    output_mw: float,
) -> float:
    """Piecewise-linear interpolation of a total-cost curve.

    `points` is an iterable of mappings with `mw` and `cost` keys. The
    curve is sorted by `mw` before evaluation; out-of-range queries
    clamp to the nearest endpoint (no extrapolation). Use only when the
    source data represents *total* cost at each breakpoint — if the
    source gives marginal or incremental-segment cost, convert before
    calling.

    Raises ValueError if the resolved output falls in no segment (the
    sorted curve had fewer than two distinct points).
    """
    pts = sorted((float(p["mw"]), float(p["cost"])) for p in points)
    if not pts:
        raise ValueError("cost curve has no points")
    if output_mw <= pts[0][0]:
        return pts[0][1]
    if output_mw >= pts[-1][0]:
        return pts[-1][1]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x0 <= output_mw <= x1:
            if x1 == x0:
                return y0
            a = (output_mw - x0) / (x1 - x0)
            return y0 + a * (y1 - y0)
    raise ValueError("output_mw outside cost curve")


def actual_from_above_min(
    pmin: float,
    commitment: int,
    output_above_min: float,
) -> float:
    """Actual MW from the output-above-minimum internal convention.

    `commitment` is 0 (offline) or 1 (online). When offline, actual
    output is 0 by convention.
    """
    return pmin * commitment + output_above_min


def above_min_from_actual(
    pmin: float,
    commitment: int,
    actual_output: float,
) -> float:
    """Output above minimum from the actual-MW convention."""
    return actual_output - pmin * commitment

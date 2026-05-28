"""Hex grid utilities for Civ6 odd-r offset coordinates.

If a scenario uses a different convention (even-r, odd-q, even-q),
re-run verify_neighbors() against known-adjacent tile pairs from the
map data and swap the rule.
"""
from __future__ import annotations


def hex_neighbors(x, y, width=None, wrap_x=False):
    """Return the 6 neighbors of (x, y) in odd-r offset coordinates."""
    if y % 2 == 0:
        cand = [(x - 1, y), (x + 1, y),
                (x - 1, y + 1), (x, y + 1),
                (x - 1, y - 1), (x, y - 1)]
    else:
        cand = [(x - 1, y), (x + 1, y),
                (x, y + 1), (x + 1, y + 1),
                (x, y - 1), (x + 1, y - 1)]
    if wrap_x and width:
        cand = [(nx % width, ny) for nx, ny in cand]
    return cand


def offset_to_axial(x, y):
    """odd-r offset to axial."""
    q = x - (y - (y & 1)) // 2
    r = y
    return q, r


def hex_distance(a, b):
    aq, ar = offset_to_axial(*a)
    bq, br = offset_to_axial(*b)
    return (abs(aq - bq) + abs(ar - br) + abs(aq + ar - bq - br)) // 2


def tiles_within(center, radius, in_bounds=None):
    """All tiles within `radius` of center (inclusive). in_bounds is a
    predicate (x,y) -> bool."""
    cx, cy = center
    out = []
    for dy in range(-radius, radius + 1):
        for dx in range(-radius * 2, radius * 2 + 1):
            tx, ty = cx + dx, cy + dy
            if hex_distance(center, (tx, ty)) <= radius:
                if in_bounds is None or in_bounds(tx, ty):
                    out.append((tx, ty))
    return out


def verify_neighbors(known_adjacent_pairs):
    """Given a list of (a, b) tile pairs known to be adjacent in-game,
    return True if odd-r matches them. Use to pick the right layout."""
    for a, b in known_adjacent_pairs:
        if b not in hex_neighbors(*a):
            return False
    return True

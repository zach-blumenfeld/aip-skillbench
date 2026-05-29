#!/usr/bin/env python3
"""Reference factory functions for custom distance metrics.

Provides closure-based factories that return distance callables suitable for
sklearn estimators (DBSCAN, AgglomerativeClustering, ...) and for the scipy
distance APIs (cdist, pdist). Use these as drop-in patterns when an algorithm
needs an application-specific notion of distance.

Run directly to see worked sklearn + scipy examples.
"""

from __future__ import annotations

from typing import Callable

import numpy as np


Point = np.ndarray
Distance = Callable[[Point, Point], float]


def create_weighted_euclidean(weight_x: float, weight_y: float) -> Distance:
    """Anisotropic Euclidean: independent axis weights on x and y."""

    def distance(a: Point, b: Point) -> float:
        dx = a[0] - b[0]
        dy = a[1] - b[1]
        return float(np.sqrt((weight_x * dx) ** 2 + (weight_y * dy) ** 2))

    return distance


def create_shape_weighted_distance(shape_weight: float) -> Distance:
    """Single-knob anisotropic Euclidean parameterised by `shape_weight` (w).

    d(a, b) = sqrt((w * dx)**2 + ((2 - w) * dy)**2)

    w == 1   -> standard Euclidean
    w  > 1   -> attenuates y differences (favours x-aligned proximity)
    w  < 1   -> attenuates x differences (favours y-aligned proximity)
    """

    wx = shape_weight
    wy = 2.0 - shape_weight

    def distance(a: Point, b: Point) -> float:
        dx = a[0] - b[0]
        dy = a[1] - b[1]
        return float(np.sqrt((wx * dx) ** 2 + (wy * dy) ** 2))

    return distance


def create_manhattan_distance(scale: float = 1.0) -> Distance:
    """L1 (sum of absolute differences) with an optional scalar multiplier."""

    def distance(a: Point, b: Point) -> float:
        return float(scale * (abs(a[0] - b[0]) + abs(a[1] - b[1])))

    return distance


def _demo() -> None:
    from sklearn.cluster import DBSCAN
    from scipy.spatial.distance import cdist, pdist, squareform

    rng = np.random.default_rng(0)
    points = rng.uniform(0, 50, size=(12, 2))

    # sklearn: pass any callable as `metric`.
    metric = create_shape_weighted_distance(shape_weight=1.3)
    labels = DBSCAN(eps=10, min_samples=3, metric=metric).fit_predict(points)
    print("DBSCAN labels (shape_weight=1.3):", labels)

    # scipy.spatial.distance: same callable works with cdist / pdist.
    dmat = cdist(points, points, metric=metric)
    pair = squareform(pdist(points, metric=metric))
    print("cdist shape:", dmat.shape, "pdist square shape:", pair.shape)


if __name__ == "__main__":
    _demo()

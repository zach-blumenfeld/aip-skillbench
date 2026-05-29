"""Reference template: parameterized custom distance factory.

Demonstrates the closure/factory pattern for building a custom callable
metric whose parameters you intend to sweep (e.g., during hyperparameter
search). Adapt the inner `distance` to your application's geometry —
the factory shape is what to copy.

Pattern:

    factory(params) -> callable(a, b) -> float

where `a` and `b` are 1D numpy arrays of equal length (one row of the
input matrix each), and the returned callable is what you pass as the
`metric=` argument to sklearn.cluster.DBSCAN / scipy.spatial.cdist /
scipy.spatial.pdist.

Example sweep:

    for w in np.arange(0.9, 2.0, 0.1):
        metric = create_weighted_distance(w)
        db = DBSCAN(eps=10, min_samples=3, metric=metric).fit(points)
        ...
"""

from __future__ import annotations

import math


def create_weighted_distance(weight_x: float, weight_y: float):
    """Return a callable d(a, b) computing weighted Euclidean distance.

    Useful when one axis should dominate cluster shape (e.g., elongated
    clusters along x when weight_x > weight_y).
    """

    def distance(a, b):
        dx = a[0] - b[0]
        dy = a[1] - b[1]
        return math.sqrt((weight_x * dx) ** 2 + (weight_y * dy) ** 2)

    return distance


def create_shape_weighted_distance(shape_weight: float):
    """Single-parameter variant: weight_x = w, weight_y = (2 - w).

    Equivalent to standard Euclidean when shape_weight == 1. Values > 1
    attenuate y-distances; values < 1 attenuate x-distances. Convenient
    when you want one knob instead of two.
    """
    return create_weighted_distance(shape_weight, 2.0 - shape_weight)


if __name__ == "__main__":
    # Smoke test: a unit step on each axis under the default weights.
    d = create_weighted_distance(1.0, 1.0)
    assert abs(d([0.0, 0.0], [1.0, 0.0]) - 1.0) < 1e-9
    assert abs(d([0.0, 0.0], [0.0, 1.0]) - 1.0) < 1e-9

    d_shape = create_shape_weighted_distance(1.0)
    assert abs(d_shape([0.0, 0.0], [1.0, 1.0]) - math.sqrt(2.0)) < 1e-9
    print("ok")

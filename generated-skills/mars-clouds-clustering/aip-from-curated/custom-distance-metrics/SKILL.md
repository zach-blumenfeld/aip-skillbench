---
name: custom-distance-metrics
description: Define custom distance/similarity metrics for clustering and ML algorithms. Use when working with DBSCAN, sklearn, or scipy distance functions with application-specific metrics — weighted axes, parameterized factories for hyperparameter sweeps, or scipy cdist/pdist with a custom callable.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a3
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a3/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Define application-specific distance or similarity metrics for clustering
  and ML algorithms in sklearn and scipy. Covers the two patterns that
  cover almost every real need — a plain callable, and a closure factory
  for parameterized metrics you intend to sweep — plus how to wire the
  callable into DBSCAN, cdist, and pdist, and what to watch for on large
  inputs.

trigger_when:
  - Calling sklearn clustering (DBSCAN, OPTICS, AgglomerativeClustering) with a non-built-in `metric`.
  - Building distance matrices with `scipy.spatial.distance.cdist` / `pdist` / `squareform`.
  - The distance needs to weight axes differently, parameterize over a knob, or otherwise diverge from Euclidean/Manhattan/Minkowski built-ins.
  - Running a hyperparameter sweep where each combination implies a different distance function.

do_not_use_when:
  - A built-in metric name (`euclidean`, `manhattan`, `cosine`, `minkowski`, ...) already expresses what you need — pass the string, not a callable.
  - You only need a precomputed distance matrix and the algorithm accepts `metric='precomputed'`; build the matrix directly with vectorized numpy and skip the callable.

steps:
  - name: identify-metric-need
    description: >
      Pin down what the metric must express before writing code. Decide
      (a) the input shape the callable will see (sklearn passes two 1D
      arrays — one row each), (b) which axes or features matter and
      whether they need different weights, and (c) whether any
      parameters will be swept (eps, weights, scale). If parameters
      will be swept, you need the factory pattern; if not, a plain
      function is enough.
    outputs:
      - name: metric-spec
        type: object
        description: Informal spec — input shape, axis weights, parameters (if any), expected output sign/range.

  - name: choose-pattern
    description: >
      Pick exactly one of the two patterns.

      (1) **Plain callable** — write a top-level `def my_distance(a, b):`
      that returns a float. Use when the distance has no tunable
      parameters or you only ever need one fixed configuration.

      (2) **Closure factory** — write `def create_xxx_distance(params):`
      that returns an inner `distance(a, b)` capturing `params` in its
      closure. Use whenever you will sweep parameters (each call to the
      factory yields a fresh callable bound to those parameter values).
      Hyperparameter searches almost always want this shape.

      The bundled template in `scripts/weighted_distance_factory.py`
      shows both `create_weighted_distance(weight_x, weight_y)` and the
      single-knob `create_shape_weighted_distance(shape_weight)` —
      adapt the inner body to the geometry your task needs.
    inputs:
      - name: metric-spec
        type: object
    outputs:
      - name: pattern-choice
        type: string
        description: "`callable` or `factory`."
    one_of:
      - Plain callable
      - Closure factory

  - name: implement-metric
    description: >
      Write the function. Two rules cover almost every mistake.

      • **The callable receives 1D arrays, not 2D.** Index features as
        `a[0]`, `a[1]`, ... — do not assume rows/columns. sklearn passes
        one row at a time.

      • **Return a non-negative float.** Distances must satisfy
        `d(a, a) == 0` and `d(a, b) >= 0`. Use `math.sqrt` /
        `np.sqrt` / `abs` as needed. Symmetry (`d(a,b) == d(b,a)`) is
        expected by most algorithms — break it only with eyes open.

      Concrete shapes (adapt freely):

      ```python
      # Plain callable — fixed weights baked in
      def my_distance(a, b):
          dx, dy = a[0] - b[0], a[1] - b[1]
          return (dx * dx + dy * dy) ** 0.5

      # Factory — weights become parameters
      def create_weighted_distance(weight_x, weight_y):
          def distance(a, b):
              dx, dy = a[0] - b[0], a[1] - b[1]
              return ((weight_x * dx) ** 2 + (weight_y * dy) ** 2) ** 0.5
          return distance

      # Manhattan variant (L1) with a scale knob — same factory shape
      def create_manhattan_distance(scale=1.0):
          def distance(a, b):
              return scale * (abs(a[0] - b[0]) + abs(a[1] - b[1]))
          return distance
      ```

      For richer parameterization, see
      `scripts/weighted_distance_factory.py`.
    inputs:
      - name: pattern-choice
        type: string
      - name: metric-spec
        type: object
    outputs:
      - name: metric-callable
        type: object
        description: The Python callable (or factory that produces callables) to pass downstream.

  - name: wire-into-algorithm
    description: >
      Pass the callable as the algorithm's `metric=` argument.

      **sklearn DBSCAN** (and OPTICS / AgglomerativeClustering with
      `affinity='precomputed'` is the alternative):

      ```python
      from sklearn.cluster import DBSCAN

      metric = create_weighted_distance(weight_x=2.0, weight_y=0.5)
      db = DBSCAN(eps=10, min_samples=3, metric=metric).fit(points)
      ```

      **scipy distance matrices** for batch use:

      ```python
      from scipy.spatial.distance import cdist, pdist, squareform

      def my_metric(u, v):
          return ((u - v) ** 2).sum() ** 0.5

      # Between two sets
      D = cdist(points_a, points_b, metric=my_metric)

      # Pairwise within one set, condensed -> square form
      D = squareform(pdist(points, metric=my_metric))
      ```

      For hyperparameter sweeps, instantiate a fresh callable each
      iteration so the closure binds that iteration's parameters:

      ```python
      for w in shape_weights:
          metric = create_shape_weighted_distance(w)
          db = DBSCAN(eps=eps, min_samples=ms, metric=metric).fit(points)
          ...
      ```
    inputs:
      - name: metric-callable
        type: object
    outputs:
      - name: fitted-or-matrix
        type: object
        description: The fitted sklearn estimator or the computed distance matrix.

  - name: tune-performance
    description: >
      Python callables are interpreter-bound — sklearn / scipy call them
      O(N²) times for pairwise work, and that dominates wall-clock on
      anything past a few thousand points. Mitigations, in order of
      effort:

      • **Prefer a built-in metric name** if one fits — `'euclidean'`,
        `'manhattan'`, `'minkowski'` route through compiled code and
        are an order of magnitude faster than a Python callable.

      • **Precompute the matrix once** and pass it via
        `metric='precomputed'` if the same distances will be reused
        across multiple model fits.

      • **Vectorize the body** — write the metric in terms of numpy
        array ops on (u, v) and lift to `cdist`/`pdist` rather than a
        per-pair Python loop.

      • **Cache invariants** outside the closure — anything that doesn't
        depend on (a, b) should be computed once at factory time, not
        on every distance call.
    inputs:
      - name: metric-callable
        type: object

scenarios:
  - need: >
      DBSCAN with weighted axes — y-axis distances should count for
      less than x-axis distances to find horizontally-elongated
      clusters.
    action: >
      Use `create_weighted_distance(weight_x=1.0, weight_y=0.5)` from
      the bundled template; pass the returned callable to
      `DBSCAN(metric=...)`.
    outcome: >
      DBSCAN's eps threshold now applies to weighted Euclidean
      distance, so neighborhoods are wider along y than along x.

  - need: >
      Hyperparameter sweep over a single shape-weight knob `w` where
      `d(a, b) = sqrt((w·Δx)² + ((2 - w)·Δy)²)`.
    context: >
      `w == 1` is standard Euclidean. The sweep wants `w ∈ [0.9, 1.9]`
      to explore both x-dominant and y-dominant clusterings.
    action: >
      For each `w` in the sweep, call
      `create_shape_weighted_distance(w)` to build a fresh callable,
      then fit DBSCAN with that callable. Do not rebuild the input
      points each iteration — only the metric callable changes.
    outcome: >
      Each iteration produces a different clustering shaped by `w`,
      letting the search rank configurations on whatever downstream
      objective applies (F1, silhouette, Pareto frontier).

  - need: >
      Reuse the same pairwise distances across many model fits.
    action: >
      Build the matrix once with
      `D = squareform(pdist(points, metric=custom))` and pass it as
      `DBSCAN(metric='precomputed').fit(D)` for each fit.
    outcome: >
      Custom callable runs O(N²) once instead of once per fit.

anti_patterns:
  - Writing a non-vectorized Python distance for tens of thousands of points and waiting for DBSCAN to finish — at that size, vectorize or precompute.
  - Hardcoding parameters into a plain callable when you will sweep them — every sweep iteration then needs an edit. Use a factory.
  - Indexing the callable's arguments as 2D (`a[0, :]`) — sklearn passes 1D rows; this will raise on the first call.
  - Forgetting closures bind by reference — appending `lambda` callables inside a `for w in ws` loop captures the final `w` value for every callable. Use a factory function (`create_xxx(w)`) so each iteration binds its own `w`.
  - Returning a signed similarity where a non-negative distance is required — DBSCAN, cdist, and pdist all expect `d >= 0`.
  - Reaching for a custom callable when a built-in metric name (`euclidean`, `manhattan`, `cosine`, `minkowski`) already fits — the string form runs in compiled code and is far faster.
```

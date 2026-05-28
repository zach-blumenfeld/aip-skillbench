---
name: custom-distance-metrics
description: Define custom distance/similarity metrics for clustering and ML algorithms. Use when working with DBSCAN, sklearn, or scipy distance functions with application-specific metrics.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a2/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Plug an application-specific notion of distance into sklearn estimators
  (DBSCAN, AgglomerativeClustering, NearestNeighbors, ...) and the scipy
  distance APIs (cdist, pdist, squareform). Covers the three things that
  trip agents up: choosing the right API surface, building a parameterised
  metric as a closure factory, and keeping the call cheap enough for
  hyperparameter sweeps.

trigger_when:
  - Configuring DBSCAN, AgglomerativeClustering, NearestNeighbors, or any
    sklearn estimator that accepts a `metric=` argument with anything other
    than the built-in string metric names.
  - Computing a pairwise or rectangular distance matrix with
    `scipy.spatial.distance.cdist` / `pdist` / `squareform` and the metric
    is not a built-in name.
  - The distance has tunable parameters (axis weights, scales, thresholds)
    that need to vary across a grid search or per call site.
  - Reaching for a precomputed distance matrix (`metric="precomputed"`) to
    avoid recomputing distances across repeated estimator calls.

do_not_use_when:
  - The standard `euclidean`, `manhattan`, `cosine`, `chebyshev`, etc. metric
    already fits — pass the string name and let sklearn / scipy use the C
    path.
  - The "custom" metric is just a linear rescale of input axes; rescale the
    coordinates once and use the built-in Euclidean instead (see
    `references/performance.md`).

steps:
  - name: choose-api-surface
    description: >
      Pick how the metric will be consumed before writing it. sklearn
      estimators accept either a callable as `metric=` or a precomputed
      square matrix with `metric="precomputed"`. scipy's `cdist` and `pdist`
      accept the same callable signature. The choice drives the next steps.
    inputs:
      - name: estimator-or-api
        type: string
        description: Target API (e.g. `sklearn.cluster.DBSCAN`, `scipy.spatial.distance.cdist`).
      - name: reuse-count
        type: integer
        description: Roughly how many times the same pairwise distances will be queried. High reuse favours the precomputed path.
    outputs:
      - name: surface
        type: string
        description: One of `sklearn-callable`, `sklearn-precomputed`, `scipy-callable`.
    one_of:
      - sklearn-callable
      - sklearn-precomputed
      - scipy-callable

  - name: build-parameterised-distance
    description: >
      Build the distance as a closure returned by a factory function. The
      factory binds the tunable parameters; the inner function takes two 1D
      arrays `a`, `b` and returns a float. `scripts/build_distance_metric.py`
      ships three reference factories (weighted Euclidean, shape-weighted
      Euclidean, scaled Manhattan) — import them or copy the pattern.
    script: scripts/build_distance_metric.py
    inputs:
      - name: parameters
        type: object
        description: Tunable knobs (axis weights, scales, thresholds) bound by the factory.
    outputs:
      - name: metric-fn
        type: object
        description: Callable `(a, b) -> float` ready to pass as `metric=`.

  - name: precompute-distance-matrix
    description: >
      Only when `surface` is `sklearn-precomputed` or many lookups are
      expected. Build the square distance matrix with
      `scipy.spatial.distance.cdist(points, points, metric=metric_fn)` (or
      `squareform(pdist(points, metric=metric_fn))`), then pass the matrix
      to the estimator with `metric="precomputed"`.
    depends_on:
      - choose-api-surface
      - build-parameterised-distance
    inputs:
      - name: surface
        type: string
      - name: points
        type: object
        description: 2D array of shape `(n, d)`.
      - name: metric-fn
        type: object
    outputs:
      - name: distance-matrix
        type: object
        description: Square `(n, n)` ndarray. Skipped entirely when `surface == "sklearn-callable"` or `scipy-callable`.

  - name: wire-metric-into-estimator
    description: >
      Pass the closure (callable path) or the precomputed matrix
      (precomputed path) into the estimator. For sklearn callables use
      `DBSCAN(eps=..., min_samples=..., metric=metric_fn)`. For the
      precomputed path use `DBSCAN(eps=..., min_samples=..., metric="precomputed").fit(distance_matrix)`.
      For scipy use `cdist(a, b, metric=metric_fn)` or
      `pdist(points, metric=metric_fn)`.
    depends_on:
      - build-parameterised-distance
    inputs:
      - name: surface
        type: string
      - name: metric-fn
        type: object
      - name: distance-matrix
        type: object
        nullable: true
    outputs:
      - name: fitted-estimator-or-matrix
        type: object

  - name: check-performance
    description: >
      Estimate the cost before running a sweep. Python callables are
      single-threaded and per-pair; large `n` × many hyperparameter cells
      hurts. Read `references/performance.md` and apply the cheapest fix
      that works: vectorise the closure body, precompute and reuse the
      matrix, or rewrite the metric as a coordinate rescale and switch to
      the built-in C path. Parallelise the outer loop, not the closure.
    inputs:
      - name: dataset-size
        type: integer
      - name: sweep-size
        type: integer
    outputs:
      - name: optimisation-decision
        type: string
        description: One of `keep-callable`, `vectorise-closure`, `precompute-once`, `rescale-coords-use-builtin`.

scenarios:
  - need: >
      DBSCAN on 2D points with an anisotropic distance controlled by one
      knob `w` such that `d = sqrt((w*dx)**2 + ((2-w)*dy)**2)`. Many
      `(eps, min_samples, w)` combinations to sweep.
    context: >
      Sweep size dominates per-call cost. Each `w` defines a different
      metric, so a single precomputed matrix is not reusable across the
      sweep, but the metric is a pure axis rescale.
    action: >
      `choose-api-surface` -> `sklearn-callable` for correctness, but
      `check-performance` flags this as `rescale-coords-use-builtin`: scale
      `x' = w*x`, `y' = (2-w)*y` once per `w`, then call
      `DBSCAN(metric="euclidean")` on the rescaled points. Cluster identity
      is preserved.
    outcome: >
      Closure factory still exists as the reference / correctness oracle,
      but the hot loop runs on the C euclidean path.

  - need: Compute a pairwise distance matrix between two sets of points with a custom metric.
    action: >
      `choose-api-surface` -> `scipy-callable`. `build-parameterised-distance`
      returns the closure. `wire-metric-into-estimator` calls
      `cdist(points_a, points_b, metric=metric_fn)`.
    outcome: Dense `(len(points_a), len(points_b))` distance matrix.

  - need: Sklearn estimator that will be re-fit many times on the same points with the same metric.
    action: >
      `choose-api-surface` -> `sklearn-precomputed`.
      `precompute-distance-matrix` builds the square matrix once;
      `wire-metric-into-estimator` passes it in with `metric="precomputed"`.
    outcome: Repeated fits avoid recomputing pairwise distances.

anti_patterns:
  - Returning a non-finite value (NaN/inf) from the metric — sklearn's
    neighbour search will silently mis-cluster or raise deep in the call.
  - Capturing mutable state in the closure (e.g. a counter, a list)
    expecting it to persist meaningfully across DBSCAN's calls; treat the
    closure as a pure function of `(a, b)`.
  - Writing a Python-level for-loop inside the closure when the body could
    be expressed with numpy array ops on `a` and `b` directly.
  - Recomputing a distance matrix inside the inner loop of a hyperparameter
    sweep when the matrix does not depend on the swept parameter.
  - Using a Python callable for what is really a linear axis rescale —
    rescale the inputs once and call the built-in Euclidean instead.
  - Threading inside the closure to dodge the cost; the GIL eats the win.
    Parallelise the outer loop (across images, across hyperparameter cells)
    instead.
```

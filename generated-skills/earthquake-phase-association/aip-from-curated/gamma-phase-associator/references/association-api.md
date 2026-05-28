# `association` — full API reference

Load this when preparing the `picks`/`stations` DataFrames, populating the
`config` dict, or parsing the `(events, assignments)` return value.

GaMMA treats phase association as unsupervised clustering: it models each
event's phase picks with a multivariate Gaussian and uses
Expectation-Maximization to assign picks and estimate source parameters
(location, origin time, magnitude).

> Zhu, W., McBrearty, I. W., Mousavi, S. M., Ellsworth, W. L., & Beroza, G. C.
> (2022). Earthquake phase association using a Bayesian Gaussian mixture model.
> Journal of Geophysical Research: Solid Earth, 127(5).

Derivative of https://github.com/AI4EPS/GaMMA. Import path: `from gamma.utils import association, estimate_eps`.

## Function signature

```python
def association(picks, stations, config, event_idx0=0, method="BGMM", **kwargs)
```

Associates seismic phase picks (P and S waves) to earthquake events using
Bayesian or standard Gaussian Mixture Models. It clusters picks based on
arrival time and amplitude information, then fits GMMs to estimate earthquake
locations, times, and magnitudes.

## 1. Input parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `picks` | DataFrame | required | Seismic phase pick data |
| `stations` | DataFrame | required | Station metadata with locations |
| `config` | dict | required | Configuration parameters |
| `event_idx0` | int | `0` | Starting event index for numbering |
| `method` | str | `"BGMM"` | `"BGMM"` (Bayesian) or `"GMM"` (standard) |

## 2. Required DataFrame columns

### `picks` DataFrame

| Column | Type | Description | Example |
|--------|------|-------------|---------|
| `id` | str | Station identifier (must match `stations`) | `network.station.` or `network.station.location.channel` |
| `timestamp` | datetime/str | Pick arrival time (ISO format or datetime) | `"2019-07-04T22:00:06.084"` |
| `type` | str | Phase type: `"p"` or `"s"` (lowercase) | `"p"` |
| `prob` | float | Pick probability/weight (0-1) | `0.94` |
| `amp` | float | Amplitude in m/s (required if `use_amplitude=True`) | `0.000017` |

**Notes:**
- Timestamps must be in UTC or converted to UTC
- Phase types are forced to lowercase internally
- Picks with `amp == 0` or `amp == -1` are filtered when `use_amplitude=True`
- The DataFrame index is used to track pick identities in the output

### `stations` DataFrame

| Column | Type | Description | Example |
|--------|------|-------------|---------|
| `id` | str | Station identifier | `"CI.CCC..BH"` |
| `x(km)` | float | X coordinate in km (projected) | `-35.6` |
| `y(km)` | float | Y coordinate in km (projected) | `45.2` |
| `z(km)` | float | Z coordinate (elevation, typically negative) | `-0.67` |

**Notes:**
- Coordinates should be in a projected local coordinate system (e.g., you can use the `pyproj` package)
- The `id` column must match the `id` values in the picks DataFrame (e.g., `network.station.` or `network.station.location.channel`)
- Group stations by unique `id`, identical attributes are collapsed to a single value and conflicting metadata are preserved as a sorted list. Idiom:
  ```python
  stations = stations.groupby("id").agg(
      lambda x: x.iloc[0] if len(set(x)) == 1 else sorted(list(x))
  ).reset_index()
  ```

## 3. Config dictionary keys

### Required keys

| Key | Type | Description | Example |
|-----|------|-------------|---------|
| `dims` | list[str] | Location dimensions to solve for | `["x(km)", "y(km)", "z(km)"]` |
| `min_picks_per_eq` | int | Minimum picks required per earthquake | `5` |
| `max_sigma11` | float | Maximum allowed time residual in seconds | `2.0` |
| `use_amplitude` | bool | Whether to use amplitude in clustering | `True` |
| `bfgs_bounds` | tuple | Bounds for BFGS optimization | `((-35, 92), (-128, 78), (0, 21), (None, None))` |
| `oversample_factor` | float | Factor for oversampling initial GMM components | `5.0` for `BGMM`, `1.0` for `GMM` |

**Notes on `dims`:**
- Options: `["x(km)", "y(km)", "z(km)"]`, `["x(km)", "y(km)"]`, or `["x(km)"]`

**Notes on `bfgs_bounds`:**
- Format: `((x_min, x_max), (y_min, y_max), (z_min, z_max), (None, None))`
- The last tuple is for time (unbounded)

### Velocity model keys

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `vel` | dict | `{"p": 6.0, "s": 3.47}` | Uniform velocity model (km/s) |
| `eikonal` | dict/None | `None` | 1D velocity model for travel times |

### DBSCAN pre-clustering keys (optional)

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `use_dbscan` | bool | `True` | Enable DBSCAN pre-clustering |
| `dbscan_eps` | float | `25` | Max time between picks (seconds) |
| `dbscan_min_samples` | int | `3` | Min samples in DBSCAN neighborhood |
| `dbscan_min_cluster_size` | int | `500` | Min cluster size for hierarchical splitting |
| `dbscan_max_time_space_ratio` | float | `10` | Max time/space ratio for splitting |

- `dbscan_eps` is obtained from the `estimate_eps` function (see `estimate-eps-api.md`)

### Filtering keys (optional)

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `max_sigma22` | float | `1.0` | Max phase amplitude residual in log scale (required if `use_amplitude=True`) |
| `max_sigma12` | float | `1.0` | Max covariance |
| `max_sigma11` | float | `2.0` | Max phase time residual (s) |
| `min_p_picks_per_eq` | int | `0` | Min P-phase picks per event |
| `min_s_picks_per_eq` | int | `0` | Min S-phase picks per event |
| `min_stations` | int | `5` | Min unique stations per event |

### Other optional keys

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `covariance_prior` | list[float] | auto | Prior for covariance `[time, amp]` |
| `ncpu` | int | auto | Number of CPUs for parallel processing |

## 4. Return values

Returns a tuple `(events, assignments)`:

### `events` (list[dict])

List of dictionaries, each representing an associated earthquake:

| Key | Type | Description |
|-----|------|-------------|
| `time` | str | Origin time (ISO 8601 with milliseconds) |
| `magnitude` | float | Estimated magnitude (999 if `use_amplitude=False`) |
| `sigma_time` | float | Time uncertainty (seconds) |
| `sigma_amp` | float | Amplitude uncertainty (log10 scale) |
| `cov_time_amp` | float | Time-amplitude covariance |
| `gamma_score` | float | Association quality score |
| `num_picks` | int | Total picks assigned |
| `num_p_picks` | int | P-phase picks assigned |
| `num_s_picks` | int | S-phase picks assigned |
| `event_index` | int | Unique event index |
| `x(km)` | float | X coordinate of hypocenter |
| `y(km)` | float | Y coordinate of hypocenter |
| `z(km)` | float | Z coordinate (depth) |

### `assignments` (list[tuple])

List of tuples `(pick_index, event_index, gamma_score)`:
- `pick_index`: Index in the original `picks` DataFrame
- `event_index`: Associated event index
- `gamma_score`: Probability/confidence of assignment

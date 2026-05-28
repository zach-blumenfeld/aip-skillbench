# `estimate_eps` — full API reference

Load this when choosing `config["dbscan_eps"]` for DBSCAN pre-clustering.

## Function signature

```python
def estimate_eps(stations, vp, sigma=2.0)
```

Estimates an appropriate DBSCAN epsilon (`eps`) parameter for clustering
seismic phase picks based on station spacing. The `eps` parameter controls the
maximum time distance between picks that should be considered neighbors in the
DBSCAN clustering algorithm.

## 1. Input parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `stations` | DataFrame | required | Station metadata with 3D coordinates |
| `vp` | float | required | P-wave velocity in km/s |
| `sigma` | float | `2.0` | Number of standard deviations above the mean |

## 2. Required DataFrame columns

### `stations` DataFrame

| Column | Type | Description | Example |
|--------|------|-------------|---------|
| `x(km)` | float | X coordinate in km | `-35.6` |
| `y(km)` | float | Y coordinate in km | `45.2` |
| `z(km)` | float | Z coordinate in km | `-0.67` |

## 3. Return value

| Type | Description |
|------|-------------|
| float | Epsilon value in **seconds** for use with DBSCAN clustering |

## 4. Example usage

```python
from gamma.utils import estimate_eps

# Assuming stations DataFrame is already prepared with x(km), y(km), z(km) columns
vp = 6.0  # P-wave velocity in km/s

# Estimate eps automatically based on station spacing
eps = estimate_eps(stations, vp, sigma=2.0)

# Use in config
config = {
    "use_dbscan": True,
    "dbscan_eps": eps,  # or use estimate_eps(stations, config["vel"]["p"])
    "dbscan_min_samples": 3,
    # ... other config options
}
```

### Typical usage pattern

```python
from gamma.utils import association, estimate_eps

# Automatic eps estimation
config["dbscan_eps"] = estimate_eps(stations, config["vel"]["p"])

# Or manual override (common in practice)
config["dbscan_eps"] = 15  # seconds
```

## 5. Practical notes

- In example notebooks, the function is often **commented out** in favor of hardcoded values (10-15 seconds)
- Practitioners may prefer manual tuning for specific networks/regions
- Typical output values range from **10-20 seconds** depending on station density
- Useful when optimal eps is unknown or when working with new networks

## 6. Related configuration

The output is typically used with these config parameters:

```python
config["dbscan_eps"] = estimate_eps(stations, config["vel"]["p"])
config["dbscan_min_samples"] = 3
config["dbscan_min_cluster_size"] = 500
config["dbscan_max_time_space_ratio"] = 10
```

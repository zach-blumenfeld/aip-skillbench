# Phase associators: PyOcto (default) and GaMMA (fallback)

Read this when PyOcto is unavailable in the environment, or when you want
a second opinion on associator behavior.

## PyOcto (default — used in `scripts/solve.py`)

- Modern, fast, SeisBench-native (`associate_seisbench(picks, stations)`).
- Single config object — minimal boilerplate.
- 1-D velocity model is the right tool for this task (`vp=6`, `vs=vp/1.75`).
- Install: `pip install pyocto`.

If `import pyocto` fails on the target environment, fall back to GaMMA.

## GaMMA fallback

GaMMA (Gaussian Mixture Model Association, Zhu et al. 2022) is the older
SeisBench-adjacent associator. Use when PyOcto cannot be installed.

### Install

```bash
pip install gmma  # if PyPI name is available
# or, from source:
pip install git+https://github.com/AI4EPS/GaMMA.git
```

### Drop-in `associate()` replacement

```python
import math
import pandas as pd
from gamma.utils import association

def associate_gamma(picks, stations: pd.DataFrame) -> pd.DataFrame:
    # picks: list of seisbench.util.Pick. Convert to GaMMA pick DataFrame.
    rows = []
    for p in picks:
        # SeisBench trace_id is "NET.STA.LOC.CHA" — strip to NET.STA.
        parts = p.trace_id.split(".")
        sid = f"{parts[0]}.{parts[1]}"
        rows.append({
            "id": sid,
            "timestamp": pd.Timestamp(str(p.peak_time)),
            "prob": float(p.peak_value),
            "type": p.phase.lower(),  # "p" or "s"
        })
    picks_df = pd.DataFrame(rows)

    # Project lat/lon to local cartesian (equirectangular around centroid).
    lat0 = stations["latitude"].mean()
    lon0 = stations["longitude"].mean()
    R = 6371.0
    d2r = math.pi / 180
    s = stations.copy()
    s["x(km)"] = R * (s["longitude"] - lon0) * d2r * math.cos(lat0 * d2r)
    s["y(km)"] = R * (s["latitude"] - lat0) * d2r
    s["z(km)"] = -s["elevation"] / 1000.0

    x_min, x_max = s["x(km)"].min() - 50, s["x(km)"].max() + 50
    y_min, y_max = s["y(km)"].min() - 50, s["y(km)"].max() + 50

    config = {
        "center": (lon0, lat0),
        "xlim_degree": (stations["longitude"].min() - 1, stations["longitude"].max() + 1),
        "ylim_degree": (stations["latitude"].min() - 1, stations["latitude"].max() + 1),
        "x(km)": (x_min, x_max),
        "y(km)": (y_min, y_max),
        "z(km)": (0.0, 60.0),
        "vel": {"p": 6.0, "s": 6.0 / 1.75},
        "method": "BGMM",
        "use_dbscan": True,
        "use_amplitude": False,
        "dbscan_eps": 10.0,
        "dbscan_min_samples": 3,
        "ncpu": 1,
        "min_picks_per_eq": 6,
        "min_p_picks_per_eq": 2,
        "min_s_picks_per_eq": 1,
        "max_sigma11": 2.0,
        "max_sigma22": 1.0,
        "max_sigma12": 1.0,
        "oversample_factor": 4,
        "bfgs_bounds": (
            (x_min, x_max),
            (y_min, y_max),
            (0.0, 60.0),
            (None, None),
        ),
    }

    station_cols = s[["id", "longitude", "latitude", "elevation",
                      "x(km)", "y(km)", "z(km)"]].copy()
    station_cols = station_cols.rename(columns={"elevation": "elevation(m)"})

    catalogs, _ = association(picks_df, station_cols, config, method="BGMM")
    if not catalogs:
        return pd.DataFrame(columns=["time"])
    return pd.DataFrame(catalogs)
```

GaMMA's catalog has a `time` column already (event origin time, datetime).
Pass through `write_output()` from `solve.py` and the rest of the pipeline
works unchanged.

### Tuning analog

| PyOcto                          | GaMMA                          |
|---------------------------------|--------------------------------|
| `n_picks`                       | `min_picks_per_eq`             |
| `n_p_picks`                     | `min_p_picks_per_eq`           |
| `n_s_picks`                     | `min_s_picks_per_eq`           |
| `velocity_model.tolerance`      | `max_sigma11`                  |
| `association_cutoff_distance`   | bounding `x(km)` / `y(km)`     |

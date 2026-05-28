# Phase picking & association — deep reference

Load this when the default run fails, produces no/too-many events, or the
F1 score is below target and you need to tune.

## 1. Picking model & weights

`pick_phases.py` defaults to **PhaseNet** and tries pretrained weight sets in
order: `instance`, `stead`, `ethz`, `scedc`, `geofon`. These are downloaded
on first use from the SeisBench model repository (needs network or a warm
cache).

- **PhaseNet** — fast, robust, good default for continuous data.
- **EQTransformer** (`--model eqtransformer`) — joint detection + picking;
  sometimes higher precision, slower. Worth trying if PhaseNet over-picks.
- Weight choice matters. `instance` (Italian) and `stead` (global) generalise
  well; `ethz`, `scedc`, `neic` are region-specific. If recall is low, try a
  different weight set before anything else.

Picking is the recall ceiling for the whole pipeline: an event with no picks
can never be associated. Favor **more** picks here and let the associator
reject the false ones.

## 2. Threshold tuning

`--p-threshold` / `--s-threshold` default to `0.2` (deliberately low for
recall). Effects:

- **Too few events / low recall** → lower thresholds (e.g. `0.1`), or switch
  weights/model.
- **Too many spurious events / low precision** → raise thresholds (`0.3`–`0.5`)
  *or* tighten the associator (raise `--min-stations`, lower `--eps`).

Prefer fixing precision at the association stage; keep picking permissive.

## 3. Association: PyOcto (primary)

`associate_events.py` uses PyOcto with a homogeneous `VelocityModel0D`
(`p_velocity=6.0`, `s_velocity=6.0/1.75`). Install if missing:

```bash
pip install pyocto
```

Key `OctoAssociator.from_area` knobs (edit the script to change):
- `zlim=(0, --zmax)` — event depth search range (km). Default 0–50.
- `n_picks`, `n_p_picks`, `n_s_picks`, `n_p_and_s_picks` — minimum picks for a
  valid event. Lower them to recover small events; raise to cut false events.
- `time_before` — how far back in time the associator looks per node (s).

PyOcto inverts for location + origin time, so it handles P-only stations and
overlapping events better than clustering. Its event `time` column is a UNIX
timestamp (seconds) — the script converts it to ISO.

### Station/pick id matching
PyOcto joins picks to stations on the `station`/`id` field. `pick_phases.py`
writes `station = "NETWORK.STATION"` (channel stripped) and `load_stations`
builds the same id and de-duplicates the per-channel rows. If a pick's
`trace_id` carries extra fields, only the first two (`network.station`) are
kept — keep both sides consistent if you change this.

## 4. Association: clustering fallback (no extra deps)

If PyOcto can't be imported or errors, the script falls back to S-P
origin-time clustering (pure numpy/pandas):

- For each station, pair each P with the next S. The S-P time gives distance
  `d = (t_S - t_P) / (1/vs - 1/vp)` and a candidate origin `t0 = t_P - d/vp`.
- Origin times within `--eps` seconds that span `--min-stations` distinct
  stations form one event; the event time is the cluster median.
- `--max-sp` (default 60 s) caps the S-P time, i.e. the max distance (~480 km
  at this velocity model), rejecting implausible P/S pairings.

Tuning the fallback:
- **Missing events** → lower `--min-stations` (to 2) or raise `--eps`.
- **Too many events** → raise `--min-stations` or lower `--eps`.

This method needs both P and S at a station, so it ignores P-only detections.
PyOcto is preferred whenever available.

## 5. Output contract & dedup

`results.csv` must have a `time` column, one row per event, ISO-8601 with **no
timezone**. The grader matches an event as correct when it is within **5 s** of
a ground-truth event, and scores F1 (need ≥ 0.6).

Implications:
- Two predicted events within ~5 s can match at most one ground-truth event,
  so duplicates only cost precision. `--dedup` (default 3 s) merges near
  duplicates. Raise toward 5 s if you still see doublets.
- Median-of-cluster / inversion origin times are typically well within 5 s, so
  exact sub-second accuracy is not required — completeness (recall) and
  avoiding spurious events (precision) drive the score.

## 6. Optimizing F1

F1 balances precision and recall. Strategy:
1. Get a baseline run end to end first; count events vs. a rough expectation.
2. If recall looks low → permissive picking (lower thresholds / other weights),
   lower `--min-stations`, lower PyOcto `n_*picks`.
3. If precision looks low → raise `--min-stations`/`n_*picks`, raise picking
   thresholds, raise `--dedup`.
4. Change one knob at a time and re-run; the pipeline is fast after picks exist
   (re-run only `associate_events.py` when tuning association).

## 7. GaMMA — alternative associator

GaMMA (Gaussian-Mixture associator) is the other standard pairing with
PhaseNet. Use it if PyOcto underperforms. Sketch:

```python
from gamma.utils import association
from pyproj import Proj
import numpy as np, pandas as pd

stations = pd.read_csv("stations.csv")
stations["id"] = stations.network + "." + stations.station
st = stations.drop_duplicates("id").copy()
lon0, lat0 = st.longitude.mean(), st.latitude.mean()
proj = Proj(f"+proj=sterea +lon_0={lon0} +lat_0={lat0} +units=km")
st["x(km)"], st["y(km)"] = proj(st.longitude.values, st.latitude.values)
st["z(km)"] = -st.elevation_m.values / 1e3
st = st.rename(columns={"elevation_m": "elevation(m)"})

picks = pd.read_csv("picks.csv")           # id/station, timestamp, type, prob
picks = picks.rename(columns={"station": "id", "time": "timestamp",
                              "phase": "type", "probability": "prob"})
picks["timestamp"] = pd.to_datetime(picks.timestamp)
picks["type"] = picks["type"].str.lower()  # gamma wants "p"/"s"

config = {
    "dims": ["x(km)", "y(km)", "z(km)"],
    "use_dbscan": True, "use_amplitude": False, "method": "BGMM",
    "vel": {"p": 6.0, "s": 6.0 / 1.75},
    "z(km)": (0, 50),
    "dbscan_eps": 10, "dbscan_min_samples": 3,
    "min_picks_per_eq": 6, "max_sigma11": 2.0,
    "x(km)": (st["x(km)"].min(), st["x(km)"].max()),
    "y(km)": (st["y(km)"].min(), st["y(km)"].max()),
    "bfgs_bounds": ((st["x(km)"].min()-1, st["x(km)"].max()+1),
                    (st["y(km)"].min()-1, st["y(km)"].max()+1),
                    (0, 50), (None, None)),
}
catalogs, assignments = association(picks, st, config, method=config["method"])
catalog = pd.DataFrame(catalogs)           # has a "time" column
catalog["time"] = pd.to_datetime(catalog["time"]).dt.tz_localize(None)
catalog[["time"]].to_csv("/root/results.csv", index=False)
```

## 8. Troubleshooting

- **`from_pretrained` fails / network error** — weights aren't cached. Try a
  different weight set; check whether a cache dir is pre-populated.
- **No picks** — check the stream actually read (`len(stream)`), lower
  thresholds, confirm the model loaded.
- **`tz_localize` errors** — origin times mixing tz-aware/naive; the script's
  `to_naive_iso_column` already strips tz. Ensure any custom path does too.
- **No events but many picks** — associator too strict: lower `--min-stations`
  / PyOcto `n_*picks`, raise `--eps`.
- **Pick station ids don't match stations.csv** — print unique `picks.station`
  vs `stations.id`; reconcile the `network.station` format.

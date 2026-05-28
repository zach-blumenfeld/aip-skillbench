#!/usr/bin/env python3
"""Associate P/S picks into earthquake events using a uniform velocity model.

Velocity model (from the task): vp = 6 km/s, vs = vp / 1.75.

Two methods, tried in this order unless --method forces one:

  1. pyocto  - PyOcto associator with a homogeneous VelocityModel0D. Inverts
               pick times for event location + origin time. Best accuracy;
               handles P-only stations. Requires `pip install pyocto`.
  2. cluster - S-P origin-time clustering, pure numpy/pandas, no extra deps.
               For each station with a P followed by an S, distance comes from
               the S-P time and a candidate origin time is t_P - distance/vp.
               Origin times that agree across >= --min-stations distinct
               stations form one event. Always available as a fallback.

Writes an events catalog CSV (one row per event) with at least a `time`
column in ISO-8601, no timezone. Default output: /root/results.csv.

Usage:
    python associate_events.py --picks picks.csv \
        --stations /root/data/stations.csv --out /root/results.csv \
        [--method auto|pyocto|cluster] \
        [--zmax 50] [--eps 3.0] [--min-stations 3] \
        [--max-sp 60] [--dedup 3.0]
"""
import argparse
import sys

import numpy as np
import pandas as pd

VP = 6.0
VS = 6.0 / 1.75
# seconds per km of S-P differential time: (1/vs - 1/vp)
SP_PER_KM = (1.0 / VS) - (1.0 / VP)


def load_stations(path):
    df = pd.read_csv(path)
    df["id"] = df["network"].astype(str) + "." + df["station"].astype(str)
    st = df.drop_duplicates("id").copy()
    if "elevation_m" in st.columns:
        st["elevation"] = st["elevation_m"].astype(float)
    else:
        st["elevation"] = 0.0
    return st[["id", "latitude", "longitude", "elevation"]].reset_index(drop=True)


def picks_to_epoch(picks):
    p = picks.copy()
    p["phase"] = p["phase"].astype(str).str.upper()
    # numpy datetime64[ns] -> int64 ns is stable across pandas versions.
    p["epoch"] = pd.to_datetime(p["time"]).to_numpy("datetime64[ns]").astype("int64") / 1e9
    if "probability" not in p.columns:
        p["probability"] = 1.0
    return p


def associate_pyocto(picks, stations, zmax):
    """PyOcto homogeneous-model association. Raises on any failure so the
    caller can fall back to clustering."""
    import pyocto

    vel = pyocto.VelocityModel0D(p_velocity=VP, s_velocity=VS, tolerance=2.0)
    lat = (float(stations.latitude.min()) - 1.0, float(stations.latitude.max()) + 1.0)
    lon = (float(stations.longitude.min()) - 1.0, float(stations.longitude.max()) + 1.0)

    associator = pyocto.OctoAssociator.from_area(
        lat=lat,
        lon=lon,
        zlim=(0.0, float(zmax)),
        time_before=300.0,
        velocity_model=vel,
        n_picks=8,
        n_p_picks=3,
        n_s_picks=3,
        n_p_and_s_picks=3,
    )

    st = stations.copy()
    associator.transform_stations(st)  # adds x/y/z (km) in place

    p = picks_to_epoch(picks)
    pyocto_picks = pd.DataFrame(
        {
            "station": p["station"],
            "time": p["epoch"],
            "phase": p["phase"],
            "probability": p["probability"],
        }
    )

    events, _assignments = associator.associate(pyocto_picks, st)
    if events is None or len(events) == 0:
        return pd.DataFrame(columns=["time"])
    events = events.copy()
    # PyOcto event "time" is a UNIX timestamp (seconds).
    events["time"] = pd.to_datetime(events["time"], unit="s")
    return events


def associate_cluster(picks, eps, min_stations, max_sp):
    """S-P origin-time clustering. Pure numpy/pandas fallback."""
    p = picks_to_epoch(picks)
    origins = []  # (origin_time_epoch, station)
    for sta, g in p.groupby("station"):
        p_times = np.sort(g.loc[g.phase == "P", "epoch"].values)
        s_times = np.sort(g.loc[g.phase == "S", "epoch"].values)
        if len(p_times) == 0 or len(s_times) == 0:
            continue
        for tp in p_times:
            later = s_times[s_times > tp]
            if len(later) == 0:
                continue
            sp = float(later[0] - tp)
            if sp <= 0 or sp > max_sp:
                continue
            distance_km = sp / SP_PER_KM
            t0 = tp - distance_km / VP
            origins.append((t0, sta))

    if not origins:
        return pd.DataFrame(columns=["time"])

    origins.sort(key=lambda x: x[0])
    times = np.array([o[0] for o in origins])
    stas = [o[1] for o in origins]

    # Group where consecutive origin-time gaps stay within eps.
    events = []
    start = 0
    for i in range(1, len(times) + 1):
        if i == len(times) or (times[i] - times[i - 1]) > eps:
            cluster_times = times[start:i]
            cluster_stations = set(stas[start:i])
            if len(cluster_stations) >= min_stations:
                events.append(float(np.median(cluster_times)))
            start = i

    return pd.DataFrame({"time": pd.to_datetime(events, unit="s")})


def dedup_events(events, dedup_s):
    """Drop events whose times fall within dedup_s of a kept event."""
    if events.empty:
        return events
    ts = pd.to_datetime(events["time"]).sort_values().reset_index(drop=True)
    kept = []
    for t in ts:
        if kept and (t - kept[-1]).total_seconds() < dedup_s:
            continue
        kept.append(t)
    return pd.DataFrame({"time": kept})


def to_naive_iso_column(events):
    ts = pd.to_datetime(events["time"])
    if getattr(ts.dt, "tz", None) is not None:
        ts = ts.dt.tz_convert("UTC").dt.tz_localize(None)
    out = events.copy()
    out["time"] = ts.dt.strftime("%Y-%m-%dT%H:%M:%S.%f")
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--picks", required=True)
    ap.add_argument("--stations", required=True)
    ap.add_argument("--out", default="/root/results.csv")
    ap.add_argument("--method", choices=["auto", "pyocto", "cluster"], default="auto")
    ap.add_argument("--zmax", type=float, default=50.0, help="Max event depth (km)")
    ap.add_argument("--eps", type=float, default=3.0, help="Cluster origin-time tolerance (s)")
    ap.add_argument("--min-stations", type=int, default=3, help="Min distinct stations per event (cluster)")
    ap.add_argument("--max-sp", type=float, default=60.0, help="Max S-P time considered (s)")
    ap.add_argument("--dedup", type=float, default=3.0, help="Merge events within this many seconds")
    args = ap.parse_args()

    stations = load_stations(args.stations)
    picks = pd.read_csv(args.picks)
    print(f"Loaded {len(picks)} picks and {len(stations)} stations", file=sys.stderr)

    events = None
    if args.method in ("auto", "pyocto"):
        try:
            events = associate_pyocto(picks, stations, args.zmax)
            print(f"PyOcto produced {len(events)} events", file=sys.stderr)
        except Exception as e:  # noqa: BLE001 - graceful fallback
            print(f"PyOcto unavailable/failed ({e}); falling back to clustering", file=sys.stderr)
            events = None
            if args.method == "pyocto":
                print("--method pyocto was forced; using clustering anyway", file=sys.stderr)

    if events is None or len(events) == 0:
        events = associate_cluster(picks, args.eps, args.min_stations, args.max_sp)
        print(f"Clustering produced {len(events)} events", file=sys.stderr)

    events = dedup_events(events, args.dedup)
    events = to_naive_iso_column(events)
    events = events.sort_values("time").reset_index(drop=True)
    events.to_csv(args.out, index=False)
    print(f"Wrote {len(events)} events to {args.out}")


if __name__ == "__main__":
    main()

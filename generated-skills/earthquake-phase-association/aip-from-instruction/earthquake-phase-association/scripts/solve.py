#!/usr/bin/env python3
"""End-to-end earthquake phase association.

Pipeline:
  1. Load MSEED waveforms (obspy) and station metadata (pandas).
  2. Pick P/S phases with SeisBench PhaseNet (pretrained on STEAD).
  3. Associate picks into events with PyOcto using a 1-D velocity model
     (vp=6.0 km/s, vs=vp/1.75).
  4. Write a CSV with one row per event and a `time` column in ISO format,
     timezone-naive (the SkillsBench evaluator parses ISO and rejects tz).

Usage:
    python solve.py <wave.mseed> <stations.csv> <output.csv>

Tunable knobs are exposed as module-level constants near the top of the
relevant functions. See references/tuning.md for guidance.
"""

from __future__ import annotations

import argparse
import sys

import obspy
import pandas as pd


def load_stations(csv_path: str) -> pd.DataFrame:
    """Collapse the per-channel station CSV into one row per network.station.

    Input columns (per the task instruction): network, station, channel,
    longitude, latitude, elevation_m, response.

    Output columns: id (NET.STA), latitude, longitude, elevation (meters).
    """
    df = pd.read_csv(csv_path)
    g = df.groupby(["network", "station"], as_index=False).agg(
        longitude=("longitude", "first"),
        latitude=("latitude", "first"),
        elevation=("elevation_m", "first"),
    )
    g["id"] = g["network"] + "." + g["station"]
    return g[["id", "latitude", "longitude", "elevation"]]


def pick_phases(stream, p_threshold: float = 0.2, s_threshold: float = 0.2):
    """Run PhaseNet on the full Stream and return a list of SeisBench Picks.

    PhaseNet (pretrained on STEAD) is a solid general-purpose default for
    regional P/S onset detection. Lower thresholds raise recall (more picks)
    at the cost of more false positives downstream.
    """
    import seisbench.models as sbm

    model = sbm.PhaseNet.from_pretrained("stead")
    out = model.classify(
        stream,
        batch_size=128,
        P_threshold=p_threshold,
        S_threshold=s_threshold,
    )
    return list(out.picks)


def associate(picks, stations: pd.DataFrame) -> pd.DataFrame:
    """Associate picks into events with PyOcto and return a catalog DataFrame.

    Returned DataFrame includes a `time` column (datetime) per event, plus
    latitude/longitude/depth (after `transform_events`).
    """
    import pyocto

    velocity_model = pyocto.VelocityModel0D(
        p_velocity=6.0,
        s_velocity=6.0 / 1.75,
        tolerance=2.0,
        association_cutoff_distance=250.0,
    )

    lat_min, lat_max = stations["latitude"].min(), stations["latitude"].max()
    lon_min, lon_max = stations["longitude"].min(), stations["longitude"].max()

    associator = pyocto.OctoAssociator.from_area(
        lat=(lat_min - 0.5, lat_max + 0.5),
        lon=(lon_min - 0.5, lon_max + 0.5),
        zlim=(0, 60),
        time_before=300,
        velocity_model=velocity_model,
        n_picks=6,
        n_p_picks=2,
        n_s_picks=1,
        n_p_and_s_picks=1,
    )

    stations_proj = associator.transform_stations(stations.copy())
    events, _ = associator.associate_seisbench(picks, stations_proj)
    if events is None or len(events) == 0:
        return pd.DataFrame(columns=["time"])
    associator.transform_events(events)
    return events


def write_output(events: pd.DataFrame, path: str) -> int:
    """Write the catalog with a single `time` column (ISO, no timezone)."""
    if events is None or len(events) == 0:
        pd.DataFrame(columns=["time"]).to_csv(path, index=False)
        return 0

    times = pd.to_datetime(events["time"], errors="coerce")
    # Strip timezone if present — the evaluator expects naive ISO timestamps.
    if pd.api.types.is_datetime64tz_dtype(times):
        times = times.dt.tz_convert("UTC").dt.tz_localize(None)

    out = pd.DataFrame(
        {"time": times.dt.strftime("%Y-%m-%dT%H:%M:%S.%f")}
    )
    out = out.dropna(subset=["time"]).reset_index(drop=True)
    out.to_csv(path, index=False)
    return len(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("mseed", help="Path to the MSEED waveform file.")
    ap.add_argument("stations", help="Path to the station CSV.")
    ap.add_argument("output", help="Path for the event catalog CSV.")
    args = ap.parse_args()

    stream = obspy.read(args.mseed)
    print(f"[solve] loaded {len(stream)} traces from {args.mseed}", file=sys.stderr)

    stations = load_stations(args.stations)
    print(f"[solve] loaded {len(stations)} unique stations", file=sys.stderr)

    picks = pick_phases(stream)
    print(f"[solve] PhaseNet produced {len(picks)} picks", file=sys.stderr)

    if not picks:
        write_output(None, args.output)
        print(f"[solve] no picks; wrote empty catalog to {args.output}", file=sys.stderr)
        return 0

    events = associate(picks, stations)
    n = write_output(events, args.output)
    print(f"[solve] wrote {n} events to {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

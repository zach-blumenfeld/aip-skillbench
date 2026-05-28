"""Load and validate routing data: depot + stations + ID/index mappings.

Single source of truth for parsing the task's `data.json`. Downstream steps
must use the returned dictionaries — never re-parse the raw JSON, never
assume station IDs are 0..n-1.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def parse_location(record: dict, label: str) -> dict:
    """Validate a {latitude, longitude} record and return floats.

    Raises ValueError on out-of-range degrees. Lat/lon are kept in degrees;
    the distance function is the only place radians appear.
    """
    lat = float(record["latitude"])
    lon = float(record["longitude"])
    if not (-90.0 <= lat <= 90.0):
        raise ValueError(f"{label} latitude out of range: {lat}")
    if not (-180.0 <= lon <= 180.0):
        raise ValueError(f"{label} longitude out of range: {lon}")
    return {"latitude": lat, "longitude": lon}


def load_routing_data(data_path: str | Path) -> dict[str, Any]:
    """Load depot + stations from a task data.json and build index maps.

    Returns a dict with:
        raw            — the full parsed JSON (so callers can reach other fields)
        depot          — {latitude, longitude}, validated
        stations_data  — list of original station records (preserves all fields)
        station_ids    — list[int] of station IDs in input order
        station_locations — list[{latitude, longitude}] aligned with station_ids
        id_to_idx      — dict[int, int]   user-facing station ID -> internal 0..n-1 index
        idx_to_id      — dict[int, int]   internal index -> user-facing station ID
        n_stations     — len(station_ids)

    Use internal indices in optimization variables. Use original station IDs
    in final reports. Convert at the boundary, not in the middle of the model.
    """
    raw = json.loads(Path(data_path).read_text())

    depot = parse_location(raw["depot"], "depot")

    stations_data = list(raw["stations"])
    station_ids = [int(s["id"]) for s in stations_data]
    if len(station_ids) != len(set(station_ids)):
        raise ValueError("duplicate station ids in input data")

    station_locations = [
        parse_location(s, f"station {s['id']}") for s in stations_data
    ]

    id_to_idx = {sid: idx for idx, sid in enumerate(station_ids)}
    idx_to_id = {idx: sid for sid, idx in id_to_idx.items()}

    return {
        "raw": raw,
        "depot": depot,
        "stations_data": stations_data,
        "station_ids": station_ids,
        "station_locations": station_locations,
        "id_to_idx": id_to_idx,
        "idx_to_id": idx_to_id,
        "n_stations": len(station_ids),
    }


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 2:
        print("usage: parse_data.py <path/to/data.json>", file=sys.stderr)
        sys.exit(2)
    bundle = load_routing_data(sys.argv[1])
    print(
        f"loaded {bundle['n_stations']} stations; depot=({bundle['depot']['latitude']}, "
        f"{bundle['depot']['longitude']}); ids={bundle['station_ids'][:5]}..."
    )

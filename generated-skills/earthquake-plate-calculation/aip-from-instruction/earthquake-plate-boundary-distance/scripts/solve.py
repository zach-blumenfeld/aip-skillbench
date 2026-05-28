#!/usr/bin/env python3
"""
Find the earthquake furthest from a tectonic plate's boundary, restricted to
earthquakes within that plate. Defaults to the Pacific plate. Writes
/root/answer.json with id, place, time (ISO 8601 UTC), magnitude, latitude,
longitude, and distance_km (rounded to 2 decimal places).

Inputs (defaults match the task layout under /root/):
  --earthquakes  GeoJSON FeatureCollection of earthquake Point features
                 (USGS-style: properties.time = epoch ms, properties.mag,
                  properties.place, top-level Feature.id is the canonical id).
  --plates       GeoJSON FeatureCollection of plate polygons (PB2002).
  --boundaries   GeoJSON FeatureCollection of plate boundary lines (PB2002).
                 Currently used only for an optional sanity check; the
                 distance is measured against the chosen plate's own polygon
                 boundary, which is identical in geometry.
  --plate        Plate name or PB2002 code to analyse. Default: Pacific (PA).
  --out          Output path. Default: /root/answer.json.
  --crs          Projected CRS used for planar distance. Default is a
                 Pacific-centered Lambert Azimuthal Equal Area
                 (+proj=laea +lat_0=0 +lon_0=-160 +datum=WGS84 +units=m).

Why a Pacific-centered projection: the Pacific plate crosses the antimeridian.
Reprojecting to a CRS whose central meridian sits inside the Pacific lets
shapely treat the plate as a single contiguous polygon and produces
well-defined point-to-line distances in metres.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
from shapely.geometry import Point, shape

DEFAULT_CRS = (
    "+proj=laea +lat_0=0 +lon_0=-160 +x_0=0 +y_0=0 "
    "+datum=WGS84 +units=m +no_defs +type=crs"
)

PLATE_NAME_COLUMNS = ("PlateName", "plate_name", "Name", "name", "PLATE", "plate", "LAYER")
PLATE_CODE_COLUMNS = ("Code", "code", "PlateCode", "plate_code", "Symbol", "PB2002")


def load_geojson_as_gdf(path: Path) -> gpd.GeoDataFrame:
    """Read a GeoJSON-ish JSON file. Preserves top-level Feature.id as a column."""
    raw = json.loads(path.read_text())
    if isinstance(raw, dict) and raw.get("type") == "FeatureCollection":
        records = []
        for feat in raw["features"]:
            props = dict(feat.get("properties") or {})
            # USGS-style: canonical id lives at the Feature level, not in properties.
            if "id" in feat and "id" not in props:
                props["id"] = feat["id"]
            geom = feat.get("geometry")
            props["geometry"] = shape(geom) if geom is not None else None
            records.append(props)
        return gpd.GeoDataFrame(records, geometry="geometry", crs="EPSG:4326")
    if isinstance(raw, list):
        records = []
        for row in raw:
            row = dict(row)
            if isinstance(row.get("geometry"), dict):
                row["geometry"] = shape(row["geometry"])
            elif "longitude" in row and "latitude" in row:
                row["geometry"] = Point(float(row["longitude"]), float(row["latitude"]))
            records.append(row)
        return gpd.GeoDataFrame(records, geometry="geometry", crs="EPSG:4326")
    raise ValueError(f"Unsupported JSON shape in {path}")


def find_plate(plates: gpd.GeoDataFrame, target: str) -> gpd.GeoSeries:
    """Locate the row for the requested plate, matching by name or PB2002 code."""
    target_lower = target.lower()
    target_codes = {target.upper(), "PA" if target_lower.startswith("pac") else target.upper()}
    for col in PLATE_NAME_COLUMNS:
        if col in plates.columns:
            mask = plates[col].astype(str).str.lower().str.contains(target_lower, na=False)
            if mask.any():
                return plates[mask].iloc[0]
    for col in PLATE_CODE_COLUMNS:
        if col in plates.columns:
            mask = plates[col].astype(str).str.upper().isin(target_codes)
            if mask.any():
                return plates[mask].iloc[0]
    raise ValueError(
        f"Could not find plate '{target}'. Columns present: {list(plates.columns)}"
    )


def epoch_ms_to_iso8601_z(value) -> str:
    """Convert a millisecond epoch (int/float/str) to ISO 8601 Zulu seconds."""
    if value is None:
        return ""
    if isinstance(value, str):
        # Already an ISO string? Normalise to seconds + Z.
        try:
            ms = float(value)
        except ValueError:
            try:
                dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
                return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            except ValueError:
                return value
    else:
        ms = float(value)
    dt = datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def extract_id(row) -> str:
    for key in ("id", "ID", "code", "eventId", "event_id", "ids"):
        if key in row and row[key]:
            value = row[key]
            if isinstance(value, str) and key == "ids":
                # USGS "ids" is a comma-delimited list like ",us6000mzvb,..."; take first non-empty.
                parts = [p for p in value.split(",") if p]
                if parts:
                    return parts[0]
            else:
                return str(value)
    raise KeyError("No id field found on earthquake record")


def extract_magnitude(row) -> float:
    for key in ("mag", "magnitude", "Mag", "Magnitude"):
        if key in row and row[key] is not None:
            return float(row[key])
    raise KeyError("No magnitude field found on earthquake record")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--earthquakes", default="/root/earthquakes_2024.json")
    parser.add_argument("--plates", default="/root/PB2002_plates.json")
    parser.add_argument("--boundaries", default="/root/PB2002_boundaries.json")
    parser.add_argument("--plate", default="Pacific")
    parser.add_argument("--out", default="/root/answer.json")
    parser.add_argument("--crs", default=DEFAULT_CRS)
    args = parser.parse_args()

    earthquakes = load_geojson_as_gdf(Path(args.earthquakes))
    plates = load_geojson_as_gdf(Path(args.plates))
    _ = load_geojson_as_gdf(Path(args.boundaries))  # validated, not directly used

    # Drop earthquakes with no geometry and ensure WGS84 lat/lon.
    earthquakes = earthquakes[earthquakes.geometry.notna()].copy()
    earthquakes = earthquakes.set_crs("EPSG:4326", allow_override=True)
    plates = plates.set_crs("EPSG:4326", allow_override=True)

    target_plate = find_plate(plates, args.plate)
    target_index = target_plate.name  # pandas row index, preserved by to_crs

    # Project to a plate-centered CRS BEFORE spatial ops. This handles the
    # antimeridian for the Pacific plate cleanly and gives planar metres.
    plates_proj = plates.to_crs(args.crs)
    earthquakes_proj = earthquakes.to_crs(args.crs)

    plate_polygon = plates_proj.loc[target_index].geometry
    plate_boundary = plate_polygon.boundary

    inside_mask = earthquakes_proj.geometry.within(plate_polygon)
    inside = earthquakes_proj[inside_mask].copy()
    if inside.empty:
        raise RuntimeError("No earthquakes found inside the selected plate.")

    inside["distance_m"] = inside.geometry.distance(plate_boundary)
    winner_idx = inside["distance_m"].idxmax()
    winner_proj = inside.loc[winner_idx]
    winner_wgs84 = earthquakes.loc[winner_idx]

    answer = {
        "id": extract_id(winner_wgs84),
        "place": winner_wgs84.get("place"),
        "time": epoch_ms_to_iso8601_z(winner_wgs84.get("time")),
        "magnitude": extract_magnitude(winner_wgs84),
        "latitude": float(winner_wgs84.geometry.y),
        "longitude": float(winner_wgs84.geometry.x),
        "distance_km": round(float(winner_proj["distance_m"]) / 1000.0, 2),
    }

    Path(args.out).write_text(json.dumps(answer, indent=2))
    print(json.dumps(answer, indent=2))


if __name__ == "__main__":
    main()

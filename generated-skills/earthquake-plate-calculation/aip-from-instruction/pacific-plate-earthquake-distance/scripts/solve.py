#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "geopandas>=0.14",
#     "shapely>=2.0",
#     "pyproj>=3.6",
# ]
# ///
"""Find the earthquake furthest from the Pacific plate boundary, inside that plate.

Pipeline
--------
1. Load USGS-format earthquakes GeoJSON as a GeoDataFrame of points (EPSG:4326).
2. Load PB2002 plates polygons; pick the Pacific plate (default code 'PA').
3. Spatial-filter earthquakes to those that fall inside the Pacific polygon.
4. Load PB2002 boundary lines and filter to Pacific-adjacent segments (boundary
   pairs that mention the Pacific plate code). Fall back to the polygon's own
   boundary if the boundary file cannot be filtered (mathematically equivalent
   for points inside the Pacific).
5. Reproject quakes and boundaries to a Pacific-centered Azimuthal Equidistant
   CRS so distances are in metres and the antimeridian-spanning Pacific stays
   intact.
6. Compute distance from each quake to the unioned boundary geometry.
7. Pick the max-distance quake, format ISO 8601 time, round km to 2 decimals,
   write the result JSON.

Default paths match the task spec (/root/...); override via CLI flags for tests.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
from shapely.geometry import Point


# Pacific-centered Azimuthal Equidistant — keeps the Pacific polygon contiguous
# (the projection seam runs through Africa, not the dateline) and gives metric
# distances. Distortion grows with distance from the centre; for the Pacific
# plate the worst case is a few percent, which is well below the gaps between
# candidate "furthest" quakes.
PACIFIC_AEQD = (
    "+proj=aeqd +lat_0=0 +lon_0=-160 +x_0=0 +y_0=0 "
    "+datum=WGS84 +units=m +no_defs"
)


def load_earthquakes(path: Path) -> gpd.GeoDataFrame:
    """Parse a USGS-style earthquakes GeoJSON FeatureCollection into a GDF."""
    with open(path) as f:
        data = json.load(f)

    rows = []
    for feat in data.get("features", []):
        props = feat.get("properties", {}) or {}
        geom = feat.get("geometry") or {}
        coords = geom.get("coordinates") or [None, None]
        lon, lat = coords[0], coords[1]
        if lon is None or lat is None:
            continue
        rows.append(
            {
                "id": feat.get("id") or props.get("id") or props.get("ids"),
                "place": props.get("place"),
                "time_ms": props.get("time"),
                "magnitude": props.get("mag"),
                "latitude": float(lat),
                "longitude": float(lon),
                "geometry": Point(float(lon), float(lat)),
            }
        )
    if not rows:
        raise SystemExit(f"No features parsed from {path}")
    return gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326")


def _first_present(columns, candidates):
    for c in candidates:
        if c in columns:
            return c
    return None


def load_pacific_polygon(path: Path, code: str = "PA") -> gpd.GeoDataFrame:
    """Read PB2002 plates and return the Pacific plate as a single-row GDF."""
    gdf = gpd.read_file(path)
    name_field = _first_present(
        gdf.columns,
        ["PlateName", "plate_name", "Name", "NAME", "name", "PLATE", "plate"],
    )
    code_field = _first_present(
        gdf.columns,
        ["Code", "CODE", "code", "PlateCode", "PLATE_ID", "plate_id"],
    )

    pacific_aliases = {code, code.upper(), code.lower(), "Pacific", "PACIFIC", "pacific"}

    selected = gdf.iloc[0:0]
    for field in (code_field, name_field):
        if field is None:
            continue
        mask = gdf[field].astype(str).isin(pacific_aliases)
        if mask.any():
            selected = gdf[mask]
            break

    if selected.empty and name_field is not None:
        # Looser match — "Pacific Plate" etc.
        mask = gdf[name_field].astype(str).str.contains(
            r"\bpacific\b", case=False, regex=True, na=False
        )
        selected = gdf[mask]

    if selected.empty:
        raise SystemExit(
            f"Could not identify Pacific plate in {path}. "
            f"Columns: {list(gdf.columns)}"
        )
    return selected.to_crs("EPSG:4326")


def load_pacific_boundaries(
    path: Path, pacific_polygon: gpd.GeoDataFrame, code: str = "PA"
) -> gpd.GeoSeries:
    """Return PB2002 boundary lines that belong to the Pacific plate.

    Prefers attribute filtering (PlateA/PlateB or a 'PA-XX' name field). If no
    such columns are found, falls back to the Pacific polygon's own boundary —
    that's exactly equivalent in the only place it matters here: the nearest
    plate-boundary point to a quake inside the Pacific plate is on the Pacific
    boundary, by topology.
    """
    gdf = gpd.read_file(path)

    name_field = _first_present(gdf.columns, ["Name", "NAME", "name", "Boundary", "BNDR_NAME"])
    pa_field = _first_present(gdf.columns, ["PlateA", "plateA", "plate_a", "PLATEA"])
    pb_field = _first_present(gdf.columns, ["PlateB", "plateB", "plate_b", "PLATEB"])

    selected = gdf.iloc[0:0]
    if pa_field and pb_field:
        mask = (gdf[pa_field].astype(str) == code) | (gdf[pb_field].astype(str) == code)
        selected = gdf[mask]
    if selected.empty and name_field is not None:
        pattern = rf"(^|[^A-Za-z]){code}([^A-Za-z]|$)"
        mask = gdf[name_field].astype(str).str.contains(pattern, regex=True, na=False)
        selected = gdf[mask]

    if not selected.empty:
        return selected.to_crs("EPSG:4326").geometry

    # Fallback: polygon boundary
    return gpd.GeoSeries(
        [pacific_polygon.geometry.union_all().boundary], crs="EPSG:4326"
    )


def ms_to_iso8601(ms) -> str | None:
    if ms is None:
        return None
    dt = datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def solve(
    earthquakes_path: Path,
    plates_path: Path,
    boundaries_path: Path,
    output_path: Path,
    pacific_code: str = "PA",
) -> dict:
    quakes = load_earthquakes(earthquakes_path)
    pacific = load_pacific_polygon(plates_path, pacific_code)

    # Within-plate filter in geographic CRS — shapely respects the polygon as
    # drawn; PB2002 polygons handle the antimeridian internally.
    pacific_geom = pacific.geometry.union_all()
    inside = quakes[quakes.geometry.within(pacific_geom)].copy()
    if inside.empty:
        raise SystemExit("No earthquakes fall inside the Pacific plate polygon.")

    # Project quakes and boundary to Pacific-centered AEQD for metric distance.
    pacific_boundaries = load_pacific_boundaries(boundaries_path, pacific, pacific_code)
    boundary_proj = pacific_boundaries.to_crs(PACIFIC_AEQD).union_all()
    inside_proj = inside.to_crs(PACIFIC_AEQD)

    inside_proj["distance_m"] = inside_proj.geometry.distance(boundary_proj)
    winner = inside_proj.loc[inside_proj["distance_m"].idxmax()]

    answer = {
        "id": winner["id"],
        "place": winner["place"],
        "time": ms_to_iso8601(winner["time_ms"]),
        "magnitude": float(winner["magnitude"]) if winner["magnitude"] is not None else None,
        "latitude": float(winner["latitude"]),
        "longitude": float(winner["longitude"]),
        "distance_km": round(float(winner["distance_m"]) / 1000.0, 2),
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(answer, f, indent=2)
    return answer


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--earthquakes", default="/root/earthquakes_2024.json")
    p.add_argument("--plates", default="/root/PB2002_plates.json")
    p.add_argument("--boundaries", default="/root/PB2002_boundaries.json")
    p.add_argument("--output", default="/root/answer.json")
    p.add_argument("--pacific-code", default="PA")
    args = p.parse_args(argv)

    answer = solve(
        Path(args.earthquakes),
        Path(args.plates),
        Path(args.boundaries),
        Path(args.output),
        args.pacific_code,
    )
    print(json.dumps(answer, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

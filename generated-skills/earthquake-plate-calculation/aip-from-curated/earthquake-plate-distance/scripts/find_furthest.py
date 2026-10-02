#!/usr/bin/env python3
"""Find the earthquake inside a target tectonic plate that is furthest from
that plate's boundaries.

Reads one JSON object from stdin with keys:
  earthquakes_path      Path to a USGS GeoJSON FeatureCollection of earthquakes.
  plates_path           Path to a PB2002-style plates GeoJSON (polygons).
  boundaries_path       Path to a PB2002-style boundaries GeoJSON (lines).
  output_path           Where to write the answer JSON.
  plate_name            Value to match in the plates layer's PlateName column
                        (e.g. "Pacific").
  boundary_name_pattern Substring to match in the boundaries layer's Name
                        column so only that plate's boundary segments are
                        used (e.g. "PA" for the Pacific plate).

Writes the answer to output_path and echoes it back on stdout under `result`.
"""

import json
import sys
from datetime import datetime, timezone

import geopandas as gpd
from shapely.geometry import Point

METRIC_CRS = "EPSG:4087"


def load_earthquakes(path):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    rows = []
    for feat in data["features"]:
        props = feat["properties"]
        coords = feat["geometry"]["coordinates"]
        rows.append(
            {
                "id": feat["id"],
                "place": props["place"],
                "time": props["time"],
                "mag": props["mag"],
                "longitude": coords[0],
                "latitude": coords[1],
                "depth": coords[2] if len(coords) > 2 else None,
            }
        )
    return rows


def main():
    payload = json.load(sys.stdin)
    state = payload.get("currentState", {})

    earthquakes_path = state["earthquakes_path"]
    plates_path = state["plates_path"]
    boundaries_path = state["boundaries_path"]
    output_path = state["output_path"]
    plate_name = state["plate_name"]
    boundary_pattern = state["boundary_name_pattern"]

    quakes = load_earthquakes(earthquakes_path)
    gdf_plates = gpd.read_file(plates_path)
    gdf_boundaries = gpd.read_file(boundaries_path)

    geometry = [Point(q["longitude"], q["latitude"]) for q in quakes]
    gdf_eq = gpd.GeoDataFrame(quakes, geometry=geometry, crs="EPSG:4326")

    target_poly = gdf_plates[gdf_plates["PlateName"] == plate_name].geometry.unary_union
    inside = gdf_eq[gdf_eq.within(target_poly)].copy()
    if len(inside) == 0:
        raise SystemExit(f"No earthquakes found within plate PlateName={plate_name!r}")

    inside_proj = inside.to_crs(METRIC_CRS)
    plate_bounds = (
        gdf_boundaries[gdf_boundaries["Name"].str.contains(boundary_pattern)]
        .to_crs(METRIC_CRS)
        .geometry.unary_union
    )
    inside["distance_km"] = inside_proj.geometry.distance(plate_bounds) / 1000.0

    furthest = inside.nlargest(1, "distance_km").iloc[0]
    time_iso = datetime.fromtimestamp(furthest["time"] / 1000.0, tz=timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )

    result = {
        "id": furthest["id"],
        "place": furthest["place"],
        "time": time_iso,
        "magnitude": furthest["mag"],
        "latitude": furthest["latitude"],
        "longitude": furthest["longitude"],
        "distance_km": round(float(furthest["distance_km"]), 2),
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    json.dump({"result": result, "output_path": output_path}, sys.stdout)


if __name__ == "__main__":
    main()

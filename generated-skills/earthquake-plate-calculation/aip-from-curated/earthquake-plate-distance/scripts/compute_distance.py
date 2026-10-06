#!/usr/bin/env python3
"""Compute earthquake-to-plate-boundary distances using geopandas.

Reads one JSON object on stdin:
  {"currentState": {
       "earthquakes_path": "...",   # GeoJSON FeatureCollection of earthquakes (USGS format)
       "plates_path": "...",        # GeoJSON FeatureCollection with Code / PlateName
       "boundaries_path": "...",    # GeoJSON FeatureCollection with Name / PlateA / PlateB
       "plate_code": "PA",         # 2-letter PB2002 plate code to filter earthquakes into
       "metric": "furthest",       # one of: furthest, nearest, mean, median
       "boundary_scope": "plate"    # one of: plate (only boundaries that touch plate_code), all
   }, ...}

Writes one JSON object with keys:
  plate_code, plate_name, n_earthquakes_in_plate, metric,
  distance_km, earthquake (details of the extremum when applicable),
  summary (one-line human sentence).
"""
import json
import sys

import geopandas as gpd
from shapely.geometry import Point

METRIC_CRS = "EPSG:4087"


def load_earthquakes(path: str) -> gpd.GeoDataFrame:
    with open(path) as f:
        raw = json.load(f)
    rows = []
    geom = []
    for feat in raw.get("features", []):
        g = feat.get("geometry") or {}
        coords = g.get("coordinates") or []
        if g.get("type") != "Point" or len(coords) < 2:
            continue
        lon, lat = coords[0], coords[1]
        depth = coords[2] if len(coords) > 2 else None
        props = feat.get("properties") or {}
        rows.append(
            {
                "id": feat.get("id"),
                "mag": props.get("mag"),
                "place": props.get("place"),
                "time": props.get("time"),
                "depth_km": depth,
                "longitude": lon,
                "latitude": lat,
            }
        )
        geom.append(Point(lon, lat))
    gdf = gpd.GeoDataFrame(rows, geometry=geom, crs="EPSG:4326")
    return gdf[gdf.geometry.notna()].copy()


def main() -> None:
    payload = json.load(sys.stdin)
    state = payload.get("currentState", {})

    earthquakes_path = state["earthquakes_path"]
    plates_path = state["plates_path"]
    boundaries_path = state["boundaries_path"]
    plate_code = state["plate_code"]
    metric = state.get("metric", "furthest")
    boundary_scope = state.get("boundary_scope", "plate")

    gdf_eq = load_earthquakes(earthquakes_path)
    gdf_plates = gpd.read_file(plates_path)
    gdf_boundaries = gpd.read_file(boundaries_path)

    plate_rows = gdf_plates[gdf_plates["Code"] == plate_code]
    if plate_rows.empty:
        raise SystemExit(f"plate_code {plate_code!r} not found in plates file")
    plate_name = str(plate_rows.iloc[0]["PlateName"])
    plate_geom = plate_rows.geometry.union_all()

    eq_in_plate = gdf_eq[gdf_eq.within(plate_geom)].copy()
    n_in_plate = int(len(eq_in_plate))
    if n_in_plate == 0:
        out = {
            "plate_code": plate_code,
            "plate_name": plate_name,
            "n_earthquakes_in_plate": 0,
            "metric": metric,
            "distance_km": float("nan"),
            "earthquake": {},
            "summary": f"No earthquakes fall inside the {plate_name} plate ({plate_code}).",
        }
        json.dump(out, sys.stdout, allow_nan=True)
        return

    if boundary_scope == "all":
        bounds_subset = gdf_boundaries
    else:
        mask = (gdf_boundaries["PlateA"] == plate_code) | (gdf_boundaries["PlateB"] == plate_code)
        bounds_subset = gdf_boundaries[mask]
    if bounds_subset.empty:
        raise SystemExit(f"no boundaries found for plate_code {plate_code!r} under scope {boundary_scope!r}")

    eq_proj = eq_in_plate.to_crs(METRIC_CRS)
    bounds_proj_geom = bounds_subset.to_crs(METRIC_CRS).geometry.union_all()

    distances_m = eq_proj.geometry.distance(bounds_proj_geom)
    eq_in_plate["distance_km"] = (distances_m / 1000.0).values

    if metric == "furthest":
        pick = eq_in_plate.nlargest(1, "distance_km").iloc[0]
    elif metric == "nearest":
        pick = eq_in_plate.nsmallest(1, "distance_km").iloc[0]
    elif metric in ("mean", "median"):
        value_km = float(eq_in_plate["distance_km"].mean() if metric == "mean" else eq_in_plate["distance_km"].median())
        out = {
            "plate_code": plate_code,
            "plate_name": plate_name,
            "n_earthquakes_in_plate": n_in_plate,
            "metric": metric,
            "distance_km": value_km,
            "earthquake": {},
            "summary": (
                f"{metric.capitalize()} distance of {n_in_plate} earthquake(s) inside the "
                f"{plate_name} plate ({plate_code}) to its boundaries: {value_km:.2f} km."
            ),
        }
        json.dump(out, sys.stdout)
        return
    else:
        raise SystemExit(f"unknown metric: {metric!r}")

    def _opt_float(v):
        return None if v is None else float(v)

    def _opt_int(v):
        return None if v is None else int(v)

    quake = {
        "id": None if pick.get("id") is None else str(pick["id"]),
        "mag": _opt_float(pick.get("mag")),
        "place": None if pick.get("place") is None else str(pick["place"]),
        "time": _opt_int(pick.get("time")),
        "depth_km": _opt_float(pick.get("depth_km")),
        "longitude": float(pick["longitude"]),
        "latitude": float(pick["latitude"]),
    }
    distance_km = float(pick["distance_km"])
    which = "furthest from" if metric == "furthest" else "nearest to"
    out = {
        "plate_code": plate_code,
        "plate_name": plate_name,
        "n_earthquakes_in_plate": n_in_plate,
        "metric": metric,
        "distance_km": distance_km,
        "earthquake": quake,
        "summary": (
            f"Among {n_in_plate} earthquake(s) inside the {plate_name} plate ({plate_code}), "
            f"{quake['id']} (M{quake['mag']}, {quake['place']}) is {which} the plate boundaries "
            f"at {distance_km:.2f} km."
        ),
    }
    json.dump(out, sys.stdout)


if __name__ == "__main__":
    main()

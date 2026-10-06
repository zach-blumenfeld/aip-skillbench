#!/usr/bin/env python3
"""Compute distance from each earthquake inside a given PB2002 plate to that
plate's boundary, in kilometres, and return the top-N by extremum.

Pipeline (from the curated geospatial-analysis skill):
  1. Load plates / boundaries / earthquakes as GeoDataFrames in EPSG:4326.
  2. Filter plates to the target code (or name) and union_all its geometry.
  3. Spatial-filter earthquakes with `.within()` on the plate polygon.
  4. Project earthquakes and boundaries to EPSG:4087 (equidistant metric CRS).
  5. Filter boundaries involving the plate (PlateA/PlateB match, or Name
     substring) and union_all their geometries.
  6. Distance from each projected earthquake to the boundary union (metres),
     convert to kilometres.
  7. nlargest / nsmallest `top_n`, serialise to JSON-safe records.
"""

from __future__ import annotations

import json
import math
import sys
from typing import Any

import geopandas as gpd
from shapely.geometry import Point

METRIC_CRS = "EPSG:4087"
GEOGRAPHIC_CRS = "EPSG:4326"


def _union_all(gdf: gpd.GeoDataFrame):
    try:
        return gdf.geometry.union_all()
    except AttributeError:
        return gdf.geometry.unary_union


def _load_geojson(path: str) -> gpd.GeoDataFrame:
    gdf = gpd.read_file(path)
    if gdf.crs is None:
        gdf = gdf.set_crs(GEOGRAPHIC_CRS)
    return gdf


def _load_earthquakes(path: str) -> gpd.GeoDataFrame:
    """Earthquakes may be a GeoJSON FeatureCollection or a plain JSON array of
    records with latitude/longitude fields. Try GeoJSON first."""
    try:
        gdf = gpd.read_file(path)
        if "geometry" in gdf.columns and gdf.geometry.notna().any():
            if gdf.crs is None:
                gdf = gdf.set_crs(GEOGRAPHIC_CRS)
            return gdf
    except Exception:
        pass

    with open(path) as fh:
        data = json.load(fh)

    if isinstance(data, dict) and data.get("type") == "FeatureCollection":
        records = []
        for feat in data.get("features", []):
            props = dict(feat.get("properties") or {})
            geom = feat.get("geometry") or {}
            if geom.get("type") == "Point":
                lon, lat = geom["coordinates"][:2]
                props.setdefault("longitude", lon)
                props.setdefault("latitude", lat)
                records.append(props)
    elif isinstance(data, list):
        records = [r for r in data if isinstance(r, dict)]
    else:
        raise ValueError(f"Unrecognised earthquakes format in {path}")

    if not records:
        return gpd.GeoDataFrame(columns=["geometry"], geometry="geometry", crs=GEOGRAPHIC_CRS)

    sample = records[0]
    lat_key = next((k for k in ("latitude", "lat", "Latitude", "LAT") if k in sample), None)
    lon_key = next((k for k in ("longitude", "lon", "lng", "Longitude", "LON", "LNG") if k in sample), None)
    if lat_key is None or lon_key is None:
        raise ValueError(
            f"Could not find latitude/longitude keys in {path}; sample keys: {list(sample)[:20]}"
        )

    geometry = [Point(float(r[lon_key]), float(r[lat_key])) for r in records]
    return gpd.GeoDataFrame(records, geometry=geometry, crs=GEOGRAPHIC_CRS)


def _filter_plate(gdf_plates: gpd.GeoDataFrame, plate_code: str) -> gpd.GeoDataFrame:
    code = str(plate_code).strip()
    for col in ("Code", "code", "PlateCode", "PLATE_CODE"):
        if col in gdf_plates.columns:
            matched = gdf_plates[gdf_plates[col].astype(str).str.upper() == code.upper()]
            if len(matched) > 0:
                return matched
    for col in ("PlateName", "Name", "name", "PLATE_NAME"):
        if col in gdf_plates.columns:
            matched = gdf_plates[
                gdf_plates[col].astype(str).str.contains(code, case=False, na=False)
            ]
            if len(matched) > 0:
                return matched
    return gdf_plates.iloc[0:0]


def _filter_boundaries(
    gdf_boundaries: gpd.GeoDataFrame, plate_code: str
) -> gpd.GeoDataFrame:
    code = str(plate_code).strip().upper()
    cols = set(gdf_boundaries.columns)
    if {"PlateA", "PlateB"}.issubset(cols):
        matched = gdf_boundaries[
            (gdf_boundaries["PlateA"].astype(str).str.upper() == code)
            | (gdf_boundaries["PlateB"].astype(str).str.upper() == code)
        ]
        if len(matched) > 0:
            return matched
    for col in ("Name", "name", "BoundaryName"):
        if col in cols:
            matched = gdf_boundaries[
                gdf_boundaries[col].astype(str).str.contains(code, case=False, na=False)
            ]
            if len(matched) > 0:
                return matched
    return gdf_boundaries


def _jsonable(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return value
    if hasattr(value, "item"):
        try:
            return _jsonable(value.item())
        except Exception:
            return str(value)
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        return str(value)


def _row_to_record(row) -> dict:
    rec: dict = {}
    for col, val in row.items():
        if col == "geometry":
            if val is not None and hasattr(val, "x") and hasattr(val, "y"):
                rec.setdefault("longitude", float(val.x))
                rec.setdefault("latitude", float(val.y))
            continue
        rec[str(col)] = _jsonable(val)
    return rec


def main() -> None:
    payload = json.load(sys.stdin)
    state = payload.get("currentState", payload)

    plates_path = state["plates_path"]
    boundaries_path = state["boundaries_path"]
    earthquakes_path = state["earthquakes_path"]
    plate_code = str(state["plate_code"]).strip()
    extremum = str(state.get("extremum", "furthest")).strip().lower()
    if extremum not in ("furthest", "closest"):
        extremum = "furthest"
    top_n = max(1, int(state.get("top_n", 1)))

    gdf_plates = _load_geojson(plates_path)
    gdf_boundaries = _load_geojson(boundaries_path)
    gdf_eq = _load_earthquakes(earthquakes_path)
    gdf_eq = gdf_eq[gdf_eq.geometry.notna()].copy()

    plate_sel = _filter_plate(gdf_plates, plate_code)
    if len(plate_sel) == 0:
        preview = []
        for col in ("Code", "code", "PlateName", "Name", "name"):
            if col in gdf_plates.columns:
                preview = sorted({str(x) for x in gdf_plates[col].dropna().unique()})[:30]
                break
        raise SystemExit(
            f"No plate matched '{plate_code}'. Available plate identifiers (sample): {preview}"
        )

    plate_geom = _union_all(plate_sel)
    eq_in_plate = gdf_eq[gdf_eq.within(plate_geom)].copy()
    count_in_plate = int(len(eq_in_plate))

    if count_in_plate == 0:
        print(json.dumps({
            "count_in_plate": 0,
            "top_results": [],
            "plate_code": plate_code,
            "extremum": extremum,
            "top_n": top_n,
        }))
        return

    eq_proj = eq_in_plate.to_crs(METRIC_CRS)

    boundaries_sel = _filter_boundaries(gdf_boundaries, plate_code)
    boundaries_proj = boundaries_sel.to_crs(METRIC_CRS)
    boundary_geom = _union_all(boundaries_proj)

    distances_m = eq_proj.geometry.distance(boundary_geom).values
    eq_in_plate["distance_km"] = distances_m / 1000.0

    if extremum == "furthest":
        picked = eq_in_plate.nlargest(top_n, "distance_km")
    else:
        picked = eq_in_plate.nsmallest(top_n, "distance_km")

    results = [_row_to_record(row) for _, row in picked.iterrows()]

    print(json.dumps({
        "count_in_plate": count_in_plate,
        "top_results": results,
        "plate_code": plate_code,
        "extremum": extremum,
        "top_n": top_n,
    }))


if __name__ == "__main__":
    main()

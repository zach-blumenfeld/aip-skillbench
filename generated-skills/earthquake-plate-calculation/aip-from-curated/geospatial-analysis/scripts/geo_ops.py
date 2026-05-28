"""Geospatial helpers for point/polygon/line analysis on Earth.

Bundles the workflow described in `SKILL.md`:

1. Load source data into a GeoDataFrame in EPSG:4326 (canonical storage CRS).
2. Filter points by polygon membership (`.within` against `.unary_union`).
3. Compute point→geometry distances correctly by projecting to a metric CRS
   (EPSG:4087, World Equidistant Cylindrical) before calling `.distance()`.
4. Pick the furthest / closest rows with nlargest / nsmallest.

The central rule the helpers enforce: distance work happens in a *metric*
CRS, never in EPSG:4326. A degree of longitude at the equator is ~111 km
but shrinks toward the poles; `.distance()` in EPSG:4326 returns degrees,
not metres, and is silently wrong.

Run from a skill consumer:

    import sys
    sys.path.insert(0, "<skill-root>/scripts")
    from geo_ops import (
        load_geojson,
        points_from_records,
        filter_points_within,
        distance_km_to,
        extreme_by_distance,
    )
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Optional, Sequence, Union

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point


STORAGE_CRS = "EPSG:4326"      # WGS84 lat/lon — how source data is stored.
METRIC_CRS = "EPSG:4087"       # World Equidistant Cylindrical — metres.


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def load_geojson(path: str) -> gpd.GeoDataFrame:
    """Load a GeoJSON (or any geopandas-readable) file as a GeoDataFrame.

    A thin wrapper around `gpd.read_file` so the load step has a single
    documented entry point. The returned GeoDataFrame keeps whatever CRS
    the file declares — assume EPSG:4326 unless the source says otherwise.
    """
    return gpd.read_file(path)


def points_from_records(
    records: Sequence[Mapping[str, Any]],
    lat_key: str = "latitude",
    lon_key: str = "longitude",
    crs: str = STORAGE_CRS,
) -> gpd.GeoDataFrame:
    """Build a point GeoDataFrame from a list of dict records.

    Each record must carry latitude and longitude under `lat_key` / `lon_key`
    (default `"latitude"` / `"longitude"`; common alternates: `"lat"`/`"lon"`).
    The output is in `crs` (default EPSG:4326). All non-coordinate fields
    are preserved as attribute columns.
    """
    if not records:
        return gpd.GeoDataFrame(geometry=[], crs=crs)

    df = pd.DataFrame(list(records))
    geometry = [Point(row[lon_key], row[lat_key]) for row in records]
    return gpd.GeoDataFrame(df, geometry=geometry, crs=crs)


# ---------------------------------------------------------------------------
# Spatial filter
# ---------------------------------------------------------------------------

def _apply_where(
    gdf: gpd.GeoDataFrame,
    where: Optional[Union[pd.Series, Iterable[bool]]],
) -> gpd.GeoDataFrame:
    if where is None:
        return gdf
    return gdf[where]


def _union_geometry(gdf: gpd.GeoDataFrame):
    """Drop missing geometries and return the unary_union of the rest."""
    clean = gdf[gdf.geometry.notna()]
    return clean.geometry.unary_union


def filter_points_within(
    gdf_points: gpd.GeoDataFrame,
    gdf_polygon: gpd.GeoDataFrame,
    where: Optional[Union[pd.Series, Iterable[bool]]] = None,
) -> gpd.GeoDataFrame:
    """Return points falling inside the (optionally filtered) polygon.

    `where` is an optional boolean mask over `gdf_polygon` (e.g.
    `gdf_plates["Code"] == "PA"`). The matching polygon features are
    combined via `.unary_union` so multi-feature polygons behave as one.
    Always returns an independent copy so callers can add columns
    without triggering pandas' SettingWithCopyWarning.
    """
    target = _union_geometry(_apply_where(gdf_polygon, where))
    mask = gdf_points.geometry.within(target)
    return gdf_points[mask].copy()


# ---------------------------------------------------------------------------
# Distance
# ---------------------------------------------------------------------------

def distance_km_to(
    gdf_points: gpd.GeoDataFrame,
    gdf_target: gpd.GeoDataFrame,
    where: Optional[Union[pd.Series, Iterable[bool]]] = None,
    metric_crs: str = METRIC_CRS,
    distance_m_column: str = "distance_m",
    distance_km_column: str = "distance_km",
) -> gpd.GeoDataFrame:
    """Add point→target distance columns (metres and kilometres).

    Steps, in order:
      1. Apply `where` to `gdf_target` (e.g. boundary-substring or
         PlateA/PlateB membership), drop missing geometries.
      2. Project both inputs to `metric_crs` (default EPSG:4087).
      3. Combine the target features with `.unary_union` so the result
         is the shortest distance to the combined geometry, not to one
         arbitrary segment.
      4. Call `.distance()` and write metres + kilometres back to a copy
         of the *original* (unprojected) points so downstream code can
         keep working in EPSG:4326 if it wants to.

    The helper enforces the project-before-distance rule: never call
    `.distance()` on EPSG:4326 geometries — the result is degrees.
    """
    filtered_target = _apply_where(gdf_target, where)
    target_proj = filtered_target[filtered_target.geometry.notna()].to_crs(metric_crs)
    target_union = target_proj.geometry.unary_union

    points_proj = gdf_points.to_crs(metric_crs)
    distances_m = points_proj.geometry.distance(target_union)

    out = gdf_points.copy()
    out[distance_m_column] = distances_m.values
    out[distance_km_column] = out[distance_m_column] / 1000.0
    return out


# ---------------------------------------------------------------------------
# Extreme selection
# ---------------------------------------------------------------------------

def extreme_by_distance(
    gdf: gpd.GeoDataFrame,
    mode: str = "max",
    n: int = 1,
    column: str = "distance_km",
) -> gpd.GeoDataFrame:
    """Return the n rows with the largest (`mode='max'`) or smallest
    (`mode='min'`) value in `column`. Wraps `nlargest` / `nsmallest`.

    Always returns a GeoDataFrame slice (not a Series), even when `n == 1`.
    Use `.iloc[0]` on the result if you want a single row as a Series.
    """
    if column not in gdf.columns:
        raise KeyError(
            f"column {column!r} not present — did you forget to call "
            "distance_km_to() first?"
        )
    if mode == "max":
        return gdf.nlargest(n, column)
    if mode == "min":
        return gdf.nsmallest(n, column)
    raise ValueError(f"mode must be 'max' or 'min', got {mode!r}")

#!/usr/bin/env python3
"""Find the earthquake inside a tectonic plate that is furthest from (or closest to)
that plate's boundaries, measuring distance in a projected metric CRS with GeoPandas.

Requires: Python >= 3.10, geopandas >= 0.14 (tested 1.0.1), shapely >= 2.0, pyproj, pandas.

Method (do not change without reason; it is what "use GeoPandas projections" means):
  1. Earthquakes -> 2D Points (lon, lat) in EPSG:4326 (depth dropped).
  2. Plate polygon(s) selected by Code or PlateName, unioned; keep quakes .within() it.
  3. Boundary segments whose PlateA or PlateB is the plate code (cross-checked against
     the Name field, e.g. "PA-NA", "NA/PA", "AU\\PA"), projected to EPSG:4087, unioned.
  4. distance_km = projected point .distance(boundary union) / 1000; pick nlargest/nsmallest.

Usage:
  python scripts/plate_quake_distance.py --earthquakes /root/earthquakes_2024.json \
      --plates /root/PB2002_plates.json --boundaries /root/PB2002_boundaries.json \
      --plate PA --out /root/answer.json [--mode furthest|closest] [--crs EPSG:4087] [--top 5]
"""
import argparse
import json
import re
import sys
from datetime import datetime, timezone

try:
    import geopandas as gpd
    import pandas as pd
    from shapely import affinity
    from shapely.geometry import Point
except ImportError as exc:  # pragma: no cover
    sys.exit(f"ERROR: missing package ({exc}). Needs geopandas, shapely, pyproj, pandas.")


def die(msg):
    sys.exit(f"ERROR: {msg}")


def union(geoseries):
    # union_all() is the non-deprecated spelling of .unary_union (geopandas >= 1.0)
    return geoseries.union_all() if hasattr(geoseries, "union_all") else geoseries.unary_union


def iso_utc(value):
    """USGS time is epoch milliseconds; also accept seconds or ISO strings."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        secs = value / 1000.0 if abs(value) > 1e11 else float(value)
        dt = datetime.fromtimestamp(secs, tz=timezone.utc)
    else:
        dt = pd.Timestamp(str(value))
        dt = dt.tz_localize("UTC") if dt.tzinfo is None else dt.tz_convert("UTC")
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def first(d, *keys):
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return None


def load_earthquakes(path):
    with open(path) as fh:
        data = json.load(fh)
    if isinstance(data, dict) and "features" in data:
        items = data["features"]
    elif isinstance(data, list):
        items = data
    else:
        die(f"{path}: expected a GeoJSON FeatureCollection or a list of records")
    rows = []
    for i, it in enumerate(items):
        props = it.get("properties", it) if isinstance(it, dict) else {}
        geom = it.get("geometry") if isinstance(it, dict) else None
        if geom and geom.get("coordinates"):
            lon, lat = geom["coordinates"][0], geom["coordinates"][1]
        else:
            lon = first(props, "longitude", "lon", "lng")
            lat = first(props, "latitude", "lat")
        if lon is None or lat is None:
            continue  # no location -> cannot be placed on a plate
        rows.append({
            "id": first(it, "id") or first(props, "id", "ids", "code") or str(i),
            "place": first(props, "place", "title"),
            "time": iso_utc(first(props, "time")),
            "magnitude": first(props, "mag", "magnitude"),
            "latitude": float(lat),
            "longitude": float(lon),
        })
    if not rows:
        die(f"{path}: no earthquakes with coordinates")
    df = pd.DataFrame(rows)
    geometry = [Point(lo, la) for lo, la in zip(df.longitude, df.latitude)]
    return gpd.GeoDataFrame(df, geometry=geometry, crs="EPSG:4326")


def read_layer(path):
    gdf = gpd.read_file(path)
    gdf = gdf[gdf.geometry.notna()]
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")
    return gdf


def resolve_plate(plates, plate):
    want = plate.strip().lower()
    for col in ("Code", "PlateName"):
        if col in plates.columns:
            hit = plates[plates[col].astype(str).str.strip().str.lower() == want]
            if len(hit):
                code = hit["Code"].iloc[0] if "Code" in hit.columns else plate
                name = hit["PlateName"].iloc[0] if "PlateName" in hit.columns else plate
                return hit, str(code), str(name)
    opts = plates[[c for c in ("Code", "PlateName") if c in plates.columns]].drop_duplicates()
    die(f"plate '{plate}' not found by Code or PlateName. Available:\n{opts.to_string(index=False)}")


def plate_boundaries(bounds, code):
    by_cols = None
    if {"PlateA", "PlateB"} <= set(bounds.columns):
        by_cols = (bounds["PlateA"] == code) | (bounds["PlateB"] == code)
    by_name = None
    if "Name" in bounds.columns:
        # Name separators in PB2002: "-", "/", "\" (e.g. "PA-NA", "NA/PA", "AU\PA")
        by_name = bounds["Name"].astype(str).apply(lambda n: code in re.split(r"[-/\\\s]+", n))
    if by_cols is None and by_name is None:
        die("boundaries file has neither PlateA/PlateB nor Name columns")
    if by_cols is not None and by_name is not None and not by_cols.equals(by_name):
        print(f"WARNING: PlateA/PlateB selects {int(by_cols.sum())} segments, Name selects "
              f"{int(by_name.sum())}; using their union", file=sys.stderr)
        mask = by_cols | by_name
    else:
        mask = by_cols if by_cols is not None else by_name
    sel = bounds[mask]
    if sel.empty:
        die(f"no boundary segments involve plate code '{code}'")
    return sel


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--earthquakes", required=True)
    ap.add_argument("--plates", required=True)
    ap.add_argument("--boundaries", required=True)
    ap.add_argument("--plate", default="PA", help="plate Code (PA) or PlateName (Pacific)")
    ap.add_argument("--mode", choices=["furthest", "closest"], default="furthest")
    ap.add_argument("--crs", default="EPSG:4087", help="projected metric CRS for distances")
    ap.add_argument("--top", type=int, default=5, help="ranked candidates to print")
    ap.add_argument("--out", help="write the answer JSON here")
    a = ap.parse_args()

    eq = load_earthquakes(a.earthquakes)
    plates = read_layer(a.plates)
    bounds = read_layer(a.boundaries)

    plate_rows, code, name = resolve_plate(plates, a.plate)
    plate_poly = union(plate_rows.to_crs("EPSG:4326").geometry)
    inside = eq[eq.within(plate_poly)].copy()
    print(f"plate {code} ({name}): {len(plate_rows)} polygon feature(s); "
          f"{len(inside)} of {len(eq)} earthquakes within it", file=sys.stderr)
    if inside.empty:
        die(f"no earthquakes fall within plate {code}")

    sel = plate_boundaries(bounds, code)
    boundary = union(sel.to_crs(a.crs).geometry)
    inside["distance_km"] = inside.to_crs(a.crs).geometry.distance(boundary) / 1000.0
    print(f"{len(sel)} boundary segments involve {code}; distances in {a.crs}", file=sys.stderr)

    pick = inside.nlargest if a.mode == "furthest" else inside.nsmallest
    ranked = pick(max(a.top, 1), "distance_km")
    cols = ["id", "magnitude", "time", "latitude", "longitude", "distance_km", "place"]
    print(ranked[cols].to_string(index=False), file=sys.stderr)

    best = ranked.iloc[0]
    mag = best["magnitude"]
    answer = {
        "id": str(best["id"]),
        "place": best["place"],
        "time": best["time"],
        "magnitude": None if pd.isna(mag) else float(mag),
        "latitude": float(best["latitude"]),
        "longitude": float(best["longitude"]),
        "distance_km": round(float(best["distance_km"]), 2),
    }
    # A flat projection cuts the globe at +/-180, so boundaries just across the antimeridian
    # look far away. Diagnostic only: re-measure the winner against copies of the boundary
    # shifted one world-width east/west. The answer keeps the plain projected distance.
    xmin, _, xmax, _ = gpd.GeoSeries([Point(-180, 0), Point(180, 0)], crs="EPSG:4326").to_crs(a.crs).total_bounds
    width = xmax - xmin
    pt = gpd.GeoSeries([best.geometry], crs="EPSG:4326").to_crs(a.crs).iloc[0]
    wrap_km = min(pt.distance(affinity.translate(boundary, xoff=s)) for s in (-width, width)) / 1000.0
    if wrap_km < answer["distance_km"]:
        print(f"NOTE: across the antimeridian the boundary is {wrap_km:.2f} km away "
              f"(< {answer['distance_km']:.2f} km); reported value is the plain {a.crs} distance",
              file=sys.stderr)

    text = json.dumps(answer, indent=2, ensure_ascii=False)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
        print(f"wrote {a.out}", file=sys.stderr)
    print(text)


if __name__ == "__main__":
    main()

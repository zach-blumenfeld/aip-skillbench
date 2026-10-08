"""Find the earthquake inside a tectonic plate that is furthest from (or nearest to)
that plate's boundaries, using geopandas with a metric projection.

stdin:  {"currentState": {...}, "assets": {...}, "expects": [...]}
stdout: one JSON object merged over the state.

Method (from the geospatial-analysis source skill):
  1. Load the earthquake GeoJSON, the PB2002 plate polygons and the PB2002 boundary lines.
  2. Resolve the target plate by Code or PlateName and union its polygon(s).
  3. Keep earthquakes strictly `.within()` that polygon (EPSG:4326, no manual lon fixes).
  4. Select the boundary segments that involve the plate (PlateA/PlateB == code, or the
     code is a token of Name), or every boundary when boundary_scope == "any".
  5. Project points and boundaries to EPSG:4087 (metres), union the boundaries once,
     one vectorised `.distance()` call, divide by 1000 -> km.
  6. nlargest / nsmallest picks the answer.
"""
import json
import math
import os
import re
import sys
from datetime import datetime, timezone

METRIC_CRS = "EPSG:4087"   # World Equidistant Cylindrical, metres
GEO_CRS = "EPSG:4326"
TOP_N = 5


def fail(msg):
    sys.stderr.write(msg + "\n")
    sys.exit(1)


try:
    import geopandas as gpd
    import pandas as pd
    from shapely.geometry import Point
except ImportError as e:  # pragma: no cover
    fail(f"geopandas/shapely/pandas are required (pip install geopandas shapely pyproj): {e}")


def union(geoseries):
    # geopandas >= 1.0 deprecates unary_union in favour of union_all
    return geoseries.union_all() if hasattr(geoseries, "union_all") else geoseries.unary_union


def resolve_path(p, label):
    if not p:
        fail(f"{label} is empty")
    p = os.path.expanduser(str(p))
    candidates = [p]
    if not os.path.isabs(p):
        for base in (os.environ.get("PWD"), "/root", os.getcwd()):
            if base:
                candidates.append(os.path.join(base, p))
    for c in candidates:
        if os.path.isfile(c):
            return os.path.abspath(c)
    fail(f"{label} not found: {p} (tried {candidates}); pass an absolute path")


def load_json(path, label):
    try:
        with open(path, encoding="utf-8-sig") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        fail(f"{label} at {path} is not valid JSON: {e}")


def to_float(v):
    try:
        f = float(v)
        return f if math.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def iso_time(v):
    """USGS `time` is epoch milliseconds; pass strings through."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return datetime.fromtimestamp(v / 1000.0, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    return str(v)


def parse_time_bound(v):
    """Accept ISO date/datetime strings or epoch ms; return epoch ms or None."""
    if v in (None, ""):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace("Z", "+00:00")
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp() * 1000.0


def load_earthquakes(path):
    """USGS FeatureCollection -> GeoDataFrame (EPSG:4326). Also accepts a plain list
    of records with latitude/longitude keys."""
    data = load_json(path, "earthquakes file")
    rows = []
    skipped = 0
    if isinstance(data, dict) and isinstance(data.get("features"), list):
        for i, feat in enumerate(data["features"]):
            props = dict(feat.get("properties") or {})
            geom = feat.get("geometry") or {}
            coords = geom.get("coordinates") if geom.get("type") == "Point" else None
            lon = to_float(coords[0]) if coords and len(coords) > 1 else None
            lat = to_float(coords[1]) if coords and len(coords) > 1 else None
            depth = to_float(coords[2]) if coords and len(coords) > 2 else None
            if lon is None or lat is None:
                skipped += 1
                continue
            rows.append({"id": feat.get("id", props.get("code", i)), "longitude": lon,
                         "latitude": lat, "depth": depth, "_props": props})
    elif isinstance(data, list):
        for i, rec in enumerate(data):
            lat = to_float(rec.get("latitude", rec.get("lat")))
            lon = to_float(rec.get("longitude", rec.get("lon")))
            if lon is None or lat is None:
                skipped += 1
                continue
            rows.append({"id": rec.get("id", i), "longitude": lon, "latitude": lat,
                         "depth": to_float(rec.get("depth")), "_props": dict(rec)})
    else:
        fail("earthquakes file is neither a GeoJSON FeatureCollection nor a list of records")
    if not rows:
        fail("earthquakes file contains no usable point features")
    gdf = gpd.GeoDataFrame(rows, geometry=[Point(r["longitude"], r["latitude"]) for r in rows], crs=GEO_CRS)
    return gdf, skipped


def apply_filters(gdf, filters):
    filters = filters or {}
    notes = []
    mags = gdf["_props"].map(lambda p: to_float(p.get("mag")))
    times = gdf["_props"].map(lambda p: to_float(p.get("time")))
    keep = pd.Series(True, index=gdf.index)
    if filters.get("min_magnitude") not in (None, ""):
        keep &= mags >= float(filters["min_magnitude"])
        notes.append(f"mag >= {filters['min_magnitude']}")
    if filters.get("max_magnitude") not in (None, ""):
        keep &= mags <= float(filters["max_magnitude"])
        notes.append(f"mag <= {filters['max_magnitude']}")
    start = parse_time_bound(filters.get("start_time"))
    end = parse_time_bound(filters.get("end_time"))
    if start is not None:
        keep &= times >= start
        notes.append(f"time >= {filters['start_time']}")
    if end is not None:
        keep &= times < end
        notes.append(f"time < {filters['end_time']} (exclusive)")
    if filters.get("event_type") not in (None, ""):
        et = str(filters["event_type"]).lower()
        keep &= gdf["_props"].map(lambda p: str(p.get("type", "")).lower() == et)
        notes.append(f"type == {et}")
    return gdf[keep.fillna(False)].copy(), notes


def resolve_plate(plates, plate):
    want = str(plate or "").strip()
    if not want:
        fail("plate is empty; give a PB2002 code (e.g. PA) or plate name (e.g. Pacific)")
    code_col = next((c for c in ("Code", "code", "CODE") if c in plates.columns), None)
    name_col = next((c for c in ("PlateName", "Name", "name", "PLATENAME") if c in plates.columns), None)
    if code_col is None and name_col is None:
        fail(f"plates file has no Code/PlateName property; columns: {list(plates.columns)}")
    w = want.lower()
    for col in (code_col, name_col):
        if col is None:
            continue
        m = plates[plates[col].astype(str).str.strip().str.lower() == w]
        if len(m):
            break
    else:
        # tolerate "Pacific Plate" / "the Pacific plate"
        w2 = re.sub(r"\b(the|plate)\b", "", w).strip()
        m = plates[plates[name_col].astype(str).str.strip().str.lower() == w2] if name_col else plates.iloc[0:0]
    if not len(m):
        avail = sorted({f"{r.get(code_col, '')}={r.get(name_col, '')}" for _, r in plates.iterrows()})
        fail(f"plate '{want}' not found in plates file. Available: {', '.join(avail)}")
    code = str(m.iloc[0][code_col]).strip() if code_col else want
    name = str(m.iloc[0][name_col]).strip() if name_col else code
    # all features of that code (a plate may be stored as several polygons)
    if code_col:
        m = plates[plates[code_col].astype(str).str.strip() == code]
    return code, name, m


def select_boundaries(bounds, code, scope):
    bounds = bounds[bounds.geometry.notna() & ~bounds.geometry.is_empty]
    if scope == "any":
        return bounds, "all boundary segments in the file"
    mask = pd.Series(False, index=bounds.index)
    for col in ("PlateA", "PlateB"):
        if col in bounds.columns:
            mask |= bounds[col].astype(str).str.strip() == code
    if "Name" in bounds.columns:
        # Name looks like "PA-NA" (sometimes "PA\NA", "PA/NA"); match the code as a whole token
        tok = bounds["Name"].astype(str).map(lambda s: code in re.split(r"[^A-Za-z0-9]+", s))
        mask |= tok
    sel = bounds[mask]
    if not len(sel):
        fail(f"no boundary segments reference plate {code} (PlateA/PlateB/Name)")
    return sel, f"segments with PlateA or PlateB == {code} or {code} as a Name token"


def record(row, dist_km):
    p = row["_props"]
    return {
        "id": row["id"],
        "place": p.get("place"),
        "time": iso_time(p.get("time")),
        "time_ms": p.get("time"),
        "magnitude": to_float(p.get("mag")),
        "mag_type": p.get("magType"),
        "latitude": row["latitude"],
        "longitude": row["longitude"],
        "depth_km": row["depth"],
        "title": p.get("title"),
        "url": p.get("url"),
        "distance_km": round(float(dist_km), 6),
    }


def main():
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError as e:
        fail(f"stdin is not JSON: {e}")
    st = payload.get("currentState", payload)

    extreme = str(st.get("extreme", "furthest")).lower()
    if extreme not in ("furthest", "nearest"):
        fail(f"extreme must be 'furthest' or 'nearest', got {extreme!r}")
    scope = str(st.get("boundary_scope", "plate")).lower()
    if scope not in ("plate", "any"):
        fail(f"boundary_scope must be 'plate' or 'any', got {scope!r}")

    eq_path = resolve_path(st.get("earthquakes_path"), "earthquakes_path")
    plates_path = resolve_path(st.get("plates_path"), "plates_path")
    bounds_path = resolve_path(st.get("boundaries_path"), "boundaries_path")

    warnings = []
    eq, skipped = load_earthquakes(eq_path)
    if skipped:
        warnings.append(f"{skipped} earthquake records lacked usable coordinates and were skipped")
    n_total = len(eq)
    eq, filter_notes = apply_filters(eq, st.get("filters"))

    plates = gpd.read_file(plates_path)
    bounds = gpd.read_file(bounds_path)
    if plates.crs is None:
        plates = plates.set_crs(GEO_CRS)
    if bounds.crs is None:
        bounds = bounds.set_crs(GEO_CRS)
    plates = plates[plates.geometry.notna()]

    code, name, plate_rows = resolve_plate(plates, st.get("plate"))
    plate_rows = plate_rows.to_crs(GEO_CRS)
    # Use the polygon as published (as the source workflow does); repair only if GEOS refuses it.
    try:
        plate_geom = union(plate_rows.geometry)
        inside = eq[eq.within(plate_geom)].copy()
    except Exception as e:  # GEOS TopologyException on a broken ring
        warnings.append(f"plate {code} polygon failed in GEOS ({e}); repaired with buffer(0)")
        plate_geom = union(plate_rows.geometry.buffer(0))
        inside = eq[eq.within(plate_geom)].copy()
    if not plate_rows.geometry.is_valid.all():
        warnings.append(f"plate {code} polygon is not OGC-valid in the source file; within() used it as is")
    if not len(inside):
        fail(f"no earthquakes (of {len(eq)} after filters) fall within plate {code} ({name})")

    sel, sel_desc = select_boundaries(bounds.to_crs(GEO_CRS), code, scope)
    boundary_geom = union(sel.to_crs(METRIC_CRS).geometry)
    inside_proj = inside.to_crs(METRIC_CRS)
    inside["distance_km"] = inside_proj.geometry.distance(boundary_geom) / 1000.0

    far = inside.nlargest(TOP_N, "distance_km")
    near = inside.nsmallest(TOP_N, "distance_km")
    chosen = (far if extreme == "furthest" else near).iloc[0]
    ranking = far if extreme == "furthest" else near
    if len(ranking) > 1 and abs(ranking.iloc[0]["distance_km"] - ranking.iloc[1]["distance_km"]) < 0.01:
        warnings.append("top two candidates are within 10 m of each other; report the tie")

    out = {
        "plate_code": code,
        "plate_name": name,
        "result": record(chosen, chosen["distance_km"]),
        "ranking": [{"id": r["id"], "distance_km": round(float(r["distance_km"]), 6),
                     "magnitude": to_float(r["_props"].get("mag")),
                     "latitude": r["latitude"], "longitude": r["longitude"]}
                    for _, r in ranking.iterrows()],
        "stats": {
            "earthquakes_loaded": n_total,
            "earthquakes_after_filters": len(eq),
            "filters_applied": filter_notes,
            "earthquakes_in_plate": len(inside),
            "boundary_segments_used": len(sel),
            "boundary_selection": sel_desc,
            "distance_km_min": round(float(inside["distance_km"].min()), 6),
            "distance_km_max": round(float(inside["distance_km"].max()), 6),
            "distance_km_mean": round(float(inside["distance_km"].mean()), 6),
        },
        "method": (f"within({code} polygon, EPSG:4326) -> to_crs({METRIC_CRS}) -> "
                   f"distance to union of {len(sel)} boundary segments -> /1000 km -> "
                   f"{'nlargest' if extreme == 'furthest' else 'nsmallest'}"),
        "warnings": warnings,
    }
    sys.stdout.write(json.dumps(out, default=lambda o: o.item() if hasattr(o, "item") else str(o)))


if __name__ == "__main__":
    main()

"""Find the earthquake inside a tectonic plate that lies furthest from that plate's boundary.

stdin:  {"state": {earthquakes_path, plates_path, boundaries_path, plate}, "assets": {"config": ...}}
stdout: {status, plate_code, plate_name, n_earthquakes, n_in_plate, n_boundary_segments,
         metric_crs, proj_version, furthest, top_candidates}

Method (geopandas, no hand-rolled geometry):
  1. Load plates/boundaries with gpd.read_file; build earthquake points from lon/lat in EPSG:4326
     (2-D, so the USGS depth coordinate never reaches the projection).
  2. Spatial filter: earthquakes .within() the union of the target plate's polygons (in EPSG:4326).
  3. Boundary = union of the boundaries-file segments whose PlateA/PlateB (or Name) involves the plate.
     The plate polygon's own outline is NOT the boundary: it carries artificial edges at +/-180 lon.
  4. Project in-plate points and boundary to the metric CRS (EPSG:4087), .distance() -> metres -> km.
  5. nlargest(1) on distance_km.
"""
import json
import numbers
import re
import sys
from datetime import datetime, timezone

import geopandas as gpd
import pandas as pd
import pyproj
from shapely.geometry import Point


def fail(msg):
    print(msg, file=sys.stderr)
    sys.exit(1)


def load_config(assets):
    cfg = assets.get("config", {}) if isinstance(assets, dict) else {}
    if isinstance(cfg, str):
        cfg = json.loads(cfg) if cfg.strip() else {}
    return {
        "source_crs": cfg.get("source_crs", "EPSG:4326"),
        "metric_crs": cfg.get("metric_crs", "EPSG:4087"),
        "top_n": int(cfg.get("top_n", 5)),
    }


def iso_time(value):
    """USGS `time` is epoch milliseconds (UTC). Return YYYY-MM-DDTHH:MM:SSZ (sub-seconds truncated)."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, numbers.Real):  # includes numpy int64/float64
        dt = datetime.fromtimestamp(int(value) // 1000, tz=timezone.utc)
    else:
        dt = pd.Timestamp(value)
        dt = dt.tz_localize("UTC") if dt.tzinfo is None else dt.tz_convert("UTC")
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def load_earthquakes(path, crs):
    with open(path) as fh:
        data = json.load(fh)
    records = []
    if isinstance(data, dict) and "features" in data:
        for feat in data["features"]:
            geom = feat.get("geometry") or {}
            coords = geom.get("coordinates") or []
            if geom.get("type") != "Point" or len(coords) < 2 or coords[0] is None or coords[1] is None:
                continue  # missing geometry
            props = feat.get("properties") or {}
            records.append({
                "id": feat.get("id") or props.get("ids", "").strip(",").split(",")[0] or props.get("code"),
                "place": props.get("place"),
                "time": props.get("time"),
                "magnitude": props.get("mag"),
                "longitude": float(coords[0]),
                "latitude": float(coords[1]),
            })
    elif isinstance(data, list):
        for row in data:
            lat = row.get("latitude", row.get("lat"))
            lon = row.get("longitude", row.get("lon"))
            if lat is None or lon is None:
                continue
            records.append({
                "id": row.get("id"), "place": row.get("place"), "time": row.get("time"),
                "magnitude": row.get("magnitude", row.get("mag")),
                "longitude": float(lon), "latitude": float(lat),
            })
    else:
        fail(f"{path}: expected a GeoJSON FeatureCollection or a list of records")
    if not records:
        fail(f"{path}: no earthquakes with point coordinates found")
    geometry = [Point(r["longitude"], r["latitude"]) for r in records]
    return gpd.GeoDataFrame(records, geometry=geometry, crs=crs)


def resolve_plate(plates, plate):
    want = str(plate).strip().lower()
    code_col = next((c for c in plates.columns if c.lower() == "code"), None)
    name_col = next((c for c in plates.columns if c.lower() in ("platename", "name")), None)
    mask = pd.Series(False, index=plates.index)
    if code_col:
        mask |= plates[code_col].astype(str).str.lower() == want
    if name_col:
        mask |= plates[name_col].astype(str).str.lower() == want
    hits = plates[mask & plates.geometry.notna()]
    if hits.empty:
        avail = sorted(set(plates[code_col].astype(str))) if code_col else []
        fail(f"plate {plate!r} not found by code or name; available codes: {avail}")
    code = str(hits[code_col].iloc[0]) if code_col else str(plate)
    name = str(hits[name_col].iloc[0]) if name_col else code
    return code, name, hits


def plate_boundaries(bounds, code):
    bounds = bounds[bounds.geometry.notna()]
    cols = {c.lower(): c for c in bounds.columns}
    mask = pd.Series(False, index=bounds.index)
    if "platea" in cols and "plateb" in cols:
        mask |= (bounds[cols["platea"]].astype(str) == code) | (bounds[cols["plateb"]].astype(str) == code)
    if "name" in cols:
        # PB2002 names join two codes with '-', '/' or '\' (e.g. "PA-NA", "AU\\PA").
        tokens = bounds[cols["name"]].astype(str).map(lambda s: re.split(r"[-/\\]", s))
        mask |= tokens.map(lambda t: code in t)
    sel = bounds[mask]
    if sel.empty:
        fail(f"no boundary segments involve plate {code!r}")
    return sel


def main():
    payload = json.load(sys.stdin)
    state = payload.get("state", {})
    cfg = load_config(payload.get("assets", {}))
    src, metric = cfg["source_crs"], cfg["metric_crs"]

    plates = gpd.read_file(state["plates_path"])
    bounds = gpd.read_file(state["boundaries_path"])
    if plates.crs is None:
        plates = plates.set_crs(src)
    if bounds.crs is None:
        bounds = bounds.set_crs(src)
    plates, bounds = plates.to_crs(src), bounds.to_crs(src)
    eq = load_earthquakes(state["earthquakes_path"], src)

    code, name, plate_rows = resolve_plate(plates, state["plate"])
    plate_geom = plate_rows.geometry.make_valid().union_all()
    inside = eq[eq.within(plate_geom)].copy()

    seg = plate_boundaries(bounds, code)
    out = {
        "plate_code": code,
        "plate_name": name,
        "n_earthquakes": int(len(eq)),
        "n_in_plate": int(len(inside)),
        "n_boundary_segments": int(len(seg)),
        "metric_crs": metric,
        # EPSG:4087 northings differ across PROJ releases (spherical in 9.4, ellipsoidal in 9.8),
        # shifting distances by up to ~0.3%; the task container's PROJ is the reference.
        "proj_version": f"pyproj {pyproj.__version__} / PROJ {pyproj.proj_version_str}",
    }
    if inside.empty:
        out.update(status="no_events_in_plate", furthest={}, top_candidates=[])
        print(json.dumps(out))
        return

    boundary_m = seg.to_crs(metric).geometry.union_all()
    inside["distance_km"] = inside.to_crs(metric).geometry.distance(boundary_m) / 1000.0

    def record(row):
        mag = row["magnitude"]
        return {
            "id": None if row["id"] is None else str(row["id"]),
            "place": row["place"],
            "time": iso_time(row["time"]),
            "magnitude": None if mag is None or pd.isna(mag) else float(mag),
            "latitude": float(row["latitude"]),
            "longitude": float(row["longitude"]),
            "distance_km": round(float(row["distance_km"]), 2),
        }

    top = inside.nlargest(cfg["top_n"], "distance_km")
    out.update(
        status="found",
        furthest=record(top.iloc[0]),
        top_candidates=[record(r) for _, r in top.iterrows()],
    )
    print(json.dumps(out))


if __name__ == "__main__":
    main()

"""Stdlib-only loaders and lookups over the TravelPlanner-style sandbox datasets.

Mirrors the six curated search skills (search-cities, search-flights,
search-driving-distance, search-accommodations, search-restaurants,
search-attractions) with the same filtering semantics, so whatever these
functions return is exactly what the sandbox "contains":

- rows missing any selected column are dropped (pandas ``dropna`` semantics,
  including pandas' default NA strings such as "", "NA", "None", "nan");
- city/state lookups strip text after the first "(";
- flights match origin, destination and date exactly (case-sensitive);
- driving distance matches origin/destination exactly; a duration containing
  "day" means "no valid information"; cost is int(km * 0.05) for self-driving
  and int(km) for taxi (per vehicle);
- accommodations/restaurants/attractions match city case-insensitively.

Also usable as a CLI for ad-hoc lookups, printing JSON:

    python travel_db.py cities --state Texas
    python travel_db.py flights --origin "New York" --destination Denver --date 2022-03-16
    python travel_db.py distance --origin Killeen --destination Austin --mode self-driving
    python travel_db.py accommodations --city Austin
    python travel_db.py restaurants --city Austin
    python travel_db.py attractions --city Austin
    (add --data-dir DIR when the data folder is not auto-discovered)
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path

MARKER = Path("background") / "citySet_with_states.txt"

FILES = {
    "cities": Path("background") / "citySet_with_states.txt",
    "flights": Path("flights") / "clean_Flights_2022.csv",
    "distance": Path("googleDistanceMatrix") / "distance.csv",
    "accommodations": Path("accommodations") / "clean_accommodations_2022.csv",
    "restaurants": Path("restaurants") / "clean_restaurant_2022.csv",
    "attractions": Path("attractions") / "attractions.csv",
}

FLIGHT_COLUMNS = ["Flight Number", "Price", "DepTime", "ArrTime", "ActualElapsedTime",
                  "FlightDate", "OriginCityName", "DestCityName", "Distance"]
DISTANCE_COLUMNS = ["origin", "destination", "duration", "distance"]
ACCOMMODATION_COLUMNS = ["NAME", "price", "room type", "house_rules", "minimum nights",
                         "maximum occupancy", "review rate number", "city"]
RESTAURANT_COLUMNS = ["Name", "Average Cost", "Cuisines", "Aggregate Rating", "City"]
ATTRACTION_COLUMNS = ["Name", "Latitude", "Longitude", "Address", "Phone", "Website", "City"]

# pandas.read_csv default NA strings: such cells count as missing and drop the row.
NA_STRINGS = {"", "#N/A", "#N/A N/A", "#NA", "-1.#IND", "-1.#QNAN", "-NaN", "-nan",
              "1.#IND", "1.#QNAN", "<NA>", "N/A", "NA", "NULL", "NaN", "None", "n/a",
              "nan", "null"}

csv.field_size_limit(sys.maxsize)


def before_paren(value: str | None) -> str:
    """Return the substring before the first '(' (e.g. 'Austin(Texas)' -> 'Austin')."""
    if value is None:
        return ""
    return str(value).split("(", 1)[0].strip()


# ---------------------------------------------------------------- data dir ---

def _candidate_dirs(explicit: str | None) -> list[Path]:
    out: list[Path] = []
    if explicit:
        out.append(Path(explicit).expanduser())
    env = os.environ.get("TRAVEL_DATA_DIR")
    if env:
        out.append(Path(env).expanduser())
    here = Path(__file__).resolve().parent
    out += [Path("/app/data"), Path("/root/data"), Path("/root/environment/data"),
            Path("/root"), Path("/data"), Path("/workspace/data"), Path.cwd() / "data",
            here.parent / "data", here.parent.parent / "data"]
    return out


def find_data_dir(explicit: str | None = None) -> Path:
    """Locate the folder holding background/, flights/, googleDistanceMatrix/, ...

    Order: explicit argument, $TRAVEL_DATA_DIR, common container paths, then a
    shallow search (depth <= 4) under /app, /root, /data, /workspace, /mnt, /home.
    """
    for cand in _candidate_dirs(explicit):
        if (cand / MARKER).is_file():
            return cand
    if explicit and Path(explicit).is_dir():
        # Explicit folder that holds the files somewhere below it.
        roots = [Path(explicit)]
    else:
        roots = [Path(p) for p in ("/app", "/root", "/data", "/workspace", "/mnt", "/home")]
    for root in roots:
        if not root.is_dir():
            continue
        base_depth = len(root.parts)
        for dirpath, dirnames, _ in os.walk(root):
            depth = len(Path(dirpath).parts) - base_depth
            if depth >= 4:
                dirnames[:] = []
            dirnames[:] = [d for d in dirnames if not d.startswith(".") and d not in
                           ("proc", "sys", "node_modules", "site-packages", "__pycache__")]
            if (Path(dirpath) / MARKER).is_file():
                return Path(dirpath)
    raise FileNotFoundError(
        "Travel data folder not found (looked for background/citySet_with_states.txt). "
        "Pass data_dir / --data-dir or set TRAVEL_DATA_DIR.")


# ------------------------------------------------------------------ loaders ---

def _rows(path: Path, columns: list[str], rename: dict[str, str] | None = None):
    """Yield dicts with only `columns`, skipping rows where any is NA (dropna)."""
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.reader(fh)
        header = next(reader)
        if rename:
            header = [rename.get(h, h) for h in header]
        idx = {c: header.index(c) for c in columns if c in header}
        for raw in reader:
            row = {}
            ok = True
            for col, i in idx.items():
                v = raw[i] if i < len(raw) else ""
                if v in NA_STRINGS:
                    ok = False
                    break
                row[col] = v
            if ok:
                yield row


def _num(value: str) -> float:
    return float(str(value).replace(",", ""))


def load_city_states(data_dir: Path) -> dict[str, list[str]]:
    """State -> cities, from the tab-separated city<TAB>state file."""
    mapping: dict[str, list[str]] = {}
    text = (data_dir / FILES["cities"]).read_text(encoding="utf-8").strip()
    for line in text.splitlines():
        if not line.strip():
            continue
        city, sep, state = line.partition("\t")
        if not sep:
            continue
        city, state = city.strip(), state.strip()
        if city and state:
            mapping.setdefault(state, []).append(city)
    return mapping


def cities_for_state(mapping: dict[str, list[str]], state: str) -> list[str] | None:
    want = before_paren(state).lower()
    for key, cities in mapping.items():
        if key.lower() == want:
            return list(cities)
    return None


def state_of_city(mapping: dict[str, list[str]], city: str) -> str | None:
    want = before_paren(city).lower()
    for state, cities in mapping.items():
        if any(c.lower() == want for c in cities):
            return state
    return None


def load_flights(data_dir: Path, dates: set[str] | None = None,
                 cities: set[str] | None = None) -> list[dict]:
    """Flights, optionally restricted to FlightDate in `dates` and both ends in `cities`."""
    out = []
    for r in _rows(data_dir / FILES["flights"], FLIGHT_COLUMNS, {"Unnamed: 0": "Flight Number"}):
        if dates is not None and r["FlightDate"] not in dates:
            continue
        o, d = r["OriginCityName"], r["DestCityName"]
        if cities is not None and (o not in cities or d not in cities):
            continue
        r["Price"] = _num(r["Price"])
        out.append(r)
    return out


def search_flights(flights: list[dict], origin: str, destination: str, date: str) -> list[dict]:
    o, d = before_paren(origin), before_paren(destination)
    return [f for f in flights if f["OriginCityName"] == o and f["DestCityName"] == d
            and f["FlightDate"] == date]


def load_distances(data_dir: Path) -> dict[tuple[str, str], dict]:
    """(origin, destination) -> first matching row (the original tool takes values[0])."""
    out: dict[tuple[str, str], dict] = {}
    for r in _rows(data_dir / FILES["distance"], DISTANCE_COLUMNS):
        key = (r["origin"].strip(), r["destination"].strip())
        out.setdefault(key, r)
    return out


def parse_km(text: str) -> float | None:
    try:
        return float(str(text).lower().replace("km", "").replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def mode_cost(distance_km: float | None, mode: str) -> int | None:
    """Per-vehicle cost: self-driving int(km*0.05), taxi int(km)."""
    if distance_km is None:
        return None
    mode = mode.lower()
    if "driving" in mode or "self-drive" in mode:
        return int(distance_km * 0.05)
    if mode == "taxi":
        return int(distance_km)
    return None


def search_distance(distances: dict, origin: str, destination: str, mode: str = "driving") -> dict:
    """Return {origin, destination, duration, distance, distance_km, cost, valid}."""
    o, d = before_paren(origin), before_paren(destination)
    info = {"origin": o, "destination": d, "mode": mode, "duration": None,
            "distance": None, "distance_km": None, "cost": None, "valid": False}
    row = distances.get((o, d))
    if not row:
        return info
    duration, dist = row["duration"], row["distance"]
    if "day" in duration.lower():
        return info
    km = parse_km(dist)
    info.update(duration=duration, distance=dist, distance_km=km,
                cost=mode_cost(km, mode), valid=True)
    return info


def load_accommodations(data_dir: Path) -> list[dict]:
    out = []
    for r in _rows(data_dir / FILES["accommodations"], ACCOMMODATION_COLUMNS):
        r["city"] = r["city"].strip()
        r["price"] = _num(r["price"])
        r["minimum nights"] = _num(r["minimum nights"])
        r["maximum occupancy"] = int(_num(r["maximum occupancy"]))
        r["review rate number"] = _num(r["review rate number"])
        out.append(r)
    return out


def load_restaurants(data_dir: Path) -> list[dict]:
    out = []
    for r in _rows(data_dir / FILES["restaurants"], RESTAURANT_COLUMNS):
        r["City"] = r["City"].strip()
        r["Average Cost"] = _num(r["Average Cost"])
        r["Aggregate Rating"] = _num(r["Aggregate Rating"])
        r["cuisine_list"] = [c.strip() for c in r["Cuisines"].split(",") if c.strip()]
        out.append(r)
    return out


def load_attractions(data_dir: Path) -> list[dict]:
    out = []
    for r in _rows(data_dir / FILES["attractions"], ATTRACTION_COLUMNS):
        r["City"] = r["City"].strip()
        out.append(r)
    return out


def by_city(rows: list[dict], city: str, key: str) -> list[dict]:
    want = before_paren(city).strip().lower()
    return [r for r in rows if r[key].lower() == want]


# ---------------------------------------------------------------------- CLI ---

def _main() -> None:
    p = argparse.ArgumentParser(description="Look up the travel sandbox datasets (JSON output).")
    p.add_argument("kind", choices=["cities", "flights", "distance", "accommodations",
                                    "restaurants", "attractions", "datadir"])
    p.add_argument("--state", "-s")
    p.add_argument("--city", "-c")
    p.add_argument("--origin", "-o")
    p.add_argument("--destination", "-d")
    p.add_argument("--date", "-t", help="YYYY-MM-DD")
    p.add_argument("--mode", "-m", default="self-driving", help="self-driving or taxi")
    p.add_argument("--data-dir")
    a = p.parse_args()
    data_dir = find_data_dir(a.data_dir)
    if a.kind == "datadir":
        result: object = str(data_dir)
    elif a.kind == "cities":
        result = cities_for_state(load_city_states(data_dir), a.state or "") or "Invalid state."
    elif a.kind == "flights":
        rows = load_flights(data_dir, {a.date} if a.date else None)
        result = search_flights(rows, a.origin or "", a.destination or "", a.date or "")
        if not result:
            result = f"There is no flight from {a.origin} to {a.destination} on {a.date}."
    elif a.kind == "distance":
        result = search_distance(load_distances(data_dir), a.origin or "", a.destination or "", a.mode)
    elif a.kind == "accommodations":
        result = by_city(load_accommodations(data_dir), a.city or "", "city") or \
            "There are no accommodations in this city."
    elif a.kind == "restaurants":
        result = by_city(load_restaurants(data_dir), a.city or "", "City") or \
            "There is no restaurant in this city."
    else:
        result = by_city(load_attractions(data_dir), a.city or "", "City") or \
            "There is no attraction in this city."
    print(json.dumps(result, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    _main()

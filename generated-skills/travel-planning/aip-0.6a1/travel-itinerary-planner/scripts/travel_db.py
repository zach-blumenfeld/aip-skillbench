"""Search layer over the travel-planning sandbox database.

A faithful port of the six source skills (search-cities, search-accommodations,
search-restaurants, search-attractions, search-driving-distance, search-flights):
same files, same column subsets, same dropna() cleaning, same case rules and
the same driving/taxi cost formulas. Only the data root is configurable
(default /app/data) so the step scripts and an agent can share it.

Also a CLI for ad-hoc lookups while repairing a plan:
    python travel_db.py cities --state Ohio [--data-dir /app/data]
    python travel_db.py accommodations --city Cleveland
    python travel_db.py restaurants --city Cleveland
    python travel_db.py attractions --city Cleveland
    python travel_db.py distance --origin Minneapolis --destination Cleveland [--mode driving|taxi]
    python travel_db.py flights --origin Minneapolis --destination Cleveland --date 2022-03-17
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from functools import lru_cache
from pathlib import Path

import pandas as pd

DEFAULT_DATA_DIR = "/app/data"

FILES = {
    "cities": "background/citySet_with_states.txt",
    "states": "background/stateSet.txt",
    "accommodations": "accommodations/clean_accommodations_2022.csv",
    "restaurants": "restaurants/clean_restaurant_2022.csv",
    "attractions": "attractions/attractions.csv",
    "distance": "googleDistanceMatrix/distance.csv",
    "flights": "flights/clean_Flights_2022.csv",
}

ACCOMMODATION_COLUMNS = ["NAME", "price", "room type", "house_rules", "minimum nights",
                         "maximum occupancy", "review rate number", "city"]
RESTAURANT_COLUMNS = ["Name", "Average Cost", "Cuisines", "Aggregate Rating", "City"]
ATTRACTION_COLUMNS = ["Name", "Latitude", "Longitude", "Address", "Phone", "Website", "City"]
DISTANCE_COLUMNS = ["origin", "destination", "duration", "distance"]
FLIGHT_COLUMNS = ["Flight Number", "Price", "DepTime", "ArrTime", "ActualElapsedTime",
                  "FlightDate", "OriginCityName", "DestCityName", "Distance"]

# Local constraint vocabulary -> dataset values.
HOUSE_RULE_TEXT = {
    "pets": "No pets",
    "smoking": "No smoking",
    "parties": "No parties",
    "children under 10": "No children under 10",
    "visitors": "No visitors",
}
ROOM_TYPES = {
    "entire room": {"Entire home/apt"},
    "private room": {"Private room"},
    "shared room": {"Shared room"},
    "not shared room": {"Entire home/apt", "Private room"},
}


def path_for(data_dir: str, kind: str) -> Path:
    p = Path(data_dir or DEFAULT_DATA_DIR) / FILES[kind]
    if not p.exists():
        raise FileNotFoundError(f"{kind} data not found at {p}")
    return p


def before_parenthesis(value: str | None) -> str:
    if value is None:
        return ""
    return str(value).split("(", 1)[0].strip()


# ---------------------------------------------------------------- loaders
@lru_cache(maxsize=None)
def city_state_map(data_dir: str) -> dict[str, list[str]]:
    """state -> [cities], from the tab-separated background file (search-cities)."""
    mapping: dict[str, list[str]] = {}
    for line in path_for(data_dir, "cities").read_text(encoding="utf-8").strip().splitlines():
        city, sep, state = line.partition("\t")
        city, state = city.strip(), state.strip()
        if sep and city and state:
            mapping.setdefault(state, []).append(city)
    return mapping


def states(data_dir: str) -> list[str]:
    return list(city_state_map(data_dir).keys())


def all_cities(data_dir: str) -> list[str]:
    return [c for cs in city_state_map(data_dir).values() for c in cs]


def search_cities(data_dir: str, state: str) -> list[str] | str:
    target = state.strip().lower()
    for key, cities in city_state_map(data_dir).items():
        if key.lower() == target:
            return list(cities)
    return "Invalid state."


def canonical_city(data_dir: str, city: str) -> str:
    """Map a city to the database spelling (case-insensitive); unchanged if unknown."""
    c = before_parenthesis(city).lower()
    for known in all_cities(data_dir):
        if known.lower() == c:
            return known
    return before_parenthesis(city)


@lru_cache(maxsize=None)
def _accommodations(data_dir: str) -> pd.DataFrame:
    df = pd.read_csv(path_for(data_dir, "accommodations"))
    df = df[[c for c in ACCOMMODATION_COLUMNS if c in df.columns]].dropna()
    df["city"] = df["city"].astype(str).str.strip()
    return df


@lru_cache(maxsize=None)
def _restaurants(data_dir: str) -> pd.DataFrame:
    df = pd.read_csv(path_for(data_dir, "restaurants"))
    df = df[[c for c in RESTAURANT_COLUMNS if c in df.columns]].dropna()
    df["City"] = df["City"].astype(str).str.strip()
    return df


@lru_cache(maxsize=None)
def _attractions(data_dir: str) -> pd.DataFrame:
    df = pd.read_csv(path_for(data_dir, "attractions"))
    df = df[[c for c in ATTRACTION_COLUMNS if c in df.columns]].dropna()
    df["City"] = df["City"].astype(str).str.strip()
    return df


@lru_cache(maxsize=None)
def _distances(data_dir: str) -> pd.DataFrame:
    try:
        df = pd.read_csv(path_for(data_dir, "distance"))
    except FileNotFoundError:
        return pd.DataFrame(columns=DISTANCE_COLUMNS)
    df = df[[c for c in DISTANCE_COLUMNS if c in df.columns]].dropna()
    df["origin"] = df["origin"].astype(str).str.strip()
    df["destination"] = df["destination"].astype(str).str.strip()
    return df


@lru_cache(maxsize=None)
def _flights(data_dir: str) -> pd.DataFrame:
    df = pd.read_csv(path_for(data_dir, "flights"))
    df = df.rename(columns={"Unnamed: 0": "Flight Number"})
    return df[[c for c in FLIGHT_COLUMNS if c in df.columns]].dropna()


# ---------------------------------------------------------------- searches
def search_accommodations(data_dir: str, city: str) -> pd.DataFrame:
    df = _accommodations(data_dir)
    return df[df["city"].str.lower() == city.strip().lower()].reset_index(drop=True)


def search_restaurants(data_dir: str, city: str) -> pd.DataFrame:
    df = _restaurants(data_dir)
    return df[df["City"].str.lower() == before_parenthesis(city).lower()].reset_index(drop=True)


def search_attractions(data_dir: str, city: str) -> pd.DataFrame:
    df = _attractions(data_dir)
    return df[df["City"].str.lower() == city.strip().lower()].reset_index(drop=True)


def parse_km(distance_text) -> float | None:
    if not isinstance(distance_text, str):
        return None
    try:
        return float(distance_text.lower().replace("km", "").replace(",", "").strip())
    except ValueError:
        return None


def leg_cost(distance_km: float | None, mode: str) -> int | None:
    """Per-vehicle cost: self-driving int(km*0.05), taxi int(km)."""
    if distance_km is None:
        return None
    if "driving" in mode:
        return int(distance_km * 0.05)
    if mode == "taxi":
        return int(distance_km)
    return None


def duration_hours(text) -> float | None:
    if not isinstance(text, str):
        return None
    h = m = 0.0
    parts = text.replace(",", " ").split()
    for i in range(0, len(parts) - 1):
        if parts[i + 1].startswith("hour"):
            h = float(parts[i])
        elif parts[i + 1].startswith("min"):
            m = float(parts[i])
    return h + m / 60.0


def search_driving_distance(data_dir: str, origin: str, destination: str, mode: str = "driving") -> dict:
    """Exact-match lookup (search-driving-distance); multi-day legs count as no valid information."""
    o, d = before_parenthesis(origin), before_parenthesis(destination)
    info = {"origin": o, "destination": d, "mode": mode, "duration": None, "distance": None,
            "distance_km": None, "hours": None, "cost": None}
    df = _distances(data_dir)
    hit = df[(df["origin"] == o) & (df["destination"] == d)]
    if hit.empty:
        return info
    duration, distance = hit["duration"].values[0], hit["distance"].values[0]
    if pd.isna(duration) or pd.isna(distance) or "day" in str(duration).lower():
        return info
    km = parse_km(distance)
    info.update(duration=duration, distance=distance, distance_km=km,
                hours=duration_hours(duration), cost=leg_cost(km, mode))
    return info


def search_flights(data_dir: str, origin: str, destination: str, date: str) -> pd.DataFrame:
    df = _flights(data_dir)
    return df[(df["OriginCityName"] == before_parenthesis(origin))
              & (df["DestCityName"] == before_parenthesis(destination))
              & (df["FlightDate"] == date)].reset_index(drop=True)


# ---------------------------------------------------------------- budget rules
def vehicles(people: int, mode: str) -> int:
    """Self-driving: one car per 5 people; taxi: one cab per 4 people."""
    return math.ceil(people / 5) if mode == "self-driving" else math.ceil(people / 4)


def rooms_needed(people: int, max_occupancy) -> int:
    occ = int(max_occupancy) if max_occupancy and max_occupancy > 0 else 1
    return math.ceil(people / occ)


def cuisine_tokens(cuisines: str) -> set[str]:
    return {c.strip().lower() for c in str(cuisines).split(",") if c.strip()}


def accommodation_ok(row, house_rule, room_type, nights: int | None = None) -> bool:
    rules = str(row.get("house_rules", ""))
    if house_rule and HOUSE_RULE_TEXT.get(house_rule.lower(), "\0") in rules:
        return False
    if room_type and row.get("room type") not in ROOM_TYPES.get(room_type.lower(), {row.get("room type")}):
        return False
    if nights is not None and float(row.get("minimum nights", 1)) > nights:
        return False
    return True


# ---------------------------------------------------------------- CLI
def _main() -> None:
    p = argparse.ArgumentParser(description="Search the travel sandbox database.")
    p.add_argument("kind", choices=["cities", "accommodations", "restaurants", "attractions", "distance", "flights"])
    p.add_argument("--data-dir", default=DEFAULT_DATA_DIR)
    p.add_argument("--state")
    p.add_argument("--city")
    p.add_argument("--origin")
    p.add_argument("--destination")
    p.add_argument("--date")
    p.add_argument("--mode", default="driving")
    a = p.parse_args()
    dd = a.data_dir
    if a.kind == "cities":
        out = search_cities(dd, a.state or "")
    elif a.kind == "distance":
        out = search_driving_distance(dd, a.origin, a.destination, a.mode)
    else:
        fn = {"accommodations": search_accommodations, "restaurants": search_restaurants,
              "attractions": search_attractions}.get(a.kind)
        df = fn(dd, a.city) if fn else search_flights(dd, a.origin, a.destination, a.date)
        out = df.to_dict(orient="records")
    json.dump(out, sys.stdout, indent=1, default=str)
    print()


if __name__ == "__main__":
    _main()

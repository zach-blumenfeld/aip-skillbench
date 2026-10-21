#!/usr/bin/env python3
"""Travel-itinerary toolkit over the bundled TravelPlanner-style database.

Requires: Python >= 3.10, pandas (tested with 2.2.2). No network access.

Subcommands
  search tools (each one is logged so `draft` can fill `tool_called`):
    cities          --state S                       -> search_cities
    accommodations  --city C [filters]              -> search_accommodations
    attractions     --city C                        -> search_attractions
    restaurants     --city C [--cuisines a,b]       -> search_restaurants
    distance        --origin A --destination B      -> search_driving_distance
    flights         --origin A --destination B --date YYYY-MM-DD -> search_flights
  planning:
    reset-log  clear the tool-call log (run once at the start of each task)
    draft     --constraints c.json --out itinerary.json   cheapest valid plan
    validate  --constraints c.json --plan itinerary.json  check every rule, cost

Data directory: --data-dir, else $TRAVEL_DATA_DIR, else /app/data, else
./data, else ../../data relative to this script. It must contain
accommodations/, attractions/, restaurants/, googleDistanceMatrix/, flights/,
background/ exactly as the bundled dataset ships them.
"""
from __future__ import annotations

import argparse
import itertools
import json
import math
import os
import re
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

HOUSE_RULES = {  # constraint value -> text in house_rules that forbids it
    "pets": "No pets",
    "smoking": "No smoking",
    "parties": "No parties",
    "children under 10": "No children under 10",
    "visitors": "No visitors",
}
ROOM_TYPES = {
    "entire room": lambda t: t == "Entire home/apt",
    "private room": lambda t: t == "Private room",
    "shared room": lambda t: t == "Shared room",
    "not shared room": lambda t: t != "Shared room",
}
TRANSPORT_CONSTRAINTS = {"no flight", "no self-driving"}
# Row filters copied from the original search tools: rows blank in any of these
# columns are invisible to those tools, so the planner must not use them.
ACC_COLUMNS = ["NAME", "price", "room type", "house_rules", "minimum nights",
               "maximum occupancy", "review rate number", "city"]
REST_COLUMNS = ["Name", "Average Cost", "Cuisines", "Aggregate Rating", "City"]
ATTR_COLUMNS = ["Name", "Latitude", "Longitude", "Address", "Phone", "Website", "City"]
DEFAULT_CITY_COUNT = {3: 1, 5: 2, 7: 3}  # days -> cities when dest is a state
TOOL_LOG = Path(os.environ.get("TRAVEL_TOOL_LOG", Path(tempfile.gettempdir()) / "travel_tool_calls.json"))
TOOL_ORDER = ["search_cities", "search_flights", "search_driving_distance",
              "search_accommodations", "search_restaurants", "search_attractions"]


# ----------------------------------------------------------------- data access
def find_data_dir(arg: str | None) -> Path:
    here = Path(__file__).resolve().parent
    candidates = [arg, os.environ.get("TRAVEL_DATA_DIR"), "/app/data", "data",
                  here.parent.parent / "data"]
    for c in candidates:
        if c and (Path(c) / "accommodations").is_dir():
            return Path(c)
    sys.exit("ERROR: data directory not found; pass --data-dir pointing at the folder "
             "that contains accommodations/, restaurants/, attractions/, googleDistanceMatrix/, background/")


def strip_paren(v: str) -> str:
    return str(v).split("(", 1)[0].strip()


def log_tool(name: str) -> None:
    try:
        used = json.loads(TOOL_LOG.read_text()) if TOOL_LOG.exists() else []
    except (OSError, ValueError):
        used = []
    if name not in used:
        used.append(name)
        try:
            TOOL_LOG.write_text(json.dumps(used))
        except OSError:
            pass


def logged_tools() -> list[str]:
    try:
        return json.loads(TOOL_LOG.read_text()) if TOOL_LOG.exists() else []
    except (OSError, ValueError):
        return []


class DB:
    def __init__(self, data_dir: Path):
        self.dir = data_dir
        self._cache: dict[str, object] = {}

    def _get(self, key, loader):
        if key not in self._cache:
            self._cache[key] = loader()
        return self._cache[key]

    def city_state(self) -> dict[str, str]:
        def load():
            m = {}
            for line in (self.dir / "background/citySet_with_states.txt").read_text(encoding="utf-8").splitlines():
                city, sep, state = line.partition("\t")
                if sep and city.strip() and state.strip():
                    m[city.strip()] = state.strip()
            return m
        return self._get("cs", load)

    def cities_in_state(self, state: str) -> list[str]:
        s = state.strip().lower()
        return [c for c, st in self.city_state().items() if st.lower() == s]

    def accommodations(self) -> pd.DataFrame:
        def load():
            df = pd.read_csv(self.dir / "accommodations/clean_accommodations_2022.csv")
            # Same row filter as the original search tool (dropna over these
            # columns): a listing the search tool cannot return does not exist
            # for the evaluator, even if its only blank field is house_rules.
            df = df.dropna(subset=[c for c in ACC_COLUMNS if c in df.columns])
            df["city"] = df["city"].astype(str).str.strip()
            df["NAME"] = df["NAME"].astype(str).str.strip()
            return df.drop(columns=[c for c in df.columns if c.startswith("Unnamed")])
        return self._get("acc", load)

    def restaurants(self) -> pd.DataFrame:
        def load():
            df = pd.read_csv(self.dir / "restaurants/clean_restaurant_2022.csv")
            df = df.dropna(subset=[c for c in REST_COLUMNS if c in df.columns])
            df["City"] = df["City"].astype(str).str.strip()
            df["Name"] = df["Name"].astype(str).str.strip()
            return df.drop(columns=[c for c in df.columns if c.startswith("Unnamed")])
        return self._get("rest", load)

    def attractions(self) -> pd.DataFrame:
        def load():
            df = pd.read_csv(self.dir / "attractions/attractions.csv")
            df = df.dropna(subset=[c for c in ATTR_COLUMNS if c in df.columns])
            df["City"] = df["City"].astype(str).str.strip()
            df["Name"] = df["Name"].astype(str).str.strip()
            return df
        return self._get("attr", load)

    def distances(self) -> pd.DataFrame:
        def load():
            df = pd.read_csv(self.dir / "googleDistanceMatrix/distance.csv")
            df = df.dropna(subset=["origin", "destination", "duration", "distance"])
            df["origin"] = df["origin"].astype(str).str.strip()
            df["destination"] = df["destination"].astype(str).str.strip()
            return df.drop_duplicates(["origin", "destination"])
        return self._get("dist", load)

    def flights(self) -> pd.DataFrame:
        def load():
            df = pd.read_csv(self.dir / "flights/clean_Flights_2022.csv")
            df = df.rename(columns={"Unnamed: 0": "Flight Number"}).dropna()
            return df
        return self._get("fl", load)

    # ---- lookups
    def leg(self, origin: str, dest: str, mode: str, people: int) -> dict | None:
        """Ground leg; mode is 'self-driving' or 'taxi'. None if not drivable."""
        o, d = strip_paren(origin), strip_paren(dest)
        idx = self._get("dist_idx", lambda: {(r.origin, r.destination): (str(r.duration), str(r.distance))
                                             for r in self.distances().itertuples()})
        if (o, d) not in idx:
            return None
        dur, dist = idx[(o, d)]
        if "day" in dur.lower():  # multi-day drives are treated as infeasible
            return None
        try:
            km = float(dist.lower().replace("km", "").replace(",", "").strip())
        except ValueError:
            return None
        if mode == "self-driving":
            unit, vehicles = int(km * 0.05), math.ceil(people / 5)
        else:
            unit, vehicles = int(km), math.ceil(people / 4)
        return {"mode": mode, "origin": o, "destination": d, "duration": dur, "distance": dist,
                "unit_cost": unit, "vehicles": vehicles, "cost": unit * vehicles}

    def cheapest_flight(self, origin: str, dest: str, day: str, people: int) -> dict | None:
        def load():
            f = self.flights().sort_values(["Price", "DepTime"])
            f = f.drop_duplicates(["OriginCityName", "DestCityName", "FlightDate"])
            cols = ["Flight Number", "DepTime", "ArrTime", "Price"]
            return {k: dict(zip(cols, v)) for k, v in zip(
                zip(f.OriginCityName, f.DestCityName, f.FlightDate), f[cols].itertuples(index=False))}
        r = self._get("fl_idx", load).get((strip_paren(origin), strip_paren(dest), day))
        if r is None:
            return None
        return {"mode": "flight", "origin": strip_paren(origin), "destination": strip_paren(dest),
                "flight_number": r["Flight Number"], "dep": r["DepTime"], "arr": r["ArrTime"],
                "unit_cost": int(r["Price"]), "vehicles": people, "cost": int(r["Price"]) * people}

    def lodging(self, city: str, cons: dict, nights: int | None) -> pd.DataFrame:
        df = self.accommodations()
        df = df[df.city.str.lower() == city.strip().lower()].copy()
        for rule in as_list(cons.get("house rule")):
            df = df[~df.house_rules.str.contains(HOUSE_RULES[rule], regex=False)]
        rt = cons.get("room type")
        if rt:
            df = df[df["room type"].map(ROOM_TYPES[rt])]
        if nights is not None:
            df = df[df["minimum nights"] <= nights]
        people = cons["people_number"]
        df["rooms_needed"] = (people / df["maximum occupancy"]).apply(math.ceil)
        df["cost_per_night"] = df.price * df.rooms_needed
        return df.sort_values(["cost_per_night", "review rate number"], ascending=[True, False])


def as_list(v) -> list[str]:
    if not v:
        return []
    if isinstance(v, str):
        return [v]
    return list(v)


# ----------------------------------------------------------------- constraints
def load_constraints(path: str, db: DB) -> dict:
    c = json.loads(Path(path).read_text())
    errs = []
    for k in ["org", "dest", "days", "date", "people_number", "budget"]:
        if k not in c:
            errs.append(f"missing key '{k}'")
    if errs:
        sys.exit("ERROR in constraints: " + "; ".join(errs))
    local = c.get("local_constraint") or {}
    c["house rule"] = [r.lower() for r in as_list(local.get("house rule"))]
    c["room type"] = (local.get("room type") or None)
    c["room type"] = c["room type"].lower() if c["room type"] else None
    c["cuisine"] = [x.strip().title() if x.lower() != "bbq" else "BBQ" for x in as_list(local.get("cuisine"))]
    c["transportation"] = (local.get("transportation") or None)
    c["transportation"] = c["transportation"].lower() if c["transportation"] else None
    for r in c["house rule"]:
        if r not in HOUSE_RULES:
            errs.append(f"house rule '{r}' not one of {sorted(HOUSE_RULES)}")
    if c["room type"] and c["room type"] not in ROOM_TYPES:
        errs.append(f"room type '{c['room type']}' not one of {sorted(ROOM_TYPES)}")
    if c["transportation"] and c["transportation"] not in TRANSPORT_CONSTRAINTS:
        errs.append(f"transportation '{c['transportation']}' not one of {sorted(TRANSPORT_CONSTRAINTS)}")
    known_cuisines = {x.strip() for s in db.restaurants().Cuisines for x in s.split(",") if x.strip()}
    for x in c["cuisine"]:
        if x not in known_cuisines:
            errs.append(f"cuisine '{x}' not in database cuisines {sorted(known_cuisines)}")
    cs = db.city_state()
    if strip_paren(c["org"]) not in cs:
        errs.append(f"origin '{c['org']}' is not a city in the database")
    c["org"] = strip_paren(c["org"])
    states = {s.lower() for s in cs.values()}
    dest_type = c.get("dest_type") or ("state" if c["dest"].lower() in states and c["dest"] not in cs else "city")
    c["dest_type"] = dest_type
    if dest_type == "state":
        c["candidate_cities"] = [x for x in db.cities_in_state(c["dest"]) if x != c["org"]]
        if not c["candidate_cities"]:
            errs.append(f"state '{c['dest']}' has no cities in the database")
        n = c.get("visiting_city_number") or DEFAULT_CITY_COUNT.get(int(c["days"]))
        if not n:
            errs.append("visiting_city_number required when days is not 3/5/7")
        c["visiting_city_number"] = n
    else:
        if strip_paren(c["dest"]) not in cs:
            errs.append(f"destination city '{c['dest']}' is not in the database")
        c["dest"] = strip_paren(c["dest"])
        c["candidate_cities"] = [c["dest"]]
        c["visiting_city_number"] = 1
    c["start"] = date.fromisoformat(c["date"][0] if isinstance(c["date"], list) else c["date"])
    if errs:
        sys.exit("ERROR in constraints: " + "; ".join(errs))
    return c


def split_nights(days: int, n: int) -> list[int]:
    nights = days - 1
    base, extra = divmod(nights, n)
    return [base + (1 if i < extra else 0) for i in range(n)]


# ----------------------------------------------------------------- draft
def transport_options(cons: dict) -> list[str]:
    t = cons["transportation"]
    if t == "no flight":
        return ["self-driving", "taxi"]
    if t == "no self-driving":
        return ["flight", "taxi"]
    return ["self-driving", "flight", "taxi"]


_LEG_CACHE: dict = {}


def plan_legs(db: DB, stops: list[str], dates: list[str], family: str, people: int):
    legs = []
    for (a, b), d in zip(zip(stops, stops[1:]), dates):
        key = (a, b, d, family)
        if key in _LEG_CACHE:
            leg = _LEG_CACHE[key]
            if leg is None:
                return None
            legs.append(leg)
            continue
        if family == "flight":  # flights, taxi fallback (never mixed with self-driving)
            leg = db.cheapest_flight(a, b, d, people) or db.leg(a, b, "taxi", people)
        else:
            leg = db.leg(a, b, family, people)
        _LEG_CACHE[key] = leg
        if leg is None:
            return None
        legs.append(leg)
    return legs


def fmt_leg(leg: dict) -> str:
    if leg["mode"] == "flight":
        return (f"Flight Number: {leg['flight_number']}, from {leg['origin']} to {leg['destination']}, "
                f"Departure Time: {leg['dep']}, Arrival Time: {leg['arr']}")
    label = "Self-driving" if leg["mode"] == "self-driving" else "Taxi"
    return (f"{label}: from {leg['origin']} to {leg['destination']}, duration: {leg['duration']}, "
            f"distance: {leg['distance']}, cost: {leg['cost']}")


def build_skeleton(org: str, route: list[str], nights: list[int]):
    """Per-day (current_city, travel_leg_index, meal cities, attraction city, lodging city index)."""
    days = []
    stops = [org] + route + [org]
    leg_i = 0
    for ci, city in enumerate(route):
        prev = stops[ci]
        for k in range(nights[ci]):
            if k == 0:
                days.append({"current_city": f"from {prev} to {city}", "leg": leg_i,
                             "meals": [prev, city, city], "attr": [city], "stay": ci})
                leg_i += 1
            else:
                days.append({"current_city": city, "leg": None,
                             "meals": [city, city, city], "attr": [city, city], "stay": ci})
    last = route[-1]
    days.append({"current_city": f"from {last} to {org}", "leg": leg_i,
                 "meals": [last, last, None], "attr": [last], "stay": None})
    return days


def pick_meals(db: DB, skeleton, cons, org):
    """Assign distinct restaurants: cover required cuisines in non-origin cities first,
    then prefer requested cuisines, then cheaper, then higher rated."""
    want = set(cons["cuisine"])
    r = db.restaurants()
    slots = [(di, mi, city) for di, d in enumerate(skeleton) for mi, city in enumerate(d["meals"]) if city]
    used: set[tuple[str, str]] = set()
    chosen: dict[tuple[int, int], pd.Series] = {}
    pools = {}
    for _, _, city in slots:
        if city not in pools:
            p = r[r.City == city].copy()
            p["cset"] = p.Cuisines.map(lambda s: {x.strip() for x in s.split(",") if x.strip()})
            pools[city] = p
    uncovered = set(want)
    # pass 1: cover cuisines (only outside the origin city counts)
    for di, mi, city in slots:
        if not uncovered:
            break
        if city == org:
            continue
        p = pools[city]
        p = p[~p.apply(lambda x: (x.Name, x.City) in used, axis=1)] if used else p
        if p.empty:
            continue
        gain = p.cset.map(lambda s: len(s & uncovered))
        if gain.max() == 0:
            continue
        best = p.assign(g=gain).sort_values(["g", "Average Cost", "Aggregate Rating"],
                                            ascending=[False, True, False]).iloc[0]
        chosen[(di, mi)] = best
        used.add((best.Name, best.City))
        uncovered -= best.cset
    # pass 2: fill remaining slots
    for di, mi, city in slots:
        if (di, mi) in chosen:
            continue
        p = pools[city]
        p = p[~p.apply(lambda x: (x.Name, x.City) in used, axis=1)] if used else p
        if p.empty:
            return None, uncovered
        pref = p.cset.map(lambda s: 1 if (s & want) else 0) if want else 0
        best = p.assign(pref=pref).sort_values(["pref", "Average Cost", "Aggregate Rating"],
                                               ascending=[False, True, False]).iloc[0]
        chosen[(di, mi)] = best
        used.add((best.Name, best.City))
    return chosen, uncovered


def pick_attractions(db: DB, skeleton):
    a = db.attractions()
    a = a[~a.Name.str.contains(";", regex=False)]
    used, out = set(), {}
    for di, d in enumerate(skeleton):
        names = []
        for city in d["attr"]:
            p = a[(a.City == city) & (~a.Name.isin([n for n, c in used if c == city]))]
            if p.empty:
                continue
            row = p.iloc[0]
            used.add((row.Name, city))
            names.append(f"{row.Name}, {city}")
        out[di] = "".join(n + ";" for n in names) if names else "-"
    return out


def cmd_draft(args, db: DB):
    cons = load_constraints(args.constraints, db)
    for t in ["search_cities"] if cons["dest_type"] == "state" else []:
        log_tool(t)
    org, people, days = cons["org"], cons["people_number"], int(cons["days"])
    n = cons["visiting_city_number"]
    nights = split_nights(days, n)
    dates = [(cons["start"] + timedelta(days=i)).isoformat() for i in range(days)]

    # cheapest valid lodging per (city, nights)
    lodge_cache = {}
    def lodge(city, k):
        if (city, k) not in lodge_cache:
            df = db.lodging(city, cons, k)
            lodge_cache[(city, k)] = None if df.empty else df.iloc[0]
        return lodge_cache[(city, k)]

    candidates = []
    rejected = {}
    for route in itertools.permutations(cons["candidate_cities"], n):
        route = list(route)
        lodgings = [lodge(c, k) for c, k in zip(route, nights)]
        if any(l is None for l in lodgings):
            rejected[" -> ".join(route)] = "no lodging meeting house rule/room type/minimum nights"
            continue
        if not all((db.restaurants().City == c).any() and (db.attractions().City == c).any() for c in route):
            rejected[" -> ".join(route)] = "city lacks restaurants or attractions"
            continue
        stops = [org] + route + [org]
        travel_dates = []
        di = 0
        for k in nights:
            travel_dates.append(dates[di]); di += k
        travel_dates.append(dates[-1])
        best_legs = None
        for fam in transport_options(cons):
            legs = plan_legs(db, stops, travel_dates, fam, people)
            if legs and (best_legs is None or sum(l["cost"] for l in legs) < sum(l["cost"] for l in best_legs)):
                best_legs = legs
        if best_legs is None:
            rejected[" -> ".join(route)] = "no allowed transportation for some leg"
            continue
        lodging_cost = sum(float(l.cost_per_night) * k for l, k in zip(lodgings, nights))
        candidates.append((sum(l["cost"] for l in best_legs) + lodging_cost, route, best_legs, lodgings))
    log_tool("search_accommodations")
    if any(l["mode"] == "flight" for c in candidates for l in c[2]) or "flight" in transport_options(cons):
        log_tool("search_flights")
    log_tool("search_driving_distance")
    candidates.sort(key=lambda x: x[0])

    result = None
    for base, route, legs, lodgings in candidates[: args.max_routes]:
        skel = build_skeleton(org, route, nights)
        meals, uncovered = pick_meals(db, skel, cons, org)
        if meals is None or uncovered:
            rejected[" -> ".join(route)] = f"cannot cover cuisines {sorted(uncovered) if uncovered else ''} with distinct restaurants"
            continue
        meal_cost = sum(float(m["Average Cost"]) for m in meals.values()) * people
        total = base + meal_cost
        result = (total, route, legs, lodgings, skel, meals)
        break
    log_tool("search_restaurants")
    log_tool("search_attractions")
    if result is None:
        no_lodging = sorted({c for c in cons["candidate_cities"]
                             if all(lodge(c, k) is None for k in set(nights))})
        print(json.dumps({"status": "infeasible", "routes_feasible": len(candidates),
                          "cities_without_valid_lodging": no_lodging,
                          "rejected_examples": dict(list(rejected.items())[:10])}, indent=2))
        sys.exit(2)

    total, route, legs, lodgings, skel, meals = result
    attrs = pick_attractions(db, skel)
    plan = []
    for di, d in enumerate(skel):
        m = [meals.get((di, i)) for i in range(3)]
        stay = d["stay"]
        plan.append({
            "day": di + 1,
            "current_city": d["current_city"],
            "transportation": fmt_leg(legs[d["leg"]]) if d["leg"] is not None else "-",
            "breakfast": f"{m[0].Name}, {m[0].City}" if m[0] is not None else "-",
            "lunch": f"{m[1].Name}, {m[1].City}" if m[1] is not None else "-",
            "dinner": f"{m[2].Name}, {m[2].City}" if m[2] is not None else "-",
            "attraction": attrs[di],
            "accommodation": f"{lodgings[stay].NAME}, {lodgings[stay].city}" if stay is not None else "-",
        })
    tools = [t for t in TOOL_ORDER if t in logged_tools()]
    out = {"plan": plan, "tool_called": tools}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=2, ensure_ascii=False))
    over = total > float(cons["budget"])
    print(json.dumps({"status": "over_budget" if over else "ok", "out": args.out, "route": [org] + route + [org], "nights": nights,
                      "estimated_total_cost": round(total, 2), "budget": cons["budget"],
                      "routes_feasible": len(candidates)}, indent=2))
    sys.exit(3 if over else 0)


# ----------------------------------------------------------------- validate
def split_name_city(entry: str, cities: set[str]) -> tuple[str, str] | None:
    entry = entry.strip()
    if ", " not in entry:
        return None
    name, city = entry.rsplit(", ", 1)
    city = strip_paren(city)
    return (name.strip(), city) if city in cities else None


def parse_leg(text: str):
    t = text.strip()
    m = re.search(r"from (.+?) to ([^,]+)", t)
    if not m:
        return None
    low = t.lower()
    mode = "flight" if "flight" in low else "self-driving" if "self-driving" in low else "taxi" if "taxi" in low else None
    fn = re.search(r"Flight Number:\s*(\w+)", t)
    return {"mode": mode, "origin": strip_paren(m.group(1)), "destination": strip_paren(m.group(2)),
            "flight_number": fn.group(1) if fn else None}


def cmd_validate(args, db: DB):
    cons = load_constraints(args.constraints, db)
    doc = json.loads(Path(args.plan).read_text())
    errors, warnings = [], []
    plan = doc.get("plan")
    people, org, days = cons["people_number"], cons["org"], int(cons["days"])
    if not isinstance(plan, list) or len(plan) != days:
        sys.exit(f"ERROR: 'plan' must be a list of exactly {days} day objects")
    keys = ["day", "current_city", "transportation", "breakfast", "lunch", "dinner", "attraction", "accommodation"]
    tools = doc.get("tool_called")
    if not isinstance(tools, list) or not tools:
        errors.append("tool_called must be a non-empty list of search tool names")
    else:
        bad = [t for t in tools if t not in TOOL_ORDER]
        if bad:
            errors.append(f"tool_called has unknown names {bad}; valid: {TOOL_ORDER}")
    all_cities = set(db.city_state())
    R, A, H = db.restaurants(), db.attractions(), db.accommodations()
    seen_rest, seen_attr, route, modes = set(), set(), [], []
    cost = {"transport": 0.0, "meals": 0.0, "lodging": 0.0}
    stays: list[tuple[str, str] | None] = []
    rest_cuisines_dest = set()
    for i, d in enumerate(plan):
        tag = f"day {i + 1}"
        for k in keys:
            if k not in d or d[k] in (None, ""):
                errors.append(f"{tag}: missing '{k}'")
        if d.get("day") != i + 1:
            errors.append(f"{tag}: 'day' must be {i + 1}")
        cc = str(d.get("current_city", ""))
        m = re.match(r"from (.+?) to (.+)$", cc)
        cur = [strip_paren(m.group(1)), strip_paren(m.group(2))] if m else [strip_paren(cc)]
        for c in cur:
            if c not in all_cities:
                errors.append(f"{tag}: current_city '{c}' not in database")
        for c in cur:
            if not route or route[-1] != c:
                route.append(c)
        tr = str(d.get("transportation", "-"))
        if m:
            leg = parse_leg(tr)
            if not leg or not leg["mode"]:
                errors.append(f"{tag}: travel day needs transportation 'Self-driving|Taxi|Flight ... from {cur[0]} to {cur[1]}'")
            else:
                if (leg["origin"], leg["destination"]) != (cur[0], cur[1]):
                    errors.append(f"{tag}: transportation leg {leg['origin']}->{leg['destination']} != current_city {cur[0]}->{cur[1]}")
                modes.append(leg["mode"])
                if leg["mode"] == "flight":
                    f = db.flights()
                    row = f[f["Flight Number"] == leg["flight_number"]]
                    dt = (cons["start"] + timedelta(days=i)).isoformat()
                    if row.empty or row.OriginCityName.iloc[0] != cur[0] or row.DestCityName.iloc[0] != cur[1] or row.FlightDate.iloc[0] != dt:
                        errors.append(f"{tag}: flight {leg['flight_number']} not found for {cur[0]}->{cur[1]} on {dt}")
                    else:
                        cost["transport"] += float(row.Price.iloc[0]) * people
                else:
                    g = db.leg(cur[0], cur[1], leg["mode"], people)
                    if g is None:
                        errors.append(f"{tag}: no valid {leg['mode']} route {cur[0]}->{cur[1]} in distance matrix")
                    else:
                        cost["transport"] += g["cost"]
        elif tr.strip() not in ("-", ""):
            warnings.append(f"{tag}: transportation given on a non-travel day")
        for meal in ["breakfast", "lunch", "dinner"]:
            v = str(d.get(meal, "-"))
            if v.strip() == "-":
                continue
            nc = split_name_city(v, all_cities)
            if not nc:
                errors.append(f"{tag} {meal}: '{v}' must be 'Name, City'")
                continue
            hit = R[(R.Name == nc[0]) & (R.City == nc[1])]
            if hit.empty:
                errors.append(f"{tag} {meal}: '{nc[0]}' is not a restaurant in {nc[1]}")
                continue
            if nc[1] not in cur:
                errors.append(f"{tag} {meal}: {nc[1]} is not today's city {cur}")
            if nc in seen_rest:
                errors.append(f"{tag} {meal}: restaurant '{nc[0]}' repeated")
            seen_rest.add(nc)
            cost["meals"] += float(hit["Average Cost"].iloc[0]) * people
            if nc[1] != org:
                rest_cuisines_dest |= {x.strip() for x in hit.Cuisines.iloc[0].split(",")}
        av = str(d.get("attraction", "-"))
        if av.strip() != "-":
            if not av.strip().endswith(";"):
                errors.append(f"{tag}: attraction list must end with ';'")
            for item in [x for x in av.split(";") if x.strip()]:
                nc = split_name_city(item, all_cities)
                if not nc or A[(A.Name == nc[0]) & (A.City == nc[1])].empty:
                    errors.append(f"{tag}: attraction '{item.strip()}' not found as 'Name, City'")
                    continue
                if nc[1] not in cur:
                    errors.append(f"{tag}: attraction city {nc[1]} is not today's city {cur}")
                if nc in seen_attr:
                    errors.append(f"{tag}: attraction '{nc[0]}' repeated")
                seen_attr.add(nc)
        hv = str(d.get("accommodation", "-"))
        if hv.strip() == "-":
            stays.append(None)
            if i < days - 1:
                errors.append(f"{tag}: accommodation required on every night of the trip")
            continue
        nc = split_name_city(hv, all_cities)
        hit = H[(H.NAME == nc[0]) & (H.city == nc[1])] if nc else H.iloc[0:0]
        if hit.empty:
            errors.append(f"{tag}: accommodation '{hv}' not found as 'Name, City'")
            stays.append(None)
            continue
        h = hit.iloc[0]
        if nc[1] != cur[-1]:
            errors.append(f"{tag}: accommodation city {nc[1]} != tonight's city {cur[-1]}")
        for rule in cons["house rule"]:
            if HOUSE_RULES[rule] in h.house_rules:
                errors.append(f"{tag}: accommodation forbids {rule} ('{h.house_rules}')")
        if cons["room type"] and not ROOM_TYPES[cons["room type"]](h["room type"]):
            errors.append(f"{tag}: room type '{h['room type']}' violates '{cons['room type']}'")
        cost["lodging"] += float(h.price) * math.ceil(people / h["maximum occupancy"])
        stays.append(nc)
    # minimum nights over consecutive identical stays
    i = 0
    while i < len(stays):
        j = i
        while j + 1 < len(stays) and stays[j + 1] == stays[i]:
            j += 1
        if stays[i] is not None:
            mn = float(H[(H.NAME == stays[i][0]) & (H.city == stays[i][1])]["minimum nights"].iloc[0])
            if j - i + 1 < mn:
                errors.append(f"days {i + 1}-{j + 1}: '{stays[i][0]}' needs minimum {int(mn)} nights, stayed {j - i + 1}")
        i = j + 1
    # route
    if route[0] != org or route[-1] != org:
        errors.append(f"route must start and end at {org}: {route}")
    inner = route[1:-1]
    if len(set(inner)) != len(inner) or org in inner:
        errors.append(f"cities must not be revisited: {route}")
    if cons["dest_type"] == "state":
        bad = [c for c in inner if c not in cons["candidate_cities"]]
        if bad:
            errors.append(f"cities {bad} are not in {cons['dest']}")
    elif inner != [cons["dest"]]:
        errors.append(f"destination must be {cons['dest']}: {route}")
    if len(set(inner)) != cons["visiting_city_number"]:
        errors.append(f"visit exactly {cons['visiting_city_number']} cities; plan visits {inner}")
    # transport rules
    if "self-driving" in modes and ({"flight", "taxi"} & set(modes)):
        errors.append(f"self-driving cannot be mixed with flights/taxis: {modes}")
    if cons["transportation"] == "no flight" and "flight" in modes:
        errors.append("plan uses a flight but the user forbids flights")
    if cons["transportation"] == "no self-driving" and "self-driving" in modes:
        errors.append("plan self-drives but the user forbids self-driving")
    missing = sorted(set(cons["cuisine"]) - rest_cuisines_dest)
    if missing:
        errors.append(f"cuisines not covered by restaurants outside {org}: {missing}")
    total = round(sum(cost.values()), 2)
    if total > float(cons["budget"]):
        errors.append(f"total cost {total} exceeds budget {cons['budget']}")
    report = {"valid": not errors, "errors": errors, "warnings": warnings, "route": route,
              "transport_modes": modes, "cost": {k: round(v, 2) for k, v in cost.items()},
              "total_cost": total, "budget": cons["budget"]}
    print(json.dumps(report, indent=2))
    sys.exit(0 if not errors else 1)


# ----------------------------------------------------------------- search CLIs
def show(df: pd.DataFrame, cols: list[str], limit: int):
    if df.empty:
        print("No results.")
        return
    print(df[cols].head(limit).to_string(index=False))
    if len(df) > limit:
        print(f"... {len(df) - limit} more (raise --limit)")


def cmd_search(args, db: DB):
    if args.cmd == "cities":
        log_tool("search_cities")
        cs = db.cities_in_state(args.state)
        print("\n".join(cs) if cs else "Invalid state.")
    elif args.cmd == "accommodations":
        log_tool("search_accommodations")
        cons = {"house rule": [r.strip().lower() for r in args.rules.split(",")] if args.rules else [],
                "room type": args.room_type, "people_number": args.people}
        df = db.lodging(args.city, cons, args.nights)
        show(df, ["NAME", "room type", "price", "rooms_needed", "cost_per_night", "minimum nights",
                  "maximum occupancy", "review rate number", "house_rules"], args.limit)
    elif args.cmd == "attractions":
        log_tool("search_attractions")
        df = db.attractions()
        show(df[df.City.str.lower() == args.city.strip().lower()], ["Name", "Address", "City"], args.limit)
    elif args.cmd == "restaurants":
        log_tool("search_restaurants")
        df = db.restaurants()
        df = df[df.City.str.lower() == args.city.strip().lower()]
        if args.cuisines:
            want = [c.strip().lower() for c in args.cuisines.split(",")]
            df = df[df.Cuisines.str.lower().map(lambda s: any(w in s for w in want))]
        show(df.sort_values(["Average Cost", "Aggregate Rating"], ascending=[True, False]),
             ["Name", "Average Cost", "Cuisines", "Aggregate Rating", "City"], args.limit)
    elif args.cmd == "distance":
        log_tool("search_driving_distance")
        g = db.leg(args.origin, args.destination, args.mode, args.people)
        if g is None:
            print(f"{args.mode}, from {args.origin} to {args.destination}, no valid information.")
        else:
            print(f"{args.mode}, from {g['origin']} to {g['destination']}, duration: {g['duration']}, "
                  f"distance: {g['distance']}, cost per vehicle: {g['unit_cost']}, vehicles: {g['vehicles']}, "
                  f"total cost: {g['cost']}")
    elif args.cmd == "flights":
        log_tool("search_flights")
        f = db.flights()
        df = f[(f.OriginCityName == strip_paren(args.origin)) & (f.DestCityName == strip_paren(args.destination))
               & (f.FlightDate == args.date)]
        if df.empty:
            print(f"There is no flight from {args.origin} to {args.destination} on {args.date}.")
        else:
            show(df.sort_values("Price"), list(df.columns), args.limit)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--data-dir")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("cities"); s.add_argument("--state", required=True)
    s = sub.add_parser("accommodations"); s.add_argument("--city", required=True)
    s.add_argument("--rules", help="comma list of allowances needed: pets,smoking,parties,children under 10,visitors")
    s.add_argument("--room-type", choices=sorted(ROOM_TYPES))
    s.add_argument("--people", type=int, default=1)
    s.add_argument("--nights", type=int, help="only listings whose minimum nights <= this")
    s = sub.add_parser("attractions"); s.add_argument("--city", required=True)
    s = sub.add_parser("restaurants"); s.add_argument("--city", required=True)
    s.add_argument("--cuisines", help="comma list; keep restaurants serving any of them")
    s = sub.add_parser("distance"); s.add_argument("--origin", required=True); s.add_argument("--destination", required=True)
    s.add_argument("--mode", choices=["self-driving", "taxi"], default="self-driving")
    s.add_argument("--people", type=int, default=1)
    s = sub.add_parser("flights"); s.add_argument("--origin", required=True); s.add_argument("--destination", required=True)
    s.add_argument("--date", required=True)
    for name in ["accommodations", "attractions", "restaurants", "flights"]:
        sub.choices[name].add_argument("--limit", type=int, default=40)
    sub.add_parser("reset-log")
    s = sub.add_parser("draft"); s.add_argument("--constraints", required=True); s.add_argument("--out", required=True)
    s.add_argument("--max-routes", type=int, default=50, help="cheapest routes to try for cuisine coverage")
    s = sub.add_parser("validate"); s.add_argument("--constraints", required=True); s.add_argument("--plan", required=True)
    args = p.parse_args()
    if args.cmd == "reset-log":
        TOOL_LOG.unlink(missing_ok=True)
        print(f"tool-call log cleared ({TOOL_LOG})")
        return
    db = DB(find_data_dir(args.data_dir))
    if args.cmd == "draft":
        cmd_draft(args, db)
    elif args.cmd == "validate":
        cmd_validate(args, db)
    else:
        cmd_search(args, db)


if __name__ == "__main__":
    main()

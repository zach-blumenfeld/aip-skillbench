"""Execution step: run every database search the plan needs and keep only usable options.

stdin:  {"state": {"request": {...}, "data_dir": "/app/data"}, ...}
stdout: {"candidates": {...}, "tools_called": [...]}
"""

from __future__ import annotations

import json
import sys

import travel_db as db


def fail(msg: str) -> None:
    print(msg, file=sys.stderr)
    sys.exit(1)


def norm_request(req: dict, data_dir: str) -> dict:
    lc = req.get("local_constraint") or {}
    for k in ("org", "dest", "days", "people_number", "budget"):
        if req.get(k) in (None, ""):
            fail(f"request is missing '{k}'")
    days = int(req["days"])
    k = int(req.get("visiting_city_number") or {3: 1, 5: 2, 7: 3}.get(days, 1))
    if days < 2:
        fail("a round trip needs at least 2 days")
    cuisine = lc.get("cuisine") or []
    if isinstance(cuisine, str):
        cuisine = [c.strip() for c in cuisine.split(",") if c.strip()]
    transport = (lc.get("transportation") or "").strip().lower() or None
    return {
        "org": db.canonical_city(data_dir, req["org"]),
        "dest": str(req["dest"]).strip(),
        "days": days,
        "visiting_city_number": k,
        "dates": list(req.get("date") or []),
        "people": int(req["people_number"]),
        "budget": float(req["budget"]),
        "house_rule": (lc.get("house rule") or lc.get("house_rule") or None),
        "room_type": (lc.get("room type") or lc.get("room_type") or None),
        "cuisine": cuisine,
        "transportation": transport,
    }


def split_nights(total: int, k: int) -> list[int]:
    base, extra = divmod(total, k)
    return [base + (1 if i < extra else 0) for i in range(k)]


def main() -> None:
    payload = json.load(sys.stdin)
    state = payload.get("state", payload)
    data_dir = state.get("data_dir") or db.DEFAULT_DATA_DIR
    r = norm_request(state["request"], data_dir)
    tools: list[str] = []

    # Destination cities: a state expands via search_cities, a city stands alone.
    state_match = [s for s in db.states(data_dir) if s.lower() == r["dest"].lower()]
    if state_match:
        tools.append("search_cities")
        dest_cities = db.search_cities(data_dir, state_match[0])
        dest_state = state_match[0]
    else:
        dest_cities = [db.canonical_city(data_dir, r["dest"])]
        dest_state = None
    dest_cities = [c for c in dest_cities if c.lower() != r["org"].lower()]

    k = r["visiting_city_number"]
    nights = split_nights(r["days"] - 1, k)
    # Day (1-based) on which each leg is travelled: arrival in city i, then the return.
    leg_days = [1 + sum(nights[:i]) for i in range(k)] + [r["days"]]

    allow_flight = r["transportation"] != "no flight"
    allow_ground_self = r["transportation"] != "no self-driving"
    tools += ["search_accommodations", "search_restaurants", "search_attractions"]

    cities: dict = {}
    excluded: dict = {}
    for city in dest_cities:
        acc = db.search_accommodations(data_dir, city)
        rest = db.search_restaurants(data_dir, city)
        attr = db.search_attractions(data_dir, city)
        valid = [row for row in acc.to_dict(orient="records")
                 if db.accommodation_ok(row, r["house_rule"], r["room_type"])]
        if not valid:
            excluded[city] = f"no accommodation satisfies house rule={r['house_rule']} room type={r['room_type']} ({len(acc)} listed)"
            continue
        if rest.empty:
            excluded[city] = "no restaurants in database"
            continue
        cities[city] = {
            "accommodations": [{
                "name": a["NAME"], "price": float(a["price"]), "room_type": a["room type"],
                "house_rules": a["house_rules"], "minimum_nights": float(a["minimum nights"]),
                "maximum_occupancy": int(a["maximum occupancy"]), "rating": float(a["review rate number"]),
                "nightly_cost": float(a["price"]) * db.rooms_needed(r["people"], a["maximum occupancy"]),
            } for a in valid],
            "restaurants": [{
                "name": x["Name"], "cuisines": x["Cuisines"], "cost": float(x["Average Cost"]),
                "rating": float(x["Aggregate Rating"]),
            } for x in rest.to_dict(orient="records")],
            "attractions": [{"name": x["Name"], "address": x["Address"]} for x in attr.to_dict(orient="records")],
        }

    # Ground legs between every ordered pair the route could use.
    nodes = [r["org"]] + list(cities)
    ground: dict = {}
    tools.append("search_driving_distance")
    for o in nodes:
        for d in nodes:
            if o == d or (o == r["org"] and d == r["org"]):
                continue
            info = db.search_driving_distance(data_dir, o, d, "driving")
            if info["distance_km"] is not None:
                ground[f"{o}->{d}"] = {
                    "duration": info["duration"], "distance": info["distance"], "hours": info["hours"],
                    "self_driving_cost": db.leg_cost(info["distance_km"], "self-driving"),
                    "taxi_cost": db.leg_cost(info["distance_km"], "taxi"),
                }

    # Flights: cheapest option for each pair on each date a leg could be travelled.
    flights: dict = {}
    if allow_flight and r["dates"]:
        tools.append("search_flights")
        for leg_i, day in enumerate(leg_days):
            if day - 1 >= len(r["dates"]):
                continue
            date = r["dates"][day - 1]
            if leg_i == 0:
                pairs = [(r["org"], c) for c in cities]
            elif leg_i == k:
                pairs = [(c, r["org"]) for c in cities]
            else:
                pairs = [(a, b) for a in cities for b in cities if a != b]
            for o, d in pairs:
                key = f"{o}->{d}@{date}"
                if key in flights:
                    continue
                f = db.search_flights(data_dir, o, d, date)
                if not f.empty:
                    best = f.sort_values(["Price", "DepTime"]).iloc[0]
                    flights[key] = {
                        "flight_number": best["Flight Number"], "price": float(best["Price"]),
                        "dep_time": best["DepTime"], "arr_time": best["ArrTime"],
                        "elapsed": best["ActualElapsedTime"], "options": int(len(f)),
                    }

    out = {
        "candidates": {
            "request": r,
            "dest_state": dest_state,
            "dest_cities": dest_cities,
            "nights": nights,
            "leg_days": leg_days,
            "modes_allowed": {"flight": allow_flight, "self_driving": allow_ground_self, "taxi": True},
            "cities": cities,
            "excluded_cities": excluded,
            "ground": ground,
            "flights": flights,
        },
        "tools_called": tools,
    }
    json.dump(out, sys.stdout, default=str)


if __name__ == "__main__":
    main()

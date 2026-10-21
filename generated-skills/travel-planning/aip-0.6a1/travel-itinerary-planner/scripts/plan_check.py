"""Re-check a finished itinerary against the database and the request.

Shared by build_plan.py (report) and write_itinerary.py (final gate). Every
entity is looked up again in the database, so a hand-repaired plan gets the
same scrutiny as a generated one. Cost rules (per the source tools and the
benchmark's budget convention):
  self-driving  leg cost x ceil(people/5) cars      (cost = int(km * 0.05))
  taxi          leg cost x ceil(people/4) cabs      (cost = int(km))
  flight        ticket price x people
  meal          Average Cost x people
  night         price x ceil(people / maximum occupancy)
"""

from __future__ import annotations

import re

import travel_db as db

DAY_KEYS = ["day", "current_city", "transportation", "breakfast", "lunch", "dinner", "attraction", "accommodation"]
FROM_TO = re.compile(r"from\s+(.+?)\s+to\s+(.+?)\s*(?:,|$)", re.IGNORECASE)


def split_entity(text: str) -> tuple[str, str]:
    name, _, city = str(text).strip().rpartition(", ")
    return (name.strip(), city.strip()) if name else (str(text).strip(), "")


def day_cities(current_city: str) -> list[str]:
    m = FROM_TO.search(current_city or "")
    return [m.group(1).strip(), m.group(2).strip()] if m else [str(current_city).strip()]


def blank(value) -> bool:
    return value is None or str(value).strip() in ("", "-")


def check(itinerary: dict, r: dict, data_dir: str) -> dict:
    v: list[str] = []
    people, org = r["people"], r["org"]
    plan = itinerary.get("plan") or []
    cost = {"transport": 0.0, "meals": 0.0, "accommodation": 0.0}

    if len(plan) != r["days"]:
        v.append(f"plan has {len(plan)} days, request needs {r['days']}")
    if not isinstance(itinerary.get("tool_called"), list) or not itinerary["tool_called"]:
        v.append("tool_called must be a non-empty list of the search skills used")

    modes, visited, seen_rest, seen_attr = set(), [], set(), set()
    cuisines_hit: set[str] = set()
    stays: list[tuple[str, str] | None] = []
    dest_cities = None
    state_cities = db.search_cities(data_dir, r["dest"])
    if isinstance(state_cities, list):
        dest_cities = {c.lower() for c in state_cities}

    for i, d in enumerate(plan, start=1):
        missing = [k for k in DAY_KEYS if k not in d]
        if missing:
            v.append(f"day {i}: missing keys {missing}")
            continue
        if d["day"] != i:
            v.append(f"day {i}: 'day' field is {d['day']!r}")
        cities = day_cities(d["current_city"])
        for c in cities:
            if c != org and c not in visited:
                visited.append(c)
        if i == 1 and (len(cities) != 2 or cities[0] != org):
            v.append(f"day 1: current_city must be 'from {org} to <city>'")
        if i == len(plan) and (len(cities) != 2 or cities[1] != org):
            v.append(f"day {i}: current_city must be 'from <city> to {org}'")

        t = str(d["transportation"])
        if not blank(t):
            m = FROM_TO.search(t)
            low = t.lower()
            if not m:
                v.append(f"day {i}: transportation lacks 'from A to B': {t!r}")
            elif "flight" in low:
                modes.add("flight")
                num = re.search(r"(F\d+)", t)
                f = db.search_flights(data_dir, m.group(1), m.group(2), r["dates"][i - 1]) if r["dates"] else None
                f = f[f["Flight Number"] == num.group(1)] if f is not None and num else None
                if f is None or f.empty:
                    v.append(f"day {i}: flight not found in database: {t!r}")
                else:
                    cost["transport"] += float(f["Price"].iloc[0]) * people
            else:
                mode = "self-driving" if "self-driving" in low else "taxi" if "taxi" in low else None
                if not mode:
                    v.append(f"day {i}: unknown transportation mode: {t!r}")
                else:
                    modes.add(mode)
                    info = db.search_driving_distance(data_dir, m.group(1), m.group(2), mode)
                    if info["cost"] is None:
                        v.append(f"day {i}: no valid {mode} route {m.group(1)} -> {m.group(2)}")
                    else:
                        cost["transport"] += info["cost"] * db.vehicles(people, mode)
        elif len(cities) == 2:
            v.append(f"day {i}: travel day without transportation")

        for meal in ("breakfast", "lunch", "dinner"):
            val = d[meal]
            if blank(val):
                continue
            name, city = split_entity(val)
            if city not in cities:
                v.append(f"day {i} {meal}: {city!r} is not in current_city {cities}")
            hit = db.search_restaurants(data_dir, city)
            hit = hit[hit["Name"] == name] if not hit.empty else hit
            if hit.empty:
                v.append(f"day {i} {meal}: restaurant not in database: {val!r}")
                continue
            if (name, city) in seen_rest:
                v.append(f"day {i} {meal}: restaurant repeated: {val!r}")
            seen_rest.add((name, city))
            cost["meals"] += float(hit["Average Cost"].iloc[0]) * people
            if city != org:
                cuisines_hit |= db.cuisine_tokens(hit["Cuisines"].iloc[0])

        att = str(d["attraction"])
        if not blank(att):
            if not att.strip().endswith(";"):
                v.append(f"day {i}: attraction list must end with ';'")
            for item in [x for x in att.split(";") if x.strip()]:
                name, city = split_entity(item)
                if city not in cities:
                    v.append(f"day {i} attraction: {city!r} is not in current_city {cities}")
                hit = db.search_attractions(data_dir, city)
                if hit.empty or (hit["Name"] == name).sum() == 0:
                    v.append(f"day {i} attraction: not in database: {item.strip()!r}")
                if (name, city) in seen_attr:
                    v.append(f"day {i} attraction: repeated: {item.strip()!r}")
                seen_attr.add((name, city))

        acc = d["accommodation"]
        if blank(acc):
            stays.append(None)
            if i < len(plan):
                v.append(f"day {i}: no accommodation on a night away from home")
            continue
        name, city = split_entity(acc)
        if city not in cities:
            v.append(f"day {i} accommodation: {city!r} is not in current_city {cities}")
        hit = db.search_accommodations(data_dir, city)
        hit = hit[hit["NAME"] == name] if not hit.empty else hit
        if hit.empty:
            v.append(f"day {i} accommodation: not in database: {acc!r}")
            stays.append(None)
            continue
        row = hit.iloc[0].to_dict()
        if not db.accommodation_ok(row, r.get("house_rule"), r.get("room_type")):
            v.append(f"day {i} accommodation: violates house rule/room type ({row['house_rules']}, {row['room type']})")
        cost["accommodation"] += float(row["price"]) * db.rooms_needed(people, row["maximum occupancy"])
        stays.append((name, city, float(row["minimum nights"])))

    # Minimum nights: each consecutive run at one place must be long enough.
    run, prev = 0, None
    for s in stays + [None]:
        key = s[:2] if s else None
        if key and key == (prev[:2] if prev else None):
            run += 1
        else:
            if prev and run < prev[2]:
                v.append(f"accommodation {prev[0]!r} booked {run} night(s), minimum is {int(prev[2])}")
            run = 1 if s else 0
        prev = s

    if "self-driving" in modes and modes & {"flight", "taxi"}:
        v.append(f"conflicting transportation modes: {sorted(modes)}")
    if r.get("transportation") == "no flight" and "flight" in modes:
        v.append("request forbids flights")
    if r.get("transportation") == "no self-driving" and "self-driving" in modes:
        v.append("request forbids self-driving")
    if len(visited) != r["visiting_city_number"]:
        v.append(f"visits {len(visited)} cities {visited}, request needs {r['visiting_city_number']}")
    if dest_cities is not None:
        bad = [c for c in visited if c.lower() not in dest_cities]
        if bad:
            v.append(f"cities outside {r['dest']}: {bad}")
    missing_cuisine = [c for c in r.get("cuisine") or [] if c.lower() not in cuisines_hit]
    if missing_cuisine:
        v.append(f"requested cuisines not served at any destination meal: {missing_cuisine}")

    total = round(sum(cost.values()), 2)
    if total > r["budget"]:
        v.append(f"total cost {total} exceeds budget {r['budget']}")
    return {
        "violations": v,
        "cost": {k: round(x, 2) for k, x in cost.items()} | {"total": total, "budget": r["budget"],
                                                            "remaining": round(r["budget"] - total, 2)},
        "route": [org] + visited + [org],
        "modes": sorted(modes),
        "cuisines_covered": [c for c in r.get("cuisine") or [] if c.lower() in cuisines_hit],
    }

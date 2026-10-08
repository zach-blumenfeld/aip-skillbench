"""AIP execution step: check a day-by-day travel plan against the sandbox and every constraint.

stdin:  {"currentState": {plan, origin, destination, trip_dates, people_number, budget,
                          local_constraint, visiting_city_number, data_dir, ...}, ...}
stdout: {"plan_valid", "violations", "warnings", "total_cost", "cost_breakdown",
         "validation_attempts", "validation_outcome"}

validation_outcome is "pass" when there are no violations, "fail" when there are and
fewer than MAX_ATTEMPTS validations have run, and "give-up" after MAX_ATTEMPTS failures.
"""

from __future__ import annotations

import json
import math
import re
import sys

import travel_db as db

MAX_ATTEMPTS = 3
KEYS = ["days", "current_city", "transportation", "breakfast", "attraction", "lunch",
        "dinner", "accommodation"]
EMPTY = ("", "-", None)


def split_name_city(text: str) -> tuple[str, str] | None:
    """'Name, with, commas, City' -> ('Name, with, commas', 'City')."""
    if not isinstance(text, str) or "," not in text:
        return None
    name, city = text.rsplit(",", 1)
    city = db.before_paren(city)
    return name.strip(), city.strip()


def from_to(text: str) -> tuple[str, str] | None:
    m = re.search(r"from\s+(.+?)\s+to\s+([^,]+)", str(text), flags=re.I)
    if not m:
        return None
    return db.before_paren(m.group(1)), db.before_paren(m.group(2))


def norm_list(v) -> list[str]:
    if v in (None, "", "-", "null", "None"):
        return []
    if isinstance(v, str):
        return [s.strip() for s in v.replace(";", ",").split(",") if s.strip()]
    return [str(s).strip() for s in v if str(s).strip()]


def lc_get(lc: dict, *keys):
    for k in keys:
        if k in lc and lc[k] not in (None, "", "-", [], "null", "None"):
            return lc[k]
    return None


def main() -> None:
    payload = json.load(sys.stdin)
    st = payload.get("currentState", payload)
    attempts = int(st.get("validation_attempts") or 0) + 1
    violations: list[str] = []
    warnings: list[str] = []

    plan = st.get("plan")
    if isinstance(plan, dict):
        plan = plan.get("plan") or plan.get("days") or plan.get("itinerary")
    if not isinstance(plan, list) or not plan:
        out(False, ["plan must be a non-empty list of day objects"], [], 0, {}, attempts)
        return

    data_dir = db.find_data_dir(st.get("data_dir") or None)
    origin = db.before_paren(st["origin"])
    destination = db.before_paren(st["destination"])
    dates = list(st.get("trip_dates") or [])
    days = len(dates) or int(st.get("days") or len(plan))
    people = max(1, int(st.get("people_number") or 1))
    budget = float(st.get("budget") or 0)
    n_cities = int(st.get("visiting_city_number") or 1)
    lc = st.get("local_constraint") or {}
    house_rules = norm_list(lc_get(lc, "house_rule", "house rule"))
    room_type = (lc_get(lc, "room_type", "room type") or "")
    room_type = room_type.strip().lower() if isinstance(room_type, str) else ""
    cuisines = [c.lower() for c in norm_list(lc_get(lc, "cuisine", "cuisines"))]
    tr = lc_get(lc, "transportation") or ""
    tr = (tr if isinstance(tr, str) else " ".join(norm_list(tr))).lower()

    city_states = db.load_city_states(data_dir)
    state_cities = db.cities_for_state(city_states, destination)
    flights = {f["Flight Number"]: f for f in db.load_flights(data_dir, set(dates) or None)}
    dists = db.load_distances(data_dir)
    rests = db.load_restaurants(data_dir)
    rest_idx: dict[tuple, list] = {}
    for r in rests:
        rest_idx.setdefault((r["Name"].strip(), r["City"].lower()), []).append(r)
    atts = {(a["Name"].strip(), a["City"].lower()) for a in db.load_attractions(data_dir)}
    acc_idx: dict[tuple, list] = {}
    for a in db.load_accommodations(data_dir):
        acc_idx.setdefault((a["NAME"].strip(), a["city"].lower()), []).append(a)

    if len(plan) != days:
        violations.append(f"plan has {len(plan)} days but the trip has {days}")

    cost = {"transportation": 0.0, "accommodation": 0.0, "meals": 0.0}
    used_rest: list[str] = []
    used_att: list[str] = []
    modes: set[str] = set()
    sequence: list[str] = []  # cities in visiting order, consecutive duplicates collapsed
    acc_runs: list[list] = []  # [name_city, count, row]
    dest_rest_cuisines: set[str] = set()

    for i, unit in enumerate(plan):
        d = i + 1
        if not isinstance(unit, dict):
            violations.append(f"day {d}: not an object")
            continue
        missing = [k for k in KEYS if k not in unit]
        if missing:
            violations.append(f"day {d}: missing keys {missing}")
        cc = str(unit.get("current_city", ""))
        ft = from_to(cc)
        if ft:
            here = [ft[0], ft[1]]
            for c in here:
                if not sequence or sequence[-1] != c:
                    sequence.append(c)
        else:
            here = [db.before_paren(cc)]
            if not sequence or sequence[-1] != here[0]:
                sequence.append(here[0])
        here_l = [c.lower() for c in here]
        date = dates[i] if i < len(dates) else None

        # Transportation.
        t = unit.get("transportation")
        if ft and t in EMPTY:
            violations.append(f"day {d}: travel day without transportation")
        if t not in EMPTY:
            tl = str(t).lower()
            leg = from_to(t) or ft
            if "flight number" in tl:
                modes.add("flight")
                m = re.search(r"Flight Number:\s*(\w+)", str(t), flags=re.I)
                f = flights.get(m.group(1)) if m else None
                if f is None:
                    violations.append(f"day {d}: flight {m.group(1) if m else '?'} not found on the trip dates")
                else:
                    if leg and (f["OriginCityName"], f["DestCityName"]) != leg:
                        violations.append(f"day {d}: flight {f['Flight Number']} is "
                                          f"{f['OriginCityName']}->{f['DestCityName']}, not {leg[0]}->{leg[1]}")
                    if date and f["FlightDate"] != date:
                        violations.append(f"day {d}: flight {f['Flight Number']} flies {f['FlightDate']}, not {date}")
                    cost["transportation"] += f["Price"] * people
            elif "self-driving" in tl or "self-drive" in tl or "taxi" in tl:
                mode = "taxi" if "taxi" in tl else "self-driving"
                modes.add(mode)
                info = db.search_distance(dists, *(leg or ("", "")), mode)
                if not info["valid"]:
                    violations.append(f"day {d}: no valid {mode} information for {leg}")
                else:
                    per = 4 if mode == "taxi" else 5
                    cost["transportation"] += info["cost"] * math.ceil(people / per)
            else:
                violations.append(f"day {d}: unrecognised transportation {t!r}")
            if leg and ft and leg != ft:
                violations.append(f"day {d}: transportation leg {leg} differs from current_city {ft}")

        # Meals.
        for meal in ("breakfast", "lunch", "dinner"):
            v = unit.get(meal)
            if v in EMPTY:
                if not ft:
                    violations.append(f"day {d}: {meal} missing on a non-travel day")
                continue
            nc = split_name_city(v)
            if not nc:
                violations.append(f"day {d}: {meal} {v!r} is not 'Name, City'")
                continue
            rows = rest_idx.get((nc[0], nc[1].lower()))
            if not rows:
                violations.append(f"day {d}: restaurant {v!r} not in the restaurant data")
                continue
            if nc[1].lower() not in here_l:
                violations.append(f"day {d}: {meal} in {nc[1]} but current city is {cc!r}")
            if nc[0] in used_rest:
                violations.append(f"day {d}: restaurant {nc[0]!r} repeated")
            used_rest.append(nc[0])
            cost["meals"] += rows[0]["Average Cost"] * people
            if nc[1].lower() != origin.lower():
                dest_rest_cuisines |= {x.lower() for x in rows[0]["cuisine_list"]}

        # Attractions.
        v = unit.get("attraction")
        if v in EMPTY:
            if not ft:
                violations.append(f"day {d}: no attraction on a non-travel day")
        else:
            for part in [p for p in str(v).split(";") if p.strip()]:
                nc = split_name_city(part)
                if not nc or (nc[0], nc[1].lower()) not in atts:
                    violations.append(f"day {d}: attraction {part.strip()!r} not in the attraction data")
                    continue
                if nc[1].lower() not in here_l:
                    violations.append(f"day {d}: attraction in {nc[1]} but current city is {cc!r}")
                if nc[0] in used_att:
                    violations.append(f"day {d}: attraction {nc[0]!r} repeated")
                used_att.append(nc[0])

        # Accommodation.
        v = unit.get("accommodation")
        if v in EMPTY:
            if d != days:
                violations.append(f"day {d}: accommodation missing (required every night but the last day)")
            acc_runs.append([None, 0, None])
        else:
            if d == days:
                warnings.append(f"day {d}: accommodation on the last day adds cost; usually '-'")
            nc = split_name_city(v)
            rows = acc_idx.get((nc[0], nc[1].lower())) if nc else None
            if not rows:
                violations.append(f"day {d}: accommodation {v!r} not in the accommodation data")
                acc_runs.append([None, 0, None])
            else:
                a = rows[0]
                stay_city = (ft[1] if ft else here[0]).lower()
                if nc[1].lower() != stay_city:
                    violations.append(f"day {d}: accommodation in {nc[1]} but the night is in {stay_city}")
                if room_type:
                    rt = a["room type"]
                    bad = ((room_type == "not shared room" and rt == "Shared room")
                           or (room_type == "shared room" and rt != "Shared room")
                           or (room_type == "private room" and rt != "Private room")
                           or (room_type in ("entire room", "entire home/apt") and rt != "Entire home/apt"))
                    if bad:
                        violations.append(f"day {d}: room type {rt!r} violates '{room_type}'")
                for rule in house_rules:
                    if f"no {rule.lower()}" in a["house_rules"].lower():
                        violations.append(f"day {d}: house rules {a['house_rules']!r} forbid {rule}")
                cost["accommodation"] += a["price"] * math.ceil(people / a["maximum occupancy"])
                if acc_runs and acc_runs[-1][0] == v:
                    acc_runs[-1][1] += 1
                else:
                    acc_runs.append([v, 1, a])

    # Minimum nights.
    for name, count, a in acc_runs:
        if a and count < a["minimum nights"]:
            violations.append(f"accommodation {name!r}: {count} night(s) < minimum nights {a['minimum nights']:g}")

    # City sequence and visited cities.
    if sequence:
        if sequence[0].lower() != origin.lower():
            violations.append(f"trip must start from {origin}, starts from {sequence[0]}")
        if sequence[-1].lower() != origin.lower():
            violations.append(f"trip must end back in {origin}, ends in {sequence[-1]}")
    visited = [c for c in sequence[1:-1]]
    if len({c.lower() for c in visited}) != len(visited):
        violations.append(f"a city is revisited: {visited}")
    if origin.lower() in (c.lower() for c in visited):
        violations.append("the trip returns to the origin mid-trip")
    if len(visited) != n_cities:
        violations.append(f"visits {len(visited)} cities {visited}, request needs {n_cities}")
    if state_cities is not None:
        allowed = {c.lower() for c in state_cities}
        outside = [c for c in visited if c.lower() not in allowed]
        if outside:
            violations.append(f"cities {outside} are not in {destination}")
    elif visited and any(c.lower() != destination.lower() for c in visited):
        violations.append(f"visited cities {visited} are not the destination {destination}")

    # Transportation rules.
    if "flight" in modes and "self-driving" in modes:
        violations.append("flights and self-driving are mixed in one trip")
    if "no flight" in tr and "flight" in modes:
        violations.append("request forbids flights")
    if ("no self-driving" in tr or "no self driving" in tr) and "self-driving" in modes:
        violations.append("request forbids self-driving")

    # Cuisines.
    missing_cz = [c for c in cuisines if c not in dest_rest_cuisines]
    if missing_cz:
        violations.append(f"required cuisines not covered at the destination: {missing_cz}")

    total = round(sum(cost.values()), 2)
    if budget and total > budget:
        violations.append(f"total cost {total} exceeds budget {budget}")

    out(not violations, violations, warnings, total, {k: round(v, 2) for k, v in cost.items()}, attempts)


def out(valid, violations, warnings, total, breakdown, attempts):
    outcome = "pass" if valid else ("give-up" if attempts >= MAX_ATTEMPTS else "fail")
    print(json.dumps({"plan_valid": valid, "violations": violations, "warnings": warnings,
                      "total_cost": total, "cost_breakdown": breakdown,
                      "validation_attempts": attempts, "validation_outcome": outcome},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()

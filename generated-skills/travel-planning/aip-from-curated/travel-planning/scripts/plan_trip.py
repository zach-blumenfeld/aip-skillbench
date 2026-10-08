"""AIP execution step: search the sandbox for the cheapest valid trip and draft a day-by-day plan.

stdin:  {"currentState": {...parsed query...}, "assets": {...}, "expects": [...]}
stdout: {"data_dir", "trip_dates", "candidate_cities", "draft_plan", "draft_cost",
         "cost_breakdown", "route", "alternatives", "candidates", "planner_notes", "feasible"}

The search enumerates every ordered choice of `visiting_city_number` cities from the
destination (a state's cities, or the single destination city), every split of the
trip's nights across them, and both transport regimes (flight+taxi, self-driving+taxi;
flights and self-driving never mix). Each option is costed with the evaluation rules:
flight price x people, self-driving cost x ceil(people/5), taxi cost x ceil(people/4),
accommodation price x ceil(people/maximum occupancy) per night, meals Average Cost x people.
"""

from __future__ import annotations

import functools
import itertools
import json
import math
import sys
from datetime import date, timedelta

import travel_db as db

MEALS = {"breakfast": 8 * 60, "lunch": 12 * 60 + 30, "dinner": 19 * 60}
GROUND_DEPART = 9 * 60  # assumed departure time for self-driving / taxi legs


# --------------------------------------------------------------- utilities ---

MAX_PLANNER_ATTEMPTS = 2
CTX: dict = {"planner_attempts": 1, "data_dir": "", "trip_dates": [], "candidate_cities": [],
             "destination_kind": "", "diagnostics": {}}


def fail(msg: str) -> None:
    """Report an infeasible search, keeping what is known so the next step can act on it."""
    final = CTX["planner_attempts"] >= MAX_PLANNER_ATTEMPTS
    print(json.dumps({**CTX, "feasible": False, "planner_notes": [msg], "draft_plan": [], "plan": [],
                      "draft_cost": 0.0, "cost_breakdown": {}, "candidates": {},
                      "route": {}, "alternatives": [],
                      "planner_outcome": "infeasible-final" if final else "infeasible",
                      "violations": [], "validation_outcome": "not-run"}, ensure_ascii=False))
    sys.exit(0)


def hhmm(t: str) -> int | None:
    try:
        h, m = str(t).strip().split(":")[:2]
        return int(h) * 60 + int(m)
    except (ValueError, AttributeError):
        return None


def duration_minutes(text: str) -> int:
    """'2 hours 33 minutes' / '1 hour 1 min' / '45 mins' -> minutes."""
    total, num = 0, None
    for tok in str(text).replace(",", " ").split():
        if tok.replace(".", "", 1).isdigit():
            num = float(tok)
        elif num is not None:
            if tok.startswith("day"):
                total += num * 1440
            elif tok.startswith("hour"):
                total += num * 60
            elif tok.startswith("min"):
                total += num
            num = None
    return int(total)


def constraint(lc: dict, *keys: str):
    for k in keys:
        if k in lc and lc[k] not in (None, "", "-", [], "null", "None"):
            return lc[k]
    return None


def norm_list(v) -> list[str]:
    if v is None:
        return []
    if isinstance(v, str):
        return [s.strip() for s in v.replace(";", ",").split(",") if s.strip()]
    return [str(s).strip() for s in v if str(s).strip()]


def accommodation_ok(a: dict, room_type: str | None, house_rule: str | None) -> bool:
    if room_type:
        rt = room_type.strip().lower()
        t = a["room type"]
        if rt == "not shared room" and t == "Shared room":
            return False
        if rt == "shared room" and t != "Shared room":
            return False
        if rt == "private room" and t != "Private room":
            return False
        if rt in ("entire room", "entire home/apt", "entire home") and t != "Entire home/apt":
            return False
    for rule in norm_list(house_rule):
        if f"no {rule.lower()}" in a["house_rules"].lower():
            return False
    return True


def compositions(total: int, parts: int):
    """All ways to write `total` as an ordered sum of `parts` positive integers."""
    if parts == 1:
        if total >= 1:
            yield (total,)
        return
    for first in range(1, total - parts + 2):
        for rest in compositions(total - first, parts - 1):
            yield (first,) + rest


def name_city(name: str, city: str) -> str:
    return f"{name}, {city}"


# ------------------------------------------------------------------- main ---

def main() -> None:
    payload = json.load(sys.stdin)
    st = payload.get("currentState", payload)
    CTX["planner_attempts"] = int(st.get("planner_attempts") or 0) + 1
    CTX["data_dir"] = st.get("data_dir") or ""

    try:
        data_dir = db.find_data_dir(st.get("data_dir") or None)
    except FileNotFoundError as exc:
        fail(str(exc))
    CTX["data_dir"] = str(data_dir)

    origin = db.before_paren(st["origin"])
    destination = db.before_paren(st["destination"])
    days = int(st["days"])
    n_cities = max(1, int(st.get("visiting_city_number") or 1))
    people = max(1, int(st.get("people_number") or 1))
    budget = float(st.get("budget") or 0)
    lc = st.get("local_constraint") or {}
    house_rule = constraint(lc, "house_rule", "house rule")
    room_type = constraint(lc, "room_type", "room type")
    cuisines = norm_list(constraint(lc, "cuisine", "cuisines"))
    transport_rule = (constraint(lc, "transportation") or "")
    transport_rule = transport_rule.lower() if isinstance(transport_rule, str) else \
        " ".join(norm_list(transport_rule)).lower()
    no_flight = "no flight" in transport_rule
    no_driving = "no self-driving" in transport_rule or "no self driving" in transport_rule

    try:
        start = date.fromisoformat(str(st["start_date"]).strip())
    except ValueError:
        fail(f"start_date must be YYYY-MM-DD, got {st['start_date']!r}")
    dates = [(start + timedelta(days=i)).isoformat() for i in range(days)]
    CTX["trip_dates"] = dates
    if days < 2:
        fail("Trips need at least 2 days (outbound and return).")
    nights = days - 1
    if n_cities > nights:
        fail(f"{n_cities} cities cannot fit in {nights} nights.")

    notes: list[str] = []
    city_states = db.load_city_states(data_dir)
    state_cities = db.cities_for_state(city_states, destination)
    if state_cities is not None:
        candidates = [c for c in state_cities if c.lower() != origin.lower()]
        dest_kind = "state"
    else:
        candidates = [destination]
        dest_kind = "city"
        if n_cities > 1:
            notes.append(f"Destination {destination!r} is a city, not a state; "
                         f"visiting it alone instead of {n_cities} cities.")
            n_cities = 1
        if db.state_of_city(city_states, destination) is None:
            notes.append(f"{destination!r} is not in the city list; lookups may be empty.")

    CTX["candidate_cities"] = candidates
    CTX["destination_kind"] = dest_kind
    accs = db.load_accommodations(data_dir)
    rests = db.load_restaurants(data_dir)
    atts = db.load_attractions(data_dir)
    dists = db.load_distances(data_dir)
    all_cities = set(candidates) | {origin}
    flights = db.load_flights(data_dir, set(dates), all_cities)

    # Per-city resources.
    city_info: dict[str, dict] = {}
    for c in candidates:
        ca = [a for a in db.by_city(accs, c, "city") if accommodation_ok(a, room_type, house_rule)]
        for a in ca:
            a["_nightly"] = a["price"] * math.ceil(people / a["maximum occupancy"])
        ca.sort(key=lambda a: (a["_nightly"], -a["review rate number"]))
        cr = sorted(db.by_city(rests, c, "City"), key=lambda r: (r["Average Cost"], -r["Aggregate Rating"]))
        cat = db.by_city(atts, c, "City")
        city_info[c] = {"acc": ca, "rest": cr, "att": cat}

    # Transport options per (from, to, date) and regime.
    flight_index: dict[tuple, list] = {}
    for f in flights:
        flight_index.setdefault((f["OriginCityName"], f["DestCityName"], f["FlightDate"]), []).append(f)
    for v in flight_index.values():
        v.sort(key=lambda f: (f["Price"], f["DepTime"]))

    leg_cache: dict[tuple, dict | None] = {}

    def best_leg(a: str, b: str, d: str, regime: str) -> dict | None:
        key = (a, b, d, regime)
        if key in leg_cache:
            return leg_cache[key]
        opts = []
        if regime == "flight" and not no_flight:
            for f in flight_index.get((a, b, d), [])[:1]:
                opts.append({"mode": "flight", "cost": f["Price"] * people, "flight": f})
        if regime == "driving" and not no_driving:
            info = db.search_distance(dists, a, b, "self-driving")
            if info["valid"]:
                opts.append({"mode": "self-driving", "cost": info["cost"] * math.ceil(people / 5),
                             "info": info})
        info = db.search_distance(dists, a, b, "taxi")
        if info["valid"]:
            opts.append({"mode": "taxi", "cost": info["cost"] * math.ceil(people / 4), "info": info})
        best = min(opts, key=lambda o: o["cost"]) if opts else None
        leg_cache[key] = best
        return best

    @functools.lru_cache(maxsize=None)
    def best_acc(c: str, n: int) -> dict | None:
        for a in city_info[c]["acc"]:
            if a["minimum nights"] <= n:
                return a
        return None

    # Rough meal estimate for ranking: 3 cheapest-per-slot restaurants per day in the city.
    def meal_estimate(c: str, n: int) -> float:
        costs = [r["Average Cost"] for r in city_info[c]["rest"][: 3 * (n + 1)]]
        return sum(costs) * people

    want_cz = {c.lower() for c in cuisines}
    city_cz = {c: {x.lower() for r in city_info[c]["rest"] for x in r["cuisine_list"]} for c in candidates}

    usable = [c for c in candidates if city_info[c]["acc"] and city_info[c]["rest"]]
    if len(usable) < n_cities:
        notes.append(f"Only {len(usable)} destination cities have both matching accommodations "
                     f"and restaurants; need {n_cities}.")

    options = []
    regimes = [r for r in ("flight", "driving") if not (r == "flight" and no_flight)
               and not (r == "driving" and no_driving)] or ["taxi-only"]
    for route in itertools.permutations(usable, n_cities):
        for split in compositions(nights, n_cities):
            accs_sel = []
            acc_cost = 0.0
            for c, n in zip(route, split):
                a = best_acc(c, n)
                if a is None:
                    break
                accs_sel.append(a)
                acc_cost += a["_nightly"] * n
            else:
                stops = [origin, *route, origin]
                tdays = [0]
                for n in split:
                    tdays.append(tdays[-1] + n)
                for regime in regimes:
                    legs = []
                    for i in range(len(stops) - 1):
                        leg = best_leg(stops[i], stops[i + 1], dates[tdays[i]], regime)
                        if leg is None:
                            break
                        legs.append(leg)
                    else:
                        tcost = sum(l["cost"] for l in legs)
                        mcost = sum(meal_estimate(c, n) for c, n in zip(route, split))
                        unevenness = max(split) - min(split)
                        covered = set().union(*(city_cz[c] for c in route))
                        missing_cz = len(want_cz - covered)
                        # Every full day in a city needs at least one attraction.
                        att_short = sum(max(0, (n - 1) - len(city_info[c]["att"]))
                                        for c, n in zip(route, split))
                        options.append({"route": route, "split": split, "transfer_days": tdays,
                                        "legs": legs, "accs": accs_sel, "est_cost": tcost + acc_cost + mcost,
                                        "unevenness": unevenness, "regime": regime,
                                        "missing_cz": missing_cz, "att_short": att_short})
    if not options:
        # Say per city what blocked it, so the request can be re-read or the plan built by hand.
        diag = {}
        for c in candidates:
            in_any = any(best_leg(origin, c, d, r) for d in dates[:-1] for r in regimes)
            out_any = any(best_leg(c, origin, d, r) for d in dates[1:] for r in regimes)
            all_acc = db.by_city(accs, c, "city")
            diag[c] = {
                "accommodations_in_city": len(all_acc),
                "accommodations_matching_room_and_house_rule": len(city_info[c]["acc"]),
                "min_nights_of_matching": sorted({a["minimum nights"] for a in city_info[c]["acc"]})[:5],
                "restaurants": len(city_info[c]["rest"]),
                "attractions": len(city_info[c]["att"]),
                "transport_from_origin_any_day": in_any,
                "transport_to_origin_any_day": out_any,
            }
        CTX["diagnostics"] = diag
        fail("No feasible combination of route, transport and accommodation in the sandbox. "
             + " ".join(notes))

    def rank(o):
        over = budget > 0 and o["est_cost"] > budget
        # Cuisine coverage and attraction availability first, then budget,
        # then the most even split, then cost.
        if over:
            return (o["missing_cz"], o["att_short"], over, 0, o["est_cost"])
        return (o["missing_cz"], o["att_short"], over, o["unevenness"], o["est_cost"])

    options.sort(key=rank)
    best = options[0]

    # ------------------------------------------------------- build the plan ---
    used_rest: set[str] = set()
    used_att: set[str] = set()
    route, split, tdays, legs = best["route"], best["split"], best["transfer_days"], best["legs"]
    stops = [origin, *route, origin]

    # Day -> where each slot happens.
    def leg_times(leg) -> tuple[int, int]:
        if leg["mode"] == "flight":
            dep = hhmm(leg["flight"]["DepTime"]) or 0
            arr = hhmm(leg["flight"]["ArrTime"]) or 0
            if arr < dep:
                arr += 1440
            return dep, arr
        return GROUND_DEPART, GROUND_DEPART + duration_minutes(leg["info"]["duration"])

    day_rows = []
    slot_needs = []  # (day_index, slot, city)
    for di in range(days):
        if di in tdays:
            k = tdays.index(di)
            a_city, b_city = stops[k], stops[k + 1]
            leg = legs[k]
            dep, arr = leg_times(leg)
            if leg["mode"] == "flight":
                f = leg["flight"]
                transport = (f"Flight Number: {f['Flight Number']}, from {a_city} to {b_city}, "
                             f"Departure Time: {f['DepTime']}, Arrival Time: {f['ArrTime']}")
            else:
                inf = leg["info"]
                label = "Self-driving" if leg["mode"] == "self-driving" else "Taxi"
                transport = (f"{label}, from {a_city} to {b_city}, duration: {inf['duration']}, "
                             f"distance: {inf['distance']}, cost: {inf['cost']}")
            row = {"days": di + 1, "current_city": f"from {a_city} to {b_city}",
                   "transportation": transport}
            for meal, t in MEALS.items():
                if dep >= t + 60 and a_city != origin:
                    slot_needs.append((di, meal, a_city))
                elif arr <= t - 30 and b_city != origin:
                    slot_needs.append((di, meal, b_city))
                else:
                    row[meal] = "-"
            if arr <= 16 * 60 and b_city != origin:
                slot_needs.append((di, "attraction1", b_city))
            elif dep >= 14 * 60 and a_city != origin:
                slot_needs.append((di, "attraction1", a_city))
            else:
                row["attraction"] = "-"
            stay = b_city if di < days - 1 else None
        else:
            # Find the city we're staying in.
            k = max(i for i, t in enumerate(tdays) if t < di)
            city = stops[k + 1]
            row = {"days": di + 1, "current_city": city, "transportation": "-"}
            for meal in MEALS:
                slot_needs.append((di, meal, city))
            slot_needs.append((di, "attraction1", city))
            slot_needs.append((di, "attraction2", city))
            stay = city
        if stay:
            a = best["accs"][route.index(stay)]
            row["accommodation"] = name_city(a["NAME"], stay)
        else:
            row["accommodation"] = "-"
        day_rows.append(row)

    # Restaurants: cover required cuisines first, then cheapest distinct per slot.
    meal_slots = [s for s in slot_needs if not s[1].startswith("attraction")]
    assigned: dict[tuple, dict] = {}
    uncovered = [c.lower() for c in cuisines]
    for cz in list(uncovered):
        if cz not in uncovered:
            continue
        best_pick = None
        for slot in meal_slots:
            if slot in assigned:
                continue
            for r in city_info[slot[2]]["rest"]:
                if r["Name"] in used_rest:
                    continue
                if cz in (x.lower() for x in r["cuisine_list"]):
                    covers = sum(1 for u in uncovered if u in (x.lower() for x in r["cuisine_list"]))
                    keyv = (-covers, r["Average Cost"])
                    if best_pick is None or keyv < best_pick[0]:
                        best_pick = (keyv, slot, r)
                    break
        if best_pick:
            _, slot, r = best_pick
            assigned[slot] = r
            used_rest.add(r["Name"])
            have = {x.lower() for x in r["cuisine_list"]}
            uncovered = [u for u in uncovered if u not in have]
    if uncovered:
        notes.append(f"Could not cover cuisines {uncovered} in the chosen cities.")
    for slot in meal_slots:
        if slot in assigned:
            continue
        for r in city_info[slot[2]]["rest"]:
            if r["Name"] not in used_rest:
                assigned[slot] = r
                used_rest.add(r["Name"])
                break
    att_assigned: dict[tuple, list] = {}
    for slot in [s for s in slot_needs if s[1].startswith("attraction")]:
        for a in city_info[slot[2]]["att"]:
            if a["Name"] not in used_att:
                used_att.add(a["Name"])
                att_assigned.setdefault((slot[0], slot[2]), []).append(a)
                break

    meal_cost = 0.0
    for (di, meal, city), r in assigned.items():
        day_rows[di][meal] = name_city(r["Name"], city)
        meal_cost += r["Average Cost"] * people
    for row in day_rows:
        di = row["days"] - 1
        for meal in MEALS:
            row.setdefault(meal, "-")
        if "attraction" not in row:
            picks = [name_city(a["Name"], c) for (d, c), lst in att_assigned.items() if d == di for a in lst]
            row["attraction"] = ";".join(picks) + ";" if picks else "-"
    order = ["days", "current_city", "transportation", "breakfast", "attraction", "lunch",
             "dinner", "accommodation"]
    day_rows = [{k: r[k] for k in order} for r in day_rows]

    transport_cost = sum(l["cost"] for l in legs)
    acc_cost = sum(a["_nightly"] * n for a, n in zip(best["accs"], split))
    total = round(transport_cost + acc_cost + meal_cost, 2)
    if budget and total > budget:
        notes.append(f"Draft costs {total} which exceeds the budget {budget}; "
                     "this is the cheapest feasible option found.")

    # ------------------------------------------------ candidates for edits ---
    cand_out = {}
    for c in route:
        info = city_info[c]
        n = split[route.index(c)]
        cz_l = [x.lower() for x in cuisines]
        cand_out[c] = {
            "nights": n,
            "accommodations": [{"name": a["NAME"], "room_type": a["room type"], "price": a["price"],
                                "nightly_cost_for_party": a["_nightly"],
                                "minimum_nights": a["minimum nights"],
                                "maximum_occupancy": a["maximum occupancy"],
                                "house_rules": a["house_rules"], "rating": a["review rate number"]}
                               for a in info["acc"] if a["minimum nights"] <= n][:8],
            "restaurants": [{"name": r["Name"], "cost": r["Average Cost"], "cuisines": r["Cuisines"],
                             "rating": r["Aggregate Rating"]}
                            for r in info["rest"]][:15],
            "restaurants_matching_cuisines": [
                {"name": r["Name"], "cost": r["Average Cost"], "cuisines": r["Cuisines"]}
                for r in info["rest"] if any(x.lower() in cz_l for x in r["cuisine_list"])][:10],
            "attractions": list(dict.fromkeys(a["Name"] for a in info["att"]))[:20],
        }
    alts = [{"route": list(o["route"]), "nights": list(o["split"]), "regime": o["regime"],
             "estimated_cost": round(o["est_cost"], 2)} for o in options[1:6]]

    print(json.dumps({
        "feasible": True,
        "data_dir": str(data_dir),
        "destination_kind": dest_kind,
        "trip_dates": dates,
        "candidate_cities": candidates,
        "route": {"cities": list(route), "nights": list(split), "regime": best["regime"],
                  "legs": [{"from": stops[i], "to": stops[i + 1], "date": dates[tdays[i]],
                            "mode": l["mode"], "cost": l["cost"]} for i, l in enumerate(legs)]},
        "draft_plan": day_rows,
        "plan": day_rows,
        "draft_cost": total,
        "cost_breakdown": {"transportation": round(transport_cost, 2),
                           "accommodation": round(acc_cost, 2),
                           "meals": round(meal_cost, 2), "attractions": 0},
        "alternatives": alts,
        "candidates": cand_out,
        "planner_notes": notes,
        "violations": [],
        "validation_outcome": "not-run",
        "planner_attempts": CTX["planner_attempts"],
        "planner_outcome": "feasible",
        "diagnostics": {},
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()

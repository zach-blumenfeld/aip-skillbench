"""Execution step: choose route, transport, lodging, meals and sights, then re-check the result.

stdin:  {"state": {"candidates": {...}, "tools_called": [...], "data_dir": "..."}, ...}
stdout: {"plan": {...}, "plan_status": "ok" | "needs_repair", "plan_report": {...}}

Search order: every ordered choice of `visiting_city_number` destination cities
x every allowed transport strategy, ranked by (requested cuisines reachable,
estimated cost, hours on the road). The top routes are built at three quality
tiers (comfort -> balanced -> economy) and the first one that passes every
check in plan_check.py within budget wins. If none does, the cheapest attempt
is returned with plan_status "needs_repair" and its violations.
"""

from __future__ import annotations

import itertools
import json
import sys

import plan_check
import travel_db as db

LONG_LEG_HOURS = 6.0   # a leg this long eats the travel day: fewer meals/sights that day
TOP_ROUTES = 25
TIERS = ("comfort", "balanced", "economy")


def legs_for(route, r, cand, strategy):
    """Per-leg transport for one route under one strategy, or None if a leg is impossible."""
    org, people, dates = r["org"], r["people"], r["dates"]
    stops = [org] + list(route) + [org]
    out = []
    for i, day in enumerate(cand["leg_days"]):
        o, d = stops[i], stops[i + 1]
        g = cand["ground"].get(f"{o}->{d}")
        if strategy == "self-driving":
            if not g:
                return None
            out.append({"from": o, "to": d, "day": day, "mode": "self-driving", "hours": g["hours"],
                        "cost": g["self_driving_cost"] * db.vehicles(people, "self-driving"),
                        "text": f"Self-driving: from {o} to {d}",
                        "detail": f"duration {g['duration']}, distance {g['distance']}"})
            continue
        f = None
        if strategy == "flight+taxi" and day - 1 < len(dates):
            f = cand["flights"].get(f"{o}->{d}@{dates[day - 1]}")
        if f:
            out.append({"from": o, "to": d, "day": day, "mode": "flight", "hours": 0.0,
                        "cost": f["price"] * people,
                        "text": (f"Flight Number: {f['flight_number']}, from {o} to {d}, "
                                 f"Departure Time: {f['dep_time']}, Arrival Time: {f['arr_time']}"),
                        "detail": f"elapsed {f['elapsed']}"})
        elif g:
            out.append({"from": o, "to": d, "day": day, "mode": "taxi", "hours": g["hours"],
                        "cost": g["taxi_cost"] * db.vehicles(people, "taxi"),
                        "text": f"Taxi: from {o} to {d}",
                        "detail": f"duration {g['duration']}, distance {g['distance']}"})
        else:
            return None
    return out


def schedule(route, r, cand, legs):
    """Day skeletons: which city each meal and sight slot belongs to."""
    days, org = r["days"], r["org"]
    leg_days, nights = cand["leg_days"], cand["nights"]
    arrival = {leg_days[i]: i for i in range(len(route))}
    out, city_i = [], 0
    for day in range(1, days + 1):
        s = {"day": day, "meals": {}, "attractions": [], "stay": None, "leg": None}
        if day == days:                                   # return home
            leg, here = legs[-1], route[-1]
            short = leg["hours"] < LONG_LEG_HOURS
            s.update(current=f"from {here} to {org}", leg=leg,
                     meals={"breakfast": here, "lunch": here if short else None, "dinner": None},
                     attractions=[here])
        elif day in arrival:                              # travel into route[i]
            i = arrival[day]
            city_i = i
            leg, here = legs[i], route[i]
            prev = org if i == 0 else route[i - 1]
            short = leg["hours"] < LONG_LEG_HOURS
            s.update(current=f"from {prev} to {here}", leg=leg, stay=here,
                     meals={"breakfast": None if i == 0 else prev, "lunch": here if short else None,
                            "dinner": here},
                     attractions=[here])
        else:                                             # full day in town
            here = route[city_i]
            s.update(current=here, stay=here,
                     meals={"breakfast": here, "lunch": here, "dinner": here},
                     attractions=[here, here])
        out.append(s)
    return out


def rest_key(tier):
    if tier == "economy":
        return lambda x: (x["cost"], -x["rating"])
    return lambda x: (-x["rating"], x["cost"])


def pick_acc(options, tier):
    if tier == "comfort":
        return min(options, key=lambda a: (-a["rating"], a["nightly_cost"]))
    if tier == "balanced":
        good = [a for a in options if a["rating"] >= 3] or options
        return min(good, key=lambda a: (a["nightly_cost"], -a["rating"]))
    return min(options, key=lambda a: (a["nightly_cost"], -a["rating"]))


def build(route, r, cand, legs, tier, tools):
    sk = schedule(route, r, cand, legs)
    cities = cand["cities"]

    # Lodging per city, honouring minimum nights for the nights actually spent there.
    acc = {}
    for i, c in enumerate(route):
        ok = [a for a in cities[c]["accommodations"] if a["minimum_nights"] <= cand["nights"][i]]
        if not ok:
            return None
        acc[c] = pick_acc(ok, tier)

    # Meals: first cover every requested cuisine, then fill the rest by tier preference.
    slots = [(d["day"], m, c) for d in sk for m, c in d["meals"].items() if c]
    pools = {c: sorted(cities[c]["restaurants"], key=rest_key(tier)) for c in route}
    used_names, chosen = set(), {}
    uncovered = {x.lower() for x in r["cuisine"]}
    key = rest_key(tier)
    while uncovered:
        free_slots = [s for s in slots if s not in chosen]
        best = None
        for c in {s[2] for s in free_slots}:
            for x in pools[c]:
                if x["name"] in used_names:
                    continue
                gain = len(db.cuisine_tokens(x["cuisines"]) & uncovered)
                if gain and (best is None or (-gain, key(x)) < (-best[0], key(best[1]))):
                    best = (gain, x, c)
        if not best:
            break
        _, x, c = best
        slot = next(s for s in free_slots if s[2] == c)
        chosen[slot] = x
        used_names.add(x["name"])
        uncovered -= db.cuisine_tokens(x["cuisines"])
    for s in slots:
        if s in chosen:
            continue
        x = next((x for x in pools[s[2]] if x["name"] not in used_names), None)
        if x:
            chosen[s] = x
            used_names.add(x["name"])

    seen_attr = set()
    plan = []
    for d in sk:
        meals = {}
        for m in ("breakfast", "lunch", "dinner"):
            x = chosen.get((d["day"], m, d["meals"].get(m)))
            meals[m] = f"{x['name']}, {d['meals'][m]}" if x else "-"
        names = []
        for c in d["attractions"]:
            a = next((a for a in cities[c]["attractions"] if (a["name"], c) not in seen_attr), None)
            if a:
                seen_attr.add((a["name"], c))
                names.append(f"{a['name']}, {c};")
        plan.append({
            "day": d["day"],
            "current_city": d["current"],
            "transportation": d["leg"]["text"] if d["leg"] else "-",
            "breakfast": meals["breakfast"],
            "lunch": meals["lunch"],
            "dinner": meals["dinner"],
            "attraction": "".join(names) or "-",
            "accommodation": f"{acc[d['stay']]['name']}, {d['stay']}" if d["stay"] else "-",
        })
    return {"plan": plan, "tool_called": list(tools)}


def main() -> None:
    payload = json.load(sys.stdin)
    state = payload.get("state", payload)
    cand, tools = state["candidates"], state["tools_called"]
    data_dir = state.get("data_dir") or db.DEFAULT_DATA_DIR
    r = cand["request"]
    k = r["visiting_city_number"]

    strategies = []
    if cand["modes_allowed"]["self_driving"]:
        strategies.append("self-driving")
    strategies.append("taxi")
    if cand["modes_allowed"]["flight"]:
        strategies.append("flight+taxi")

    want = {x.lower() for x in r["cuisine"]}
    ranked = []
    if k <= r["days"] - 1:
        for route in itertools.permutations(cand["cities"], k):
            served = set().union(*(db.cuisine_tokens(x["cuisines"])
                                   for c in route for x in cand["cities"][c]["restaurants"]))
            for strat in strategies:
                legs = legs_for(route, r, cand, strat)
                if not legs:
                    continue
                est, ok = sum(l["cost"] for l in legs), True
                for i, c in enumerate(route):
                    accs = [a["nightly_cost"] for a in cand["cities"][c]["accommodations"]
                            if a["minimum_nights"] <= cand["nights"][i]]
                    if not accs:
                        ok = False
                        break
                    meals = sorted(x["cost"] for x in cand["cities"][c]["restaurants"])
                    est += min(accs) * cand["nights"][i] + sum(meals[:3 * cand["nights"][i]]) * r["people"]
                if ok:
                    hours = sum(l["hours"] for l in legs)
                    ranked.append((not want <= served, est, hours, route, strat, legs))
    ranked.sort(key=lambda t: (t[0], t[1], t[2]))

    best_fail = None
    for tier in TIERS:
        for _, est, hours, route, strat, legs in ranked[:TOP_ROUTES]:
            itin = build(route, r, cand, legs, tier, tools)
            if not itin:
                continue
            chk = plan_check.check(itin, r, data_dir)
            meta = {"route": [r["org"], *route, r["org"]], "strategy": strat, "tier": tier,
                    "estimated_cost": round(est, 2),
                    "legs": [{k2: l[k2] for k2 in ("day", "from", "to", "mode", "cost", "detail")} for l in legs]}
            if not chk["violations"]:
                json.dump({"plan": itin, "plan_status": "ok",
                           "plan_report": meta | {"check": chk}}, sys.stdout, default=str)
                return
            if tier == "economy" and (best_fail is None or chk["cost"]["total"] < best_fail[2]["check"]["cost"]["total"]):
                best_fail = (itin, None, meta | {"check": chk})

    if best_fail:
        itin, _, report = best_fail
    else:
        itin = {"plan": [], "tool_called": list(tools)}
        report = {"check": {"violations": ["no feasible route: see excluded_cities and missing legs"]},
                  "excluded_cities": cand["excluded_cities"], "usable_cities": list(cand["cities"]),
                  "nights": cand["nights"]}
    json.dump({"plan": itin, "plan_status": "needs_repair", "plan_report": report}, sys.stdout, default=str)


if __name__ == "__main__":
    main()

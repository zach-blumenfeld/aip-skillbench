# Review and finalize the travel plan

Request:

{request}

The planner searched the sandbox (feasible: {feasible}) and drafted the cheapest plan that meets the parsed constraints.

- Route: {route}
- Draft cost: {draft_cost} (breakdown {cost_breakdown}); budget: {budget}
- Planner notes: {planner_notes}
- Validation so far: {validation_outcome}; violations to fix: {violations}

Current plan (the planner's draft on the first pass; your last revision after a failed validation), one object per day:

{plan}

Swap candidates per city (already filtered by room type, house rule, and minimum nights): {candidates}

Cheaper or different routes: {alternatives}

Post only `plan` (every other key the next step lists is already in the state): the list of day objects, keys in this order: `days`, `current_city`, `transportation`, `breakfast`, `attraction`, `lunch`, `dinner`, `accommodation`. Start from the current plan; keep it unless something must change. If the planner found no feasible trip (empty plan), build one by hand with the lookup CLI below. Change it when:

1. Violations are listed above: fix each one (swap a restaurant, attraction, accommodation, flight, or the route) and post the corrected plan.
2. The request asks for something the parsed constraints did not capture (a specific city, a must-see place, a meal preference, an arrival time): honour it using sandbox entries only.
3. The draft is over budget: try an alternative route, cheaper accommodation, or fewer meals on travel days before giving up.

Rules every plan must keep (the validator enforces them):

- Every name must come from the sandbox exactly as written, formatted "Name, City"; attractions are "Name, City;Name, City;". Use "-" for an empty slot. Look up anything not in the candidates with `python scripts/travel_db.py restaurants|attractions|accommodations --city X`, `flights --origin A --destination B --date YYYY-MM-DD`, or `distance --origin A --destination B --mode self-driving|taxi` (add `--data-dir {data_dir}`).
- Travel days have `current_city` "from A to B" and a transportation entry; other days have the single city name and "-" transportation.
- Transportation strings: "Flight Number: F0123456, from A to B, Departure Time: HH:MM, Arrival Time: HH:MM" (flight on that day's date) or "Self-driving, from A to B, duration: ..., distance: ... km, cost: N" / "Taxi, from A to B, ...". Never mix flights and self-driving in one trip.
- Non-travel days need breakfast, lunch, dinner and at least one attraction. Meals and attractions sit in the current city (either city on a travel day). No restaurant or attraction twice in the trip.
- Accommodation every night except the last day ("-"); stay at one place per city at least its minimum nights.
- Required cuisines must each appear among restaurants at the destination cities (not the origin).
- Start from and return to the origin; visit exactly the requested number of cities, all inside the destination state; no city twice.
- Cost = flights price × people + self-driving cost × ceil(people/5) + taxi cost × ceil(people/4) + restaurant Average Cost × people + accommodation price × ceil(people / maximum occupancy) per night. Must not exceed the budget.

Load `references/planning-rules.md` when a violation or rule is unclear.

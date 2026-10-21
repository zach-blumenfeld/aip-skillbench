The generated itinerary did not pass every check. Repair it and answer with `repaired_plan`.

Checker report (route, transport legs, cost breakdown, violations):

{plan_report}

The draft itinerary:

{plan}

Normalised request and the database candidates (usable cities with their filtered lodging, restaurants and attractions, ground legs, flights):

{candidates}

How to repair:

1. Read the violations. Typical causes and fixes, in this order of preference:
   - Over budget: swap to cheaper lodging (compare `nightly_cost`, which already multiplies price by the rooms the party needs), cheaper restaurants (`cost` is per person), or a cheaper route/strategy from the candidates. Replace a meal with "-" only as a last resort; never drop a meal that is the only one serving a requested cuisine.
   - Cuisine not covered: put a restaurant whose `cuisines` contains it into a free meal slot in a destination city (the origin city does not count).
   - Minimum nights: pick lodging whose `minimum_nights` does not exceed the nights spent in that city.
   - No feasible route: pick other cities from `cities`, or another transport mode that is allowed.
2. Use only entities present in the candidates, or look more up with the database CLI (run from the skill's `scripts/` folder):
   `python travel_db.py restaurants|accommodations|attractions --city <City> --data-dir {data_dir}`,
   `python travel_db.py distance --origin <A> --destination <B> --data-dir {data_dir}`,
   `python travel_db.py flights --origin <A> --destination <B> --date YYYY-MM-DD --data-dir {data_dir}`.
   Add the matching skill name (`search_restaurants`, `search_accommodations`, `search_attractions`, `search_driving_distance`, `search_flights`, `search_cities`) to `tool_called` for any search you run.
3. Keep every format rule from `references/itinerary-rules.md`: one object per day, `"Name, City"` entities, attractions `"Name, City;"`-terminated, travel days `"from A to B"`, last day returns to the origin with accommodation "-", no repeated restaurants or attractions, one ground mode only (self-driving never mixed with taxi or flights).
4. If no plan can satisfy the budget, return the cheapest valid plan you can build; the next step still writes it and records the remaining violations.

`repaired_plan` must be the full itinerary object: `{{"plan": [...], "tool_called": [...]}}`.

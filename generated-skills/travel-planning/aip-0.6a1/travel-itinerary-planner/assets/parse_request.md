Turn the traveller's request into the structured `request` object the planner scripts read.

Request text:

{query}

Answer with `request` as a JSON object with exactly these fields.

Example, for "Plan a 5-day trip for a family of four from Seattle to two cities in Texas, March 10-14, 2022, budget $8,000. We smoke, want Mexican food, and won't drive ourselves.":

```json
{{
  "org": "Seattle",
  "dest": "Texas",
  "days": 5,
  "visiting_city_number": 2,
  "date": ["2022-03-10", "2022-03-11", "2022-03-12", "2022-03-13", "2022-03-14"],
  "people_number": 4,
  "budget": 8000,
  "local_constraint": {{
    "house rule": "smoking",
    "cuisine": ["Mexican"],
    "room type": null,
    "transportation": "no self-driving"
  }}
}}
```

Rules:

- `org`: the departure city, spelled as in the database (city names only, no state).
- `dest`: a US state name when the trip covers several cities "in <state>", otherwise the single destination city.
- `days`: trip length in days, counting the departure day and the return day. `date`: every calendar day of the trip as `YYYY-MM-DD`, one per day (empty list only if the request gives no dates).
- `visiting_city_number`: how many destination cities the request names ("three cities in Ohio" -> 3). If unstated: 3 days -> 1, 5 days -> 2, 7 days -> 3.
- `people_number`: travellers ("for two" -> 2; "solo"/unstated -> 1). `budget`: the total budget in dollars as a number.
- `local_constraint` uses only this vocabulary; use null (or [] for cuisine) when the request says nothing:
  - `house rule`: what the lodging must allow. One of `pets` (travelling with pets / pet-friendly), `smoking`, `parties`, `children under 10`, `visitors`.
  - `room type`: `entire room` (entire home/apartment), `private room`, `shared room`, or `not shared room` (anything but a shared room).
  - `cuisine`: list of cuisines the meals should include, capitalised as written ("American", "Mediterranean", "Chinese", "Italian", "Indian", "Mexican", "French", "Thai", "Japanese", ...).
  - `transportation`: `no flight` ("prefer not to fly", "no flights") or `no self-driving`.
- Do not add fields; do not guess cities, restaurants, or prices: those come from the database in the next step.

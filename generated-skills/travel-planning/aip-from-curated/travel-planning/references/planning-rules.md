# Travel planning rules and sandbox data

Load when a validation violation is unclear, when building or repairing a plan by hand,
or when the planner reports the trip infeasible.

## Sandbox datasets

The data folder (in the container usually `/app/data`; the scripts also try
`/root/data`, `/root`, `$TRAVEL_DATA_DIR`) holds:

| File | Format | Columns used | Lookup |
|---|---|---|---|
| `background/citySet_with_states.txt` | `City<TAB>State` per line | city, state | state → its cities, case-insensitive; unknown state → "Invalid state." |
| `background/citySet.txt`, `stateSet.txt` | one name per line | — | reference lists only |
| `flights/clean_Flights_2022.csv` | CSV, 2022-01-01 … 2022-07-31 | Flight Number, Price, DepTime, ArrTime, ActualElapsedTime, FlightDate, OriginCityName, DestCityName, Distance | exact, case-sensitive origin + destination + `YYYY-MM-DD` date |
| `googleDistanceMatrix/distance.csv` | CSV, `cost` column always empty | origin, destination, duration, distance ("1,144 km") | exact origin + destination |
| `accommodations/clean_accommodations_2022.csv` | CSV, unnamed index column first | NAME, price, room type, house_rules, minimum nights, maximum occupancy, review rate number, city | city, case-insensitive |
| `restaurants/clean_restaurant_2022.csv` | CSV, unnamed index column first | Name, Average Cost, Cuisines (comma list), Aggregate Rating, City | city, case-insensitive |
| `attractions/attractions.csv` | CSV | Name, Latitude, Longitude, Address, Phone, Website, City | city, case-insensitive |

Quirks that change answers:

- Rows with an empty value in any used column are dropped (pandas `dropna`). About 700
  accommodations have empty `house_rules` and do **not** exist in the sandbox.
- City/state text after the first "(" is ignored ("Austin(Texas)" → "Austin").
- A driving duration containing "day" (e.g. "1 day 3 hours") means **no valid route**
  for self-driving or taxi.
- Driving cost per vehicle: self-driving `int(km × 0.05)`, taxi `int(km)`.
- Some cities in the state list have no attractions, restaurants, or flights; the
  planner skips cities lacking matching accommodations or restaurants.
- Names can contain commas, odd spacing, emoji, or non-Latin characters. Copy them
  exactly. "Name, City" is split on the **last** comma.
- Restaurant names repeat across cities (chains); never use the same name twice in a trip.
- Flight `ArrTime` may be earlier than `DepTime` (overnight) or "24:00".

Ad-hoc lookup CLI (JSON output; `--data-dir DIR` if auto-discovery fails):

```bash
python scripts/travel_db.py datadir
python scripts/travel_db.py cities --state California
python scripts/travel_db.py flights --origin "New York" --destination Denver --date 2022-03-16
python scripts/travel_db.py distance --origin Seattle --destination Portland --mode self-driving
python scripts/travel_db.py accommodations --city Seattle
python scripts/travel_db.py restaurants --city "San Francisco"
python scripts/travel_db.py attractions --city "New York"
```

## Plan format

One object per day, in order; `-` marks an empty slot.

```json
[
  {"days": 1, "current_city": "from Sarasota to Chicago",
   "transportation": "Flight Number: F3573659, from Sarasota to Chicago, Departure Time: 11:56, Arrival Time: 14:13",
   "breakfast": "-", "attraction": "Millennium Park, Chicago;The Art Institute of Chicago, Chicago;",
   "lunch": "-", "dinner": "Some Restaurant, Chicago", "accommodation": "Cozy Loft, Chicago"},
  {"days": 2, "current_city": "Chicago", "transportation": "-",
   "breakfast": "A, Chicago", "attraction": "Navy Pier, Chicago;", "lunch": "B, Chicago",
   "dinner": "C, Chicago", "accommodation": "Cozy Loft, Chicago"},
  {"days": 3, "current_city": "from Chicago to Sarasota",
   "transportation": "Self-driving, from Chicago to Sarasota, duration: 17 hours 2 mins, distance: 1,860 km, cost: 93",
   "breakfast": "D, Chicago", "attraction": "-", "lunch": "-", "dinner": "-", "accommodation": "-"}
]
```

(Day 3 above mixes a flight trip with self-driving only to show the string format; a real plan may not.)

## Constraints

Commonsense (always):

1. Every entity exists in the sandbox; flights match the leg and that day's date.
2. Travel days carry transportation; non-travel days carry 3 meals and ≥1 attraction;
   accommodation every day except the last.
3. Meals, attractions, accommodation are in the current city (either end of a travel day;
   the night's accommodation is in the arrival city).
4. Route: starts at the origin, ends at the origin, no city revisited, exactly
   `visiting_city_number` destination cities, all within the destination state.
5. No restaurant repeated; no attraction repeated.
6. Flights and self-driving never in the same trip (taxi mixes with either).
7. Consecutive nights at one accommodation ≥ its `minimum nights`.

Hard (from the request):

| Constraint | Values | Rule |
|---|---|---|
| house_rule | smoking, parties, children under 10, visitors, pets | lodging `house_rules` must not contain "No <value>" |
| room_type | entire room / private room / shared room / not shared room | `Entire home/apt` / `Private room` / `Shared room` / anything but `Shared room` |
| cuisine | list | each listed cuisine appears in some chosen restaurant's Cuisines in a destination city (origin meals don't count) |
| transportation | no flight / no self-driving | that mode appears nowhere in the plan |
| budget | dollars | total cost ≤ budget |

Total cost (attractions are free):

- flight: `Price × people`
- self-driving: `cost × ceil(people / 5)` (one car per 5)
- taxi: `cost × ceil(people / 4)` (one cab per 4)
- each meal: `Average Cost × people`
- each night: `price × ceil(people / maximum occupancy)`

## Planner behaviour (scripts/plan_trip.py)

Tries every ordered choice of destination cities, every split of the nights (each city
≥1 night), and both transport regimes; per leg it takes the cheapest flight (that date)
or self-driving, or a taxi. Ranking: cover all cuisines, then enough attractions, then
within budget, then the most even split of nights, then lowest estimated cost. Meals are
placed by timing (breakfast 08:00, lunch 12:30, dinner 19:00; ground legs leave 09:00):
eaten in the departure city if the leg leaves ≥1 h after the meal, in the arrival city if
it lands ≥30 min before, else "-"; nothing is eaten at the origin.

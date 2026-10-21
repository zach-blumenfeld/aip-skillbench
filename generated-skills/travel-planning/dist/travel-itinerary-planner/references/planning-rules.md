# Planning rules, cost model, and data facts

Load this when you hand-edit a plan, when `validate` reports an error you need
to understand, or when `draft` returns `infeasible`. `scripts/travel.py
validate` enforces every rule below.

## Database (under the data dir, usually `/app/data`)

| File | Key columns | Search tool name |
|---|---|---|
| `background/citySet_with_states.txt` | `city<TAB>state` per line | `search_cities` |
| `accommodations/clean_accommodations_2022.csv` | NAME, room type, price, minimum nights, review rate number, house_rules, maximum occupancy, city | `search_accommodations` |
| `attractions/attractions.csv` | Name, Latitude, Longitude, Address, Phone, Website, City | `search_attractions` |
| `restaurants/clean_restaurant_2022.csv` | Name, City, Cuisines (comma list), Average Cost, Aggregate Rating | `search_restaurants` |
| `googleDistanceMatrix/distance.csv` | origin, destination, duration, distance ("1,057 km") | `search_driving_distance` |
| `flights/clean_Flights_2022.csv` (~30 MB, 2022-01..07) | Flight Number, Price, DepTime, ArrTime, ActualElapsedTime, FlightDate, OriginCityName, DestCityName, Distance | `search_flights` |

- A row that is blank in any searched column cannot be returned by the original
  search tool, so it does not exist for planning. This includes lodging whose
  `house_rules` is blank, and attractions missing a phone or website.
- City matching is exact after trimming. Search lookups ignore case, but the
  distance and flight lookups do not. Text in parentheses, such as
  `"Akron(Ohio)"`, is stripped before lookups.
- Lodging names are often unrelated to the city (an "Upper Manhattan" room
  listed in Toledo). Trust the `city` column, not the name.
- Cuisine labels: American, BBQ, Bakery, Cafe, Chinese, Desserts, Fast Food,
  French, Indian, Italian, Mediterranean, Mexican, Pizza, Seafood, Tea.

## Constraint vocabulary (`local_constraint` in constraints.json)

- `house rule`: one or more of `pets`, `smoking`, `parties`, `children under 10`,
  `visitors`. A listing violates the rule if its `house_rules` contains
  `No pets` / `No smoking` / `No parties` / `No children under 10` / `No visitors`.
- `room type`: `entire room` → `Entire home/apt`; `private room` → `Private room`;
  `shared room` → `Shared room`; `not shared room` → anything but `Shared room`.
- `cuisine`: every listed cuisine must appear in at least one chosen restaurant
  outside the origin city.
- `transportation`: `no flight` or `no self-driving`.

## Itinerary shape

- `days` days, `visiting_city_number` cities. When the destination is a state
  and the count isn't stated, use 3 days → 1 city, 5 → 2, 7 → 3. The cities must
  be distinct, all in that state, and must not include the origin.
- Nights are `days - 1`, split evenly across the cities, with earlier cities
  taking any extra night. Day 1 travels origin → city 1. The first day in each
  later city travels from the previous city. The last day travels back to the
  origin. Travel days use `current_city` = `"from A to B"`. Other days use the
  city name.
- Each travel-day `transportation` names that leg: `Self-driving: from A to B,
  duration: …, distance: …, cost: N`, `Taxi: from A to B, …`, or `Flight Number:
  F123, from A to B, Departure Time: hh:mm, Arrival Time: hh:mm`. Non-travel days use `"-"`.
- Meals, attractions, and lodging must be in that day's city. On a travel day,
  either endpoint counts. Lodging must be in the city where you sleep, which is
  B on a travel day. The final day has no lodging (`"-"`).
- Write entries as `"Name, City"`, using the exact database name. Write
  attractions as `"Name, City;Name, City;"`, always ending with `;`. Use `"-"`
  for a skipped slot. Don't leave a day mostly empty.
- No restaurant may appear twice in the trip, and no attraction may either.
- Consecutive nights in the same listing must be at least that listing's
  `minimum nights`. Choose a listing per city using the nights you actually
  stay there.

## Transportation rules

- `self-driving` may not be combined with `flight` or `taxi` anywhere in the trip
  (the car would be stranded). `flight` + `taxi` is fine.
- A leg is invalid if the distance matrix has no row for it, or if its duration
  contains "day".
- A flight must exist for that origin, destination, and `FlightDate` (the
  trip's start date plus day − 1).

## Cost model (budget compares against the sum)

| Item | Cost |
|---|---|
| Self-driving leg | `int(km × 0.05)` × ceil(people / 5) cars |
| Taxi leg | `int(km)` × ceil(people / 4) taxis |
| Flight leg | Price × people |
| Meal | Average Cost × people |
| Lodging night | price × ceil(people / maximum occupancy) rooms |

## When `draft` says infeasible

- The `cities_without_valid_lodging` list names cities where no listing fits
  the house rule, room type, and minimum nights. Those cities can't be used.
  If too few cities remain, the request can't be met in full.
- A cuisine failure means the cheapest 50 routes can't cover the cuisines with
  distinct restaurants. Re-run with `--max-routes 500`.
- Never drop a stated hard constraint to make a plan fit. Instead, build the
  closest plan by hand with the search commands, validate it, and report which
  constraint is unmet.

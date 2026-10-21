# Itinerary rules: database, format, and checks

Load this when repairing a plan by hand or when a check in `write_report` needs interpreting.

## The database (container: `/app/data`)

| Skill name (for `tool_called`) | File | Match rule | Columns kept (rows with a blank in any are dropped) |
|---|---|---|---|
| `search_cities` | `background/citySet_with_states.txt` (tab-separated `city<TAB>state`) | state, case-insensitive; unknown -> "Invalid state." | city, state |
| `search_accommodations` | `accommodations/clean_accommodations_2022.csv` | `city`, case-insensitive | NAME, price, room type, house_rules, minimum nights, maximum occupancy, review rate number, city |
| `search_restaurants` | `restaurants/clean_restaurant_2022.csv` | `City`, case-insensitive (text after "(" ignored) | Name, Average Cost, Cuisines, Aggregate Rating, City |
| `search_attractions` | `attractions/attractions.csv` | `City`, case-insensitive | Name, Latitude, Longitude, Address, Phone, Website, City |
| `search_driving_distance` | `googleDistanceMatrix/distance.csv` | exact `origin`/`destination` (text after "(" ignored) | origin, destination, duration, distance |
| `search_flights` | `flights/clean_Flights_2022.csv` (30 MB) | exact `OriginCityName`, `DestCityName`, `FlightDate` (`YYYY-MM-DD`) | Flight Number, Price, DepTime, ArrTime, ActualElapsedTime, FlightDate, OriginCityName, DestCityName, Distance |

Gotchas:
- Lodging with a blank `house_rules` cell is dropped by the search tool even though it has no rules; it is not in the sandbox, so never book it.
- `house_rules` is an `&`-joined list of prohibitions ("No pets & No visitors"). Pet-friendly means the text has no "No pets"; same pattern for smoking, parties, visitors, children under 10.
- Room types are `Entire home/apt`, `Private room`, `Shared room`.
- A distance row whose duration mentions "day" is "no valid information": that leg cannot be driven.
- Listing names often contain commas; the city is always the text after the last ", ".
- `distance.csv` has duplicate rows; the first match wins.

## Costs (what the budget is checked against)

- Self-driving leg: `int(km * 0.05)` per car, one car per 5 people (`ceil(people/5)`).
- Taxi leg: `int(km)` per cab, one cab per 4 people.
- Flight: ticket `Price` x people.
- Meal: `Average Cost` x people.
- Night: `price` x `ceil(people / maximum occupancy)` rooms.
- Total = all legs + all meals + all nights; must be <= budget.

## Output format (`itinerary.json`)

```json
{
  "plan": [
    {"day": 1, "current_city": "from <Origin> to <CityA>", "transportation": "Self-driving: from <Origin> to <CityA>",
     "breakfast": "-", "lunch": "-", "dinner": "<Restaurant>, <CityA>",
     "attraction": "<Attraction>, <CityA>;", "accommodation": "<Listing NAME>, <CityA>"},
    {"day": 2, "current_city": "<CityA>", "transportation": "-",
     "breakfast": "<Restaurant>, <CityA>", "lunch": "<Restaurant>, <CityA>", "dinner": "<Restaurant>, <CityA>",
     "attraction": "<Attraction>, <CityA>;<Attraction>, <CityA>;", "accommodation": "<Listing NAME>, <CityA>"},
    {"day": 7, "current_city": "from <CityC> to <Origin>", "transportation": "Self-driving: from <CityC> to <Origin>",
     "breakfast": "<Restaurant>, <CityC>", "lunch": "-", "dinner": "-",
     "attraction": "<Attraction>, <CityC>;", "accommodation": "-"}
  ],
  "tool_called": ["search_cities", "search_accommodations", "search_restaurants", "search_attractions", "search_driving_distance"]
}
```

- Exactly one object per trip day, `day` = 1..N, every key present, every value a string except `day`.
- `current_city`: the city name on a stay day; `"from A to B"` on every travel day (day 1 leaves the origin, the last day returns to it).
- `transportation`: `"Self-driving: from A to B"`, `"Taxi: from A to B"`, or `"Flight Number: F123, from A to B, Departure Time: hh:mm, Arrival Time: hh:mm"`; `"-"` on stay days.
- Meals and accommodation: `"Name, City"` with the exact database name; `"-"` when skipped. Attractions: `"Name, City;"` per item, concatenated, ending in `;`.
- Every meal, attraction, and accommodation city must be one of the day's `current_city` cities.
- Last day accommodation is `"-"`; every other night has lodging.

## Checks (`plan_check.py`)

1. Every restaurant, attraction, lodging, flight, and driving leg exists in the database.
2. No restaurant or attraction repeats.
3. Route: starts and ends at the origin, visits exactly `visiting_city_number` cities, all in the requested state.
4. Transport: self-driving is never mixed with taxi or flights; `no flight` / `no self-driving` honoured.
5. Lodging: house rule and room type satisfied; consecutive nights at one listing >= its `minimum nights`.
6. Every requested cuisine appears in at least one meal in a destination city (the origin does not count; a cuisine matches a comma-separated token of `Cuisines`).
7. Total cost <= budget.

## Day shape the planner uses

Nights are split as evenly as possible across the cities (7 days / 3 cities -> 2+2+2). A leg of 6 h or more eats the travel day: on the outbound day only dinner and one sight at the destination; on the return day only breakfast and one sight before leaving. Shorter legs: transfer days get breakfast in the departure city, lunch and dinner in the arrival city, one sight; full stay days get three meals and two sights.

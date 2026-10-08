# Parse the travel request

Request:

{request}

Turn it into the structured query the planner script needs. Post these keys:

- `origin` (string): departure city, exactly as a city name (strip any "(State)" suffix).
- `destination` (string): the destination state (e.g. "Texas") when the request names a state, otherwise the destination city.
- `start_date` (string): first travel day as YYYY-MM-DD. The datasets cover 2022-01-01 to 2022-07-31; a request without a year means 2022.
- `days` (integer): trip length in days, counting both travel days ("March 16th to March 18th" = 3).
- `visiting_city_number` (integer): how many destination cities to visit. If the request does not say: 1 for a single city or a 3-day trip; for a state, 2 cities on a 5-day trip and 3 on a 7-day trip.
- `people_number` (integer): travellers in the party (a "solo" trip or unspecified = 1; "me and my partner" = 2).
- `budget` (float): total budget in dollars for the whole party; 0 if none is given.
- `local_constraint` (object) with exactly these keys, each null when unstated:
  - `house_rule`: one of "smoking", "parties", "children under 10", "visitors", "pets" — the activity the party needs the lodging to ALLOW.
  - `room_type`: one of "entire room", "private room", "shared room", "not shared room".
  - `cuisine`: list of cuisines the party wants to try at the destination, from: American, BBQ, Bakery, Cafe, Chinese, Desserts, Fast Food, French, Indian, Italian, Mediterranean, Mexican, Pizza, Seafood, Tea.
  - `transportation`: "no flight" or "no self-driving".
- `data_dir` (string): the folder holding `background/`, `flights/`, `googleDistanceMatrix/`, `accommodations/`, `restaurants/`, `attractions/` when you know it (from the task or your environment); otherwise "" (the scripts search $TRAVEL_DATA_DIR, /app/data, /root/data, /root and nearby).

If the request already is a TravelPlanner-style JSON query, map `org`→origin, `dest`→destination, `date[0]`→start_date, `len(date)` or `days`→days, and copy `visiting_city_number`, `people_number`, `budget`, `local_constraint` (keys "house rule"/"room type" become house_rule/room_type).

Map wording to constraint values, e.g. "we're bringing our dog" → house_rule "pets"; "we'll throw a party" → "parties"; "travelling with a 5-year-old" → "children under 10"; "need the whole place" → room_type "entire room"; "not a shared room / need privacy / at least a private room" → "not shared room"; "a private room" (exactly) → "private room"; "I don't want to fly" → transportation "no flight"; "no driving" → "no self-driving". Only set a constraint the request actually implies.

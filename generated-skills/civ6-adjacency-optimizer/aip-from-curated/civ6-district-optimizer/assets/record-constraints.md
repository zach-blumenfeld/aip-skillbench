Copy the task's explicit constraints into the state so the optimizer obeys them.

Task instructions:

{task_instructions}

Map summary (start positions, existing cities):

{map_summary}

Your earlier answers: center_mode = {center_mode}, district_pool = {district_pool}.

Produce the optimize step's inputs (scenario_path, district_pool, center_mode, all already in
the state) plus whichever of these the task states explicitly:

- fixed_city_centers: list of [x, y], one per city, when the task gives the city center
  coordinates. Set center_mode to "given" with it. Coordinates are column x, row y, with plot
  ID = y * width + x; convert plot IDs if the task gives those.
- allowed_districts: list of district names (CAMPUS, HOLY_SITE, THEATER_SQUARE,
  COMMERCIAL_HUB, HARBOR, INDUSTRIAL_ZONE, GOVERNMENT_PLAZA, ENTERTAINMENT_COMPLEX,
  WATER_PARK, DIPLOMATIC_QUARTER, ENCAMPMENT, AERODROME, PRESERVE, AQUEDUCT, DAM, CANAL,
  NEIGHBORHOOD, SPACEPORT) when the task restricts which districts may be placed (for an
  exclusion list, list every other name). It overrides district_pool.
- time_limit_s: a number of seconds, only if the task sets a time budget (default 240).

Copy values exactly as the task states them; do not invent constraints the task does not state.

---
name: travel-itinerary-planner
description: Build a multi-day, multi-city travel itinerary (TravelPlanner-style) from the bundled travel database (cities by state, accommodations, restaurants, attractions, driving distances, flights) under a budget and local constraints such as pet-friendly or other house rules, room type, required cuisines, and no-flight / no-self-driving. Searches the database, picks a feasible route, lodging, meals and sights, re-checks costs and rules, and writes itinerary.json with plan and tool_called. Use for "plan a N-day trip from X covering K cities in <state>" tasks.
metadata:
  aip-version: "0.6a1"
  version: "1.0"
---

# AIP runtime — format 0.6a1

You are executing an Agent Instruction Protocol (AIP) procedure: the fenced YAML block in this skill's `SKILL.md`. AIP is a protocol for cheaply, quickly, and accurately executing multi-step tasks as a graph of typed steps. You drive the run and execute every step yourself, following the semantics below.

Critical terminology:

- **Client**: you, the agent running this procedure; the `client_task` step kind is named for it. You supply each step's input, run its script, answer its questions by your own judgment, perform its task, follow its router, and make the final call at every step.
- **State**: the one JSON object a run carries. Each step declares the keys it reads as `inputs`; `execution` and `client_task` steps declare the keys they add as `outputs`, and a `decision` adds one key per question.
- **Step kinds**: `execution` runs a script, `decision` asks typed questions about the state, `client_task` hands work to you, `router` branches on a value in the state, `end` declares the procedure's result.

## Execution

The state starts as the start step's `inputs` and flows along `inputs_to`; each step adds its outputs to it. Every key is produced by exactly one step, so keys accumulate and nothing is overwritten. A step runs only if the state holds every key it declares in `inputs`, with the declared types; check that before each step. A step sees only those keys: give it its declared `inputs` and nothing else from the state. You have the final say at every step.

- **`execution`**: before the first one, check that this machine has everything `requires` names (the interpreter at its minimum version, the packages, the tools); if anything is missing, stop and name all of it. Run `script` from its folder, launched with the step's `command` when it has one and `python <script>` otherwise, with one JSON object on stdin, `{"state": <the step's inputs>, "assets": {<file stem>: <content>}, "expects": <the next step's inputs>}`. The script writes one JSON object to stdout holding exactly the step's `outputs`; add them to the state. A non-zero exit, or output missing a declared key, fails the step: stop there and report it rather than doing the step by hand.
- **`decision`**: answer each question from the step's inputs, and from the run so far only when the step sets `history: true`. Each answer collapses to one value under its question name and is added to the state: a noul to `true`/`false`, a choice to its label, a score to its level number. `thresholds` name the questions where an uncertain answer matters most; when your answer to one is a close call, reconsider it before continuing.
- **`client_task`**: render `template` with `{key}` from the step's inputs, `{assets[stem]}` for its assets, and `{meta.name}` for the skill name. Perform the task, loading `references` if their descriptions apply, and produce the step's `outputs`; add them to the state.
- **`router`**: read the state's `branch_on` key and continue at `branches[value]`. A value with no branch is an error.
- **`end`**: the state must hold `end`'s `inputs`. Those keys are the procedure's result.

```yaml
purpose: >
  Plan a round trip from an origin city through one or more destination cities using only
  the travel sandbox database, and write it as itinerary.json ({plan: [one object per day],
  tool_called: [...]}). Folds the six search skills (search-cities, search-accommodations,
  search-restaurants, search-attractions, search-driving-distance, search-flights) into one
  pipeline: the request is structured once, every search runs in a script, a planner script
  enumerates routes x transport strategies and fills days at three quality tiers, and a
  checker re-verifies every entity, rule and the budget before the file is written. Only a
  plan that still fails its checks comes back to the agent for repair.

trigger_when:
  - A task asks for an N-day travel itinerary from an origin city to a state or city, with a budget, using the bundled travel database.
  - The request carries constraints like pet-friendly lodging, a room type, required cuisines, or no flights / no self-driving.
  - Output must be a JSON plan with per-day current_city, transportation, breakfast, lunch, dinner, attraction, accommodation and a tool_called list.

do_not_use_when:
  - The trip must be planned from live web data or real booking APIs instead of the bundled CSV database.
  - Only a single lookup is needed (one flight or one restaurant list); run scripts/travel_db.py directly instead.

requires:
  interpreter:
    name: python
    version: "3.10"
  packages:
    - pandas

steps:
  - name: parse-request
    kind: client_task
    description: Turn the natural-language trip request into the structured request object (origin, destination, days, dates, people, budget, local constraints).
    inputs:
      - name: query
        type: string
        description: The traveller's request, verbatim (the quoted requirement in the task statement).
      - name: data_dir
        type: string
        description: Root of the travel database; /app/data in the task container.
      - name: output_path
        type: string
        description: Where the itinerary JSON must be written, e.g. /app/output/itinerary.json.
    template: assets/parse_request.md
    outputs:
      - name: request
        type: object
        description: "org, dest, days, visiting_city_number, date[], people_number, budget, local_constraint{house rule, cuisine[], room type, transportation}."
    inputs_to: search-candidates

  - name: search-candidates
    kind: execution
    description: Expand the destination state into cities, search lodging (filtered by house rule and room type), restaurants, attractions, driving legs and, when flights are allowed, the cheapest flight per leg date; record which search skills ran.
    inputs:
      - name: request
        type: object
      - name: data_dir
        type: string
    script: scripts/search_candidates.py
    timeout: 300
    outputs:
      - name: candidates
        type: object
        description: Normalised request, nights per city, leg days, usable cities with filtered options, excluded cities with reasons, ground legs, flights.
      - name: tools_called
        type: list[*]
        description: Search skill names actually used (search_cities, search_accommodations, ...), for the itinerary's tool_called.
    inputs_to: build-plan

  - name: build-plan
    kind: execution
    description: Rank every route x allowed transport strategy, fill each day (lodging meeting minimum nights, cuisine-covering unique restaurants, unique sights) at comfort, balanced, then economy tier, and keep the first plan that passes every check within budget.
    inputs:
      - name: candidates
        type: object
      - name: tools_called
        type: list[*]
      - name: data_dir
        type: string
    script: scripts/build_plan.py
    timeout: 300
    outputs:
      - name: plan
        type: object
        description: The itinerary, {plan, tool_called}; the cheapest attempt when nothing passes.
      - name: plan_status
        type: string
        description: ok when the plan passes every check within budget, needs_repair otherwise.
      - name: plan_report
        type: object
        description: Route, strategy, tier, per-leg transport detail and the checker result (cost breakdown, violations, cuisines covered).
    inputs_to: route-plan

  - name: route-plan
    kind: router
    description: A clean plan is written as is; a plan with violations goes to the agent for repair first.
    branch_on: plan_status
    branches:
      ok: write-itinerary
      needs_repair: repair-itinerary

  - name: write-itinerary
    kind: execution
    description: Normalise the itinerary to the exact output shape, re-check it against the database, and write it to output_path.
    inputs:
      - name: plan
        type: object
      - name: candidates
        type: object
      - name: data_dir
        type: string
      - name: output_path
        type: string
    script: scripts/write_itinerary.py
    timeout: 120
    outputs:
      - name: write_report
        type: object
        description: Path written, day count, remaining violations (expected empty), cost breakdown, route, cuisines covered.
    inputs_to: end

  - name: repair-itinerary
    kind: client_task
    description: Fix the violations in the drafted itinerary (budget, cuisine coverage, minimum nights, missing route) using only database entities.
    inputs:
      - name: plan
        type: object
      - name: plan_report
        type: object
      - name: candidates
        type: object
      - name: data_dir
        type: string
    template: assets/repair_plan.md
    references:
      - path: references/itinerary-rules.md
        description: Database files and match rules, cost formulas, the exact output format, and every check the writer runs. Load before editing the plan by hand.
    outputs:
      - name: repaired_plan
        type: object
        description: The full repaired itinerary, {plan, tool_called}, in the same format.
    inputs_to: write-repaired

  - name: write-repaired
    kind: execution
    description: Normalise and re-check the repaired itinerary, then write it to output_path, reporting any violations that remain.
    inputs:
      - name: repaired_plan
        type: object
      - name: candidates
        type: object
      - name: data_dir
        type: string
      - name: output_path
        type: string
    script: scripts/write_itinerary.py
    timeout: 120
    outputs:
      - name: repaired_write_report
        type: object
        description: Path written, day count, remaining violations, cost breakdown, route, cuisines covered.
    inputs_to: end

  - name: end
    kind: end
    description: The itinerary JSON is written at output_path; the write report on the branch taken says what it costs and whether anything is still violated.
    inputs:
      - name: output_path
        type: string
      - name: request
        type: object

anti_patterns:
  - Using restaurants, hotels, attractions or prices from memory; every entity must come from the database (the writer rejects anything it cannot find).
  - Booking lodging whose house_rules cell is blank; the search tool drops those rows, so they are outside the sandbox.
  - Mixing self-driving with taxi or flights in one trip, or using a flight when the request says no flights.
  - Repeating a restaurant or an attraction anywhere in the trip.
  - Counting the origin city's meals toward a requested cuisine; only destination-city meals count.
  - Booking a listing for fewer consecutive nights than its minimum nights.
  - Forgetting that meals cost Average Cost x people and lodging costs price x ceil(people / maximum occupancy) per night.
  - Writing the city twice or omitting it; entities are "Name, City" and attractions end with ";".
  - Listing a search skill in tool_called that was never run, or omitting one that was.
```

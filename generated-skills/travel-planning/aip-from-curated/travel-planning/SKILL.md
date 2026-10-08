---
name: travel-planning
description: Plan a multi-day trip (TravelPlanner-style) from the bundled 2022 sandbox datasets — flights, self-driving/taxi distances, accommodations, restaurants, attractions, and state→city lists. Parses the request (origin, destination city or state, dates, party size, budget, house rule, room type, cuisine, transportation limits), searches routes and costs with scripts, drafts a day-by-day itinerary, validates it against every commonsense and hard constraint, and delivers it. Use for travel itinerary, trip plan, flight/hotel/restaurant/attraction lookup, or budget travel questions over these datasets.
metadata:
  aip-version: "0.5a1"
---

# AIP runtime — format 0.5a1

You are executing an Agent Instruction Protocol (AIP) procedure: the fenced YAML block in this skill's `SKILL.md`. AIP is a protocol for cheaply, quickly, and accurately executing multi-step tasks as a graph of typed steps. You drive the run and execute every step yourself, following the semantics below.

Critical terminology:

- **Client**: you, the agent running this procedure; the `client_task` step kind is named for it. You supply each step's input, run its script, answer its questions by your own judgment, perform its task, follow its router, and make the final call at every step.
- **State**: the JSON object a step receives. Each step declares its required keys as `inputs`; extra keys pass through.
- **Step kinds**: `execution` runs a script, `decision` asks typed questions about the state, `client_task` hands work to you, `router` branches on a value in the state, `end` declares the final state's shape.

## Execution

The state is one JSON object. It starts as the start step's `inputs` and flows along `inputs_to`; each step's output is merged over it, so keys accumulate and extra keys pass through untouched. A step runs only if the state holds every key it declares in `inputs`, with the declared types; check that before each step. You may change the state before any step runs; you have the final say at every step.

- **`execution`**: run `script` with one JSON object on stdin, `{"currentState": <state>, "assets": {<file stem>: <content>}, "expects": <the next step's inputs>}`. The script writes one JSON object to stdout; merge it over the state.
- **`decision`**: answer each question against the state. Each answer collapses to one value under its question name and is merged over the state: a noul to `true`/`false`, a choice to its label, a score to its level number. `thresholds` name the questions where an uncertain answer matters most; when your answer to one is a close call, reconsider it before continuing.
- **`client_task`**: render `template` with `{key}` from the state, `{assets[stem]}` for its assets, and `{meta.name}` for the skill name. Perform the task, loading `references` if their descriptions apply, and produce the next step's `inputs`; merge them over the state.
- **`router`**: read the state's `branch_on` key and continue at `branches[value]`. A value with no branch is an error.
- **`end`**: the state must hold `end`'s `inputs`. That state is the procedure's result.

```yaml
purpose: >
  Turn a natural-language travel request into a complete, budget-checked, day-by-day
  itinerary built only from the sandbox datasets (the six curated search-* tools merged).
  A script enumerates destination-city routes, night splits, and transport regimes and
  drafts the cheapest plan that meets the constraints; the agent adjusts it to the request;
  a validator re-checks every entity, route, timing, constraint, and the total cost before
  the plan is delivered in the format the task asks for.

trigger_when:
  - A task asks for a travel plan or itinerary between US cities or to a US state for given dates, party size, and budget.
  - A TravelPlanner-style query (org, dest, days, visiting_city_number, date, people_number, local_constraint, budget) must be answered.
  - A task needs flights, driving/taxi distance and cost, accommodations, restaurants, attractions, or the cities of a state from the bundled travel datasets.

do_not_use_when:
  - The trip needs live prices, real-time availability, or dates outside 2022-01 to 2022-07 that the sandbox does not cover.
  - The request is general travel advice with no itinerary or dataset lookup.

steps:
  - name: parse-request
    kind: client_task
    description: Extract the structured trip query (origin, destination, dates, party, budget, constraints, data folder) from the request.
    inputs:
      - name: request
        type: string
        description: The traveller's request or the task's query, verbatim (text or a JSON query).
    template: assets/parse_request.md
    inputs_to: plan-trip

  - name: plan-trip
    kind: execution
    description: Load the sandbox, search every route/night-split/transport option, and draft the cheapest valid day-by-day plan plus swap candidates.
    inputs:
      - name: origin
        type: string
      - name: destination
        type: string
        description: A state (visit its cities) or a single city.
      - name: start_date
        type: string
        description: YYYY-MM-DD.
      - name: days
        type: integer
      - name: visiting_city_number
        type: integer
      - name: people_number
        type: integer
      - name: budget
        type: float
        description: Total dollars for the party; 0 means no budget.
      - name: local_constraint
        type: object
        description: house_rule, room_type, cuisine (list), transportation; null when unstated.
      - name: data_dir
        type: string
        description: Data folder, or "" to auto-discover.
    script: scripts/plan_trip.py
    timeout: 300
    inputs_to: check-feasibility

  - name: check-feasibility
    kind: router
    description: A drafted trip goes to review; an infeasible search goes back once to re-read the request, then on to review to build the closest plan by hand.
    branch_on: planner_outcome
    branches:
      feasible: review-plan
      infeasible: revise-query
      infeasible-final: review-plan

  - name: revise-query
    kind: client_task
    description: Diagnose why no trip was feasible and re-post a corrected (or unchanged) query.
    inputs:
      - name: request
        type: string
      - name: planner_notes
        type: list[*]
      - name: diagnostics
        type: object
        description: Per destination city counts of matching lodging, restaurants, attractions, and transport availability.
    template: assets/revise_query.md
    references:
      - path: references/planning-rules.md
        description: Dataset files, quirks, lookup CLI, and constraint semantics; load to confirm why a city or leg is missing.
    inputs_to: plan-trip

  - name: review-plan
    kind: client_task
    description: Accept or adjust the draft so it honours the whole request, fixing any validator violations.
    inputs:
      - name: request
        type: string
      - name: feasible
        type: boolean
      - name: plan
        type: list[*]
        description: The planner's draft, or the last revision that failed validation.
      - name: draft_cost
        type: float
      - name: route
        type: object
      - name: candidates
        type: object
      - name: alternatives
        type: list[*]
      - name: planner_notes
        type: list[*]
      - name: violations
        type: list[*]
      - name: trip_dates
        type: list[*]
    template: assets/review_plan.md
    references:
      - path: references/planning-rules.md
        description: Dataset files, columns and quirks, the lookup CLI, the exact plan/transport string formats, every commonsense and hard constraint, and the cost formulas. Load when a violation or rule is unclear, or when building a plan by hand because the planner found none.
    inputs_to: validate-plan

  - name: validate-plan
    kind: execution
    description: Re-check the plan against the sandbox and every constraint, compute its total cost, and count attempts.
    inputs:
      - name: plan
        type: list[*]
        description: Day objects with days, current_city, transportation, breakfast, attraction, lunch, dinner, accommodation.
      - name: origin
        type: string
      - name: destination
        type: string
      - name: trip_dates
        type: list[*]
      - name: people_number
        type: integer
      - name: budget
        type: float
      - name: visiting_city_number
        type: integer
      - name: local_constraint
        type: object
      - name: data_dir
        type: string
    script: scripts/validate_plan.py
    timeout: 300
    inputs_to: check-validation

  - name: check-validation
    kind: router
    description: A clean plan, or one still failing after three validations, is delivered; otherwise go back and fix the violations.
    branch_on: validation_outcome
    branches:
      pass: deliver
      give-up: deliver
      fail: review-plan

  - name: deliver
    kind: client_task
    description: Write the final plan in the format and location the task requires and summarize it.
    inputs:
      - name: request
        type: string
      - name: plan
        type: list[*]
      - name: total_cost
        type: float
      - name: plan_valid
        type: boolean
      - name: violations
        type: list[*]
    template: assets/deliver.md
    inputs_to: end

  - name: end
    kind: end
    description: The validated itinerary, its cost, and a delivery summary.
    inputs:
      - name: plan
        type: list[*]
      - name: total_cost
        type: float
      - name: plan_valid
        type: boolean
      - name: final_answer
        type: string

anti_patterns:
  - Inventing or "tidying" a restaurant, hotel, attraction, or flight name; every entry must match the sandbox exactly or the plan fails.
  - Using an accommodation whose house_rules are empty in the CSV; such rows are dropped from the sandbox.
  - Treating a driving duration containing "day" as a usable self-driving or taxi route.
  - Mixing flights and self-driving in one trip, or using a flight from a different date than the travel day.
  - Repeating a restaurant or attraction anywhere in the trip, including chain names in different cities.
  - Pricing the party as one person; flights and meals scale by people, cars by ceil(people/5), taxis by ceil(people/4), rooms by ceil(people/maximum occupancy).
  - Booking fewer consecutive nights than an accommodation's minimum nights.
  - Counting meals in the origin city toward a cuisine requirement.
  - Reporting success when validation gave up; state which constraints the plan misses.
```

---
name: civ6-district-optimizer
description: Optimize Civilization VI (Gathering Storm) city center and district placement for maximum adjacency bonus from a scenario.json and a .Civ6Map SQLite map. Parses the map (odd-r hex grid, terrain, features, resources, rivers), enforces civ6lib placement rules, population district limits and uniqueness, and runs an exact branch-and-bound search scored by civ6lib's adjacency engine (Campus, Holy Site, Theater Square, Commercial Hub, Harbor, Industrial Zone, Government Plaza). Use for Civ6 district planning, adjacency calculation, or placement validation.
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
  Solve Civilization VI (Gathering Storm) district-placement problems: given a scenario
  (population, number of cities, map file) and a .Civ6Map SQLite map, choose the City Center
  location(s) and the specialty/infrastructure districts that maximize total adjacency bonus
  while obeying every placement, district-limit and uniqueness rule. Scripts parse the map
  (terrain, hills, mountains, features, resources, improvements, river edges on an odd-r hex
  grid), run an exact branch-and-bound search scored by the civ6lib rule engine verbatim, and
  re-validate the written answer, so totals match civ6lib to the point.

trigger_when:
  - A task asks for optimal Civ6 city center and district placements, maximum adjacency bonus, or a district plan for a scenario.json plus a .Civ6Map file.
  - A task asks to validate Civ6 district placements or compute Campus, Holy Site, Theater Square, Commercial Hub, Harbor or Industrial Zone adjacency on a map.
  - Spatial placement optimization on a Civ6 hex map with population-based district limits.

do_not_use_when:
  - The question is about Civ6 strategy in general (tech order, diplomacy, combat) with no map placement to compute.
  - The game is another Civilization title (Civ5, Civ7 rules differ) or the map is not a Civ6 SQLite map.

steps:
  - name: inspect-map
    kind: execution
    description: >
      Load scenario.json and its .Civ6Map (explore the schema first, LEFT-join plot tables,
      x = ID % width, y = ID // width) and report dimensions, terrain/feature/resource counts,
      river tiles, start positions, existing cities/districts, population, num_cities,
      max_specialty_districts = 1 + floor((pop-1)/3), and loader warnings. Run once per
      scenario; pass absolute paths (scripts run with cwd = scripts/). map_path in the state
      overrides the scenario's map_file.
    inputs:
      - name: scenario_path
        type: string
        description: Absolute path to the scenario.json (or its folder).
      - name: task_instructions
        type: string
        description: The task's instructions verbatim, including any output path and format.
    script: scripts/inspect_map.py
    timeout: 120
    inputs_to: read-task

  - name: read-task
    kind: decision
    description: Settle which districts may be used, how city centers are chosen, and whether the task states explicit constraints.
    inputs:
      - name: task_instructions
        type: string
      - name: map_summary
        type: object
        description: From inspect-map; start_positions and existing_cities matter for center_mode.
    questions:
      district_pool:
        type: choice
        instructions: >
          Which districts may the solution place? Non-specialty districts (Aqueduct, Dam, Canal,
          Neighborhood, Spaceport) do not count toward the population limit, and Aqueduct, Dam
          and Canal each give an Industrial Zone +2, so the pool changes the optimum. Pick the
          pool the task's wording supports. If the task lists allowed districts, pick the
          smallest pool containing them (the explicit list is recorded separately).
        criteria:
          specialty_only: The task restricts placements to specialty districts (those limited by population), or talks only about filling district slots with adjacency districts and excludes infrastructure.
          with_infrastructure: The task does not restrict district types, or allows non-specialty / infrastructure districts. Default when the task is silent; these are the districts civ6lib's Industrial Zone rule rewards.
          all: The task explicitly allows any district type including Neighborhoods and Spaceports, or asks for the absolute maximum with every district civ6lib knows.
      center_mode:
        type: choice
        instructions: How are city center locations determined?
        criteria:
          free: The solver must choose where to found the city (default when the task does not fix the location).
          start_position: The task says to settle at the player's start position on the map (players in order, player 0 first; use given for another player's start).
          existing_city: The map already contains the city (map_summary.existing_cities) and the task says to plan around it.
          given: The task states explicit city center coordinates or plot IDs.
      has_explicit_constraints:
        type: noul
        instructions: >
          Does the task state concrete values that must be copied into the state: city center
          coordinates/plot IDs, an explicit list of allowed or excluded district types not
          exactly matched by one district_pool, or a time budget?
        criteria:
          true: Specific coordinates, plot IDs, a named list of permitted districts, or a time limit appear in the task.
          false: The task only describes the goal and output format.
    thresholds:
      district_pool: 0.6
      center_mode: 0.6
      has_explicit_constraints: 0.2
    inputs_to: by-constraints

  - name: by-constraints
    kind: router
    description: Explicit coordinates, district lists or time budgets are recorded before optimizing.
    branch_on: has_explicit_constraints
    branches:
      "true": record-constraints
      "false": optimize

  - name: record-constraints
    kind: client_task
    description: Copy the task's explicit centers, allowed districts or time budget into the state.
    inputs:
      - name: task_instructions
        type: string
      - name: map_summary
        type: object
      - name: center_mode
        type: string
      - name: district_pool
        type: string
    template: assets/record-constraints.md
    references:
      - path: references/map-format.md
        description: Coordinate system and plot-ID conversion; load if the task gives plot IDs or coordinates in another form.
    inputs_to: optimize

  - name: optimize
    kind: execution
    description: >
      For every valid city center (land, not mountain/natural wonder/ice, min city distance
      4 same landmass / 3 otherwise; start position tried first) prune tiles with civ6lib
      PlacementRules, then branch-and-bound over district types (greedy seed, optimistic
      bounds) for the maximum total adjacency within the specialty limit, one district per
      type; fill spare specialty slots without lowering the total; re-score with
      AdjacencyCalculator after destruction and validate count, uniqueness and placement.
      Optional state keys: fixed_city_centers, allowed_districts, time_limit_s (default 240).
    inputs:
      - name: scenario_path
        type: string
      - name: district_pool
        type: string
        description: specialty_only | with_infrastructure | all.
      - name: center_mode
        type: string
        description: free | start_position | existing_city | given.
    script: scripts/optimize.py
    timeout: 900
    inputs_to: write-answer

  - name: write-answer
    kind: client_task
    description: Write the solution to the output path in the exact format the task requires.
    inputs:
      - name: task_instructions
        type: string
      - name: solution
        type: object
        description: city_center, placements, total_adjacency, per-city and per-district breakdown, validation_errors, search stats.
      - name: solution_valid
        type: boolean
    template: assets/write-answer.md
    references:
      - path: references/civ6-district-rules.md
        description: Full placement, limit, uniqueness, adjacency and destruction tables civ6lib enforces; load to explain the result or hand-check a placement.
      - path: references/optimization-strategy.md
        description: How the search works; load if solution.search.exact is false or the task adds constraints the optimizer does not model.
    inputs_to: verify-answer

  - name: verify-answer
    kind: execution
    description: >
      Re-read the written answer, re-validate every placement, the specialty count and
      uniqueness with civ6lib, recompute the total, and flag a claimed total that differs or
      a total below the optimizer's.
    inputs:
      - name: answer_path
        type: string
        description: Absolute path of the file write-answer produced.
      - name: scenario_path
        type: string
      - name: solution
        type: object
    script: scripts/verify_answer.py
    timeout: 120
    inputs_to: answer-check

  - name: answer-check
    kind: router
    description: A failed check goes back to rewrite the answer; a passing one ends.
    branch_on: answer_ok
    branches:
      "true": end
      "false": write-answer

  - name: end
    kind: end
    description: The optimal placement plan, the answer file written in the task's format, and its civ6lib check.
    inputs:
      - name: solution
        type: object
      - name: total_adjacency
        type: integer
      - name: answer_path
        type: string
      - name: answer_check
        type: object

anti_patterns:
  - Hand-placing districts or computing adjacency by eye instead of running optimize; the per-type flooring, destruction and Government Plaza rules make mental totals wrong.
  - Summing all +0.5 sources before flooring (1 Mine + 1 Lumber Mill + 1 District is 0, not 1).
  - Forgetting that placing a district destroys Woods, Rainforest, Marsh, bonus resources and improvements, changing other districts' adjacency; the City Center destroys nothing.
  - Placing a district on a Geothermal Fissure, mountain, natural wonder, strategic or luxury resource, or more than 3 tiles from its City Center.
  - Exceeding 1 + floor((population-1)/3) specialty districts, or counting Aqueduct, Dam, Canal, Neighborhood or Spaceport against that limit.
  - Brute-forcing every combination of tiles; it explodes combinatorially. Prune, score, then search from the anchor (City Center).
  - Reusing one scenario's answer for another; run the procedure once per scenario.json, since population changes the district limit.
  - Passing relative paths to the scripts; they run with cwd set to scripts/.
  - Editing coordinates or the total when transcribing the solution; copy them exactly.
```

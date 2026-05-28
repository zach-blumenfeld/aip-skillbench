---
name: flight-plan-parser
description: Use this skill when converting natural language flight commands into waypoints and timing for a drone simulator. Covers parsing commands like "Take off to X m height in Y seconds", "Hover at X m height for Y seconds", "Fly from (x,y,z) to (x',y',z') in T seconds", and "Land from X m height in Y seconds" into structured (4×n) waypoint arrays and segment mode lists.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a2/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Convert natural-language drone flight commands into the structured triple
  (waypoints, waypoint_times, modes) consumed by the simulator's trajectory
  planner. waypoints is a (4, n) numpy array of [x, y, z, yaw] columns;
  waypoint_times is a (n,) array of arrival times in seconds; modes is a
  list of (n-1) per-segment mode strings drawn from {takeoff, hover, fly,
  land}. The skill ships a working parser module so the agent can integrate
  it directly rather than re-deriving the regexes and the stateful
  ensure-start behaviour.

trigger_when:
  - Solving the drone-planning-control task and the project needs a
    flight_plan_parser module importable as `from flight_plan_parser import parse_flight_plan`.
  - Converting one or more lines of human-readable flight commands into
    waypoints, arrival times, and segment modes for a trajectory planner.
  - Wiring a simulator's `main.py` that calls `parse_flight_plan(text)` and
    expects a (4, n) waypoint array plus (n,) times plus (n-1) modes.
  - Validating that a flight-command text file matches the supported grammar
    before downstream planning.

do_not_use_when:
  - The trajectory planner, PID controllers, motor model, or step-response
    metrics need to be built — those are separate skills.
  - The command grammar must be extended with new shapes (e.g., curved
    paths, yaw control). Edit `scripts/flight_plan_parser.py` and the
    grammar reference rather than trying to bend prose around it.

scope_and_approval: >
  Read-only against the project's command files. Writes one Python module
  to the project root (typically `/root/flight_plan_parser.py`) when the
  install step runs. No external network calls, no destructive operations.

steps:
  - name: install-module
    description: >
      Copy `scripts/flight_plan_parser.py` to the project root (default
      `/root/flight_plan_parser.py`) so downstream code can
      `from flight_plan_parser import parse_flight_plan`. Overwrite any
      existing stub at that path — the bundled module is the reference
      implementation.
    outputs:
      - name: module-path
        type: string
        description: Filesystem path where the parser was installed.

  - name: parse-commands
    description: >
      For each command (or command file), call
      `parse_flight_plan(text)` from the installed module. The function
      accepts a single multi-line string or an iterable of command strings
      and returns `(waypoints, waypoint_times, modes)`. The grammar is
      documented in `references/command-grammar.md`; load that reference if
      a command appears not to match or if extending the grammar.
    script: scripts/flight_plan_parser.py
    depends_on:
      - install-module
    inputs:
      - name: command-text
        type: string
        description: Raw command text — one command per line, blank lines tolerated.
    outputs:
      - name: waypoints
        type: object
        description: numpy.ndarray of shape (4, n), rows [x, y, z, yaw].
      - name: waypoint_times
        type: object
        description: numpy.ndarray of shape (n,), arrival times in seconds.
      - name: modes
        type: list[string]
        description: List of length (n-1), each entry one of {takeoff, hover, fly, land}.

  - name: verify-shapes
    description: >
      Sanity-check the output before passing it downstream. Assert
      `waypoints.shape == (4, n)` for some `n >= 2`,
      `waypoint_times.shape == (n,)`, `len(modes) == n - 1`, that
      `waypoint_times` is strictly non-decreasing and starts at 0.0, and
      that every mode is in `{takeoff, hover, fly, land}`. A failed
      assertion means the input grammar drifted from what the parser
      accepts — re-read `references/command-grammar.md` before tweaking the
      regexes.
    depends_on:
      - parse-commands
    inputs:
      - name: waypoints
        type: object
      - name: waypoint_times
        type: object
      - name: modes
        type: list[string]

scenarios:
  - need: Parse a single takeoff command.
    action: >
      `parse_flight_plan("Take off to 1 m height in 3 seconds")`.
    outcome: >
      waypoints (4, 2): [[0,0],[0,0],[0,1],[0,0]];
      waypoint_times: [0, 3]; modes: ['takeoff'].
  - need: Parse a leading hover (start altitude must match hover height).
    action: >
      `parse_flight_plan("Hover at 3 m height for 12 seconds")`.
    outcome: >
      waypoints (4, 2): [[0,0],[0,0],[3,3],[0,0]];
      waypoint_times: [0, 12]; modes: ['hover']. The start waypoint's z is
      3, not 0 — hover snaps altitude before the implicit start insert.
  - need: Parse a fly segment starting away from the origin.
    action: >
      `parse_flight_plan("Fly from (0,0,1) to (-1,0,1) in 4 seconds")`.
    outcome: >
      waypoints (4, 2): [[0,-1],[0,0],[1,1],[0,0]];
      waypoint_times: [0, 4]; modes: ['fly']. The default (0,0,0) origin
      is replaced by the `from (...)` triple.
  - need: Parse a multi-command plan (takeoff → hover → land).
    context: >
      Multi-line input — `parse_flight_plan` splits on newlines and skips
      blank lines automatically.
    action: |
      parse_flight_plan(
          "Take off to 2 m height in 3 seconds\n"
          "Hover at 2 m height for 5 seconds\n"
          "Land from 2 m height in 4 seconds\n"
      )
    outcome: >
      waypoints (4, 4) with end-of-segment column [0,2,2,0] → [0,0,0,0];
      waypoint_times: [0, 3, 8, 12]; modes:
      ['takeoff','hover','land'].

anti_patterns:
  - Re-implementing the regex patterns inline in `main.py` or another
    module instead of importing `parse_flight_plan` — the bundled script is
    the source of truth and already handles the `location` variant of
    `Fly from (...) to (...)` plus the case-insensitive matching.
  - Treating the auto-inserted start waypoint as always `(0, 0, 0)`. Only
    `takeoff` behaves that way; `hover` and `land` snap altitude first, and
    `fly` seeds the start from its `from (...)` triple.
  - Assuming yaw is a degree of freedom. The grammar does not address yaw;
    the parser fills it with 0.0. Do not invent yaw values.
  - Letting the trailing column of `waypoints` drift from the final
    segment's terminal position. `land` ends at z=0 — downstream code that
    uses `waypoints[0:3, -1]` as the steady-state target depends on this.
  - Forgetting that `modes` has length `n - 1`, not `n`. There is one mode
    per *segment*, not per waypoint.
```

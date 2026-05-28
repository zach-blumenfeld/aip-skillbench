---
name: flight-plan-parser
description: Use this skill when converting natural language flight commands into waypoints and timing for a drone simulator. Covers parsing commands like "Take off to X m height in Y seconds", "Hover at X m height for Y seconds", "Fly from (x,y,z) to (x',y',z') in T seconds", and "Land from X m height in Y seconds" into structured (4×n) waypoint arrays and segment mode lists.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.2/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Convert human-readable flight commands into structured waypoints
  compatible with the drone simulator's trajectory planner. Each
  command maps to one flight segment tagged with a mode
  (`takeoff`, `hover`, `fly`, `land`). The output contract is:
  `waypoints` — a (4 × n) numpy array whose rows are
  [x, y, z, yaw]; `waypoint_times` — a (n,) numpy array giving
  the arrival time in seconds for each waypoint; and `modes` —
  a list of (n-1) strings, one mode per segment between
  consecutive waypoints.

trigger_when:
  - User provides natural-language flight commands that must drive a drone simulator.
  - Building or extending a pipeline that feeds waypoints into the simulator's trajectory planner.
  - Commands match the supported patterns ("Take off to ... m height in ... seconds", "Hover at ...", "Fly from (...) to (...) in ... seconds", "Land from ...").
  - Output must be a (4×n) waypoint array plus a per-segment mode list.

do_not_use_when:
  - The input is already a structured waypoint array — no parsing is needed.
  - The command vocabulary falls outside the four supported patterns and would require new grammar work.

steps:
  - name: init-parser
    description: >
      Instantiate a stateful parser that holds current position
      [x, y, z, yaw], current time, and three accumulators:
      `waypoints` (list of 4-vectors), `waypoint_times` (list of
      floats), and `modes` (list of mode strings).
  - name: auto-insert-start
    description: >
      On the first command, if the waypoint list is empty, push a
      starting waypoint at the current position with t=0. This
      guarantees N waypoints and N-1 modes after processing.
  - name: parse-line
    description: >
      For each command line, run case-insensitive regex matchers
      (one per command type) to extract numeric fields. Takeoff,
      Hover, and Land patterns capture height and duration
      (2 groups). Fly captures start (x, y, z), end (x', y', z'),
      and duration (7 groups), tolerating optional whitespace
      around commas inside the parenthesised tuples. Dispatch to
      the matching handler.
  - name: apply-handler
    description: >
      The matched handler advances the time accumulator by the
      command's duration, updates the current position to the
      command's end state, appends a copy of that position to the
      waypoints list, appends the new arrival time, and appends
      the mode string ('takeoff', 'hover', 'fly', or 'land').
      Always copy the position list when pushing to avoid mutating
      shared state.
  - name: finalize-arrays
    description: >
      After all commands are processed, convert the waypoints list
      into a (4 × n) numpy array whose rows are x, y, z, yaw, and
      convert the times list into a (n,) numpy array. Leave
      `modes` as a Python list of length n-1.
  - name: expose-entrypoint
    description: >
      Expose a top-level `parse_flight_plan(text)` function that
      instantiates the parser, feeds it each non-empty line of
      `text`, and returns the tuple
      `(waypoints, waypoint_times, modes)`.

decisions:
  - signal: First command arrives and the waypoint list is empty.
    action: Auto-insert a starting waypoint at (0, 0, 0, yaw=0) with t=0 before applying the command's handler.
  - signal: A handler is about to append the current position to the waypoints list.
    action: Push a copy of the position vector — never the live reference — so later updates do not retroactively mutate stored waypoints.
  - signal: A command handler finishes.
    action: Ensure exactly one waypoint (the end state) and one mode string are appended, preserving the N-waypoints / N-1-modes invariant.
  - signal: A line does not match any of the four supported patterns.
    action: Surface a parse error rather than silently skipping — silent skips desync the modes list from the waypoints list.

search_shortcuts:
  - category: commands
    body: |
      Supported command patterns and the mode each emits:
        - `Take off to <h> m height in <t> seconds`           → mode `'takeoff'`
        - `Hover at <h> m height for <t> seconds`             → mode `'hover'`
        - `Fly from (<x>,<y>,<z>) to (<x'>,<y'>,<z'>) in <t> seconds` → mode `'fly'`
        - `Land from <h> m height in <t> seconds`             → mode `'land'`
  - category: regex
    body: |
      Regex strategy — one case-insensitive pattern per command:
        - Takeoff / Hover / Land: 2 capture groups (height, duration).
        - Fly: 7 capture groups (x, y, z, x', y', z', duration);
          allow optional whitespace around commas inside the
          parenthesised tuples.
        - Compile every pattern with `re.IGNORECASE` so
          capitalisation does not matter.

scenarios:
  - need: Parse a single takeoff command into the simulator's waypoint format.
    action: |
      Call `parse_flight_plan("Take off to 1 m height in 3 seconds")`.
      The parser auto-inserts a start waypoint at (0, 0, 0, 0) with
      t=0, then the takeoff handler appends an end waypoint at
      (0, 0, 1, 0) with t=3 and mode 'takeoff'.
    outcome: |
      Returns
        waypoints       = [[0, 0], [0, 0], [0, 1], [0, 0]]   # shape (4, 2)
        waypoint_times  = [0, 3]
        modes           = ['takeoff']

anti_patterns:
  - Pushing the live position list (instead of a copy) into the waypoints accumulator — later updates retroactively corrupt earlier waypoints.
  - Skipping the auto-inserted starting waypoint, which breaks the N-waypoints / N-1-modes invariant the trajectory planner relies on.
  - Writing case-sensitive regex patterns and then rejecting user input that capitalises "Take Off" or "Hover".
  - Appending more than one waypoint or more than one mode per command — segment counts must stay aligned.
```

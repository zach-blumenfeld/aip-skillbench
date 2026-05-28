---
name: stepinfo-3d
description: Use this skill when computing 3D step-response performance metrics for point-to-point drone flight — rise time, settling time, percent overshoot, and steady-state error based on the Euclidean distance to the final target. Use instead of running 1D stepinfo per axis for any flight where all three position axes move simultaneously (diagonal flight, fly-from-A-to-B commands). The same metrics also apply unchanged to single-axis takeoff/hover/land commands because the 3D Euclidean distance collapses to the 1D z error there.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a2/assets/aip-schemas/procedure.schema.json
compatibility: Requires Python 3 with numpy. No filesystem or network access; pure function over arrays already in memory. The optional CLI accepts saved `.npy` arrays.
---

```yaml
purpose: >
  Compute four scalar step-response metrics — RiseTime, SettlingTime,
  Overshoot_pct, SteadyStateError — from a quadrotor's actual position
  trajectory against a fixed target. All four metrics are derived from a
  single distance signal `dist[k] = || pos_actual[:, k] - pos_target ||_2`
  so they remain coherent when the drone moves diagonally and the three
  position axes are coupled. The output is the exact 4-key payload the
  `drone-planning-control` task verifier expects inside `metrics_3d.json`
  (the orchestrator adds the `"mode"` key from the command's command-type
  label before writing the file).

trigger_when:
  - The simulator has produced an actual (15, n) state matrix and a final desired position, and the caller needs scalar tracking metrics.
  - A command file mixes axes (`Fly from (x,y,z) to (x',y',z')`) — per-axis 1D `stepinfo` would misrepresent the convergence and must not be used.
  - A single-axis command (takeoff, hover, land on z) needs the same 4-key metrics output — the 3D distance collapses to the 1D z-error so this skill still applies.
  - Writing `/root/results/<label>/metrics_3d.json` and the schema demands the four float fields `RiseTime`, `SettlingTime`, `Overshoot_pct`, `SteadyStateError`.

do_not_use_when:
  - The drone is tracking a circular, figure-eight, or otherwise non-point-to-point trajectory — there is no single fixed "final target", so rise / settling / overshoot are not well-defined. Use RMS error or cumulative absolute error instead.
  - Generating the planned trajectory itself (use `position-controller-trajectory-planner`).
  - Producing the diagnostic plot figures (use `plot-quadrotor`).
  - Tuning PID gains directly — these metrics inform the cost function but the tuning loop itself lives in the orchestrator.

scope_and_approval: >
  Pure computation over arrays already in memory. No filesystem writes,
  no network, no user-visible side effects. Safe to call without
  prompting; safe to call many times inside a PID tuning loop.

steps:
  - name: compute-distance-signal
    description: >
      Build the 1D distance signal `dist[k] = || pos_actual[:, k] -
      pos_target ||_2` from the (3, n) actual position rows and the
      (3,) target. This single signal is what makes the metrics
      coherent for diagonal flight — every later step reads from
      `dist`, not from the raw three axes.
    script: scripts/stepinfo_3d.py
    inputs:
      - name: pos_actual
        type: object
        description: Actual position trajectory, shape (3, n). Typically `actual_state_matrix[0:3, :]`.
      - name: pos_target
        type: object
        description: Target position, shape (3,). Typically `waypoints[0:3, -1]` (the last waypoint).
      - name: t
        type: object
        description: Time vector, shape (n,), seconds.
    outputs:
      - name: dist
        type: object
        description: 1D Euclidean distance signal, shape (n,), metres.
      - name: d0
        type: float
        description: Initial distance `dist[0]`. Drives every threshold below.

  - name: short-circuit-already-at-target
    description: >
      If `d0 < 1e-6` the drone is already at the target (most commonly
      a hover-in-place command). Return `{RiseTime: 0.0, SettlingTime:
      0.0, Overshoot_pct: 0.0, SteadyStateError: float(dist[-1])}` and
      stop — there is no step to characterise. Skipping this guard
      causes a divide-by-zero in the overshoot percentage.
    script: scripts/stepinfo_3d.py
    depends_on: [compute-distance-signal]
    inputs:
      - name: d0
        type: float
    outputs:
      - name: short_circuit_metrics
        type: object
        nullable: true
        description: The four-key zero-distance result, or null if `d0 >= 1e-6` and the main path continues.

  - name: rise-time
    description: >
      Scan `dist` forward and record the first `t[k]` where `dist[k]
      <= 0.10 * d0` (drone has covered 90 percent of the initial gap).
      If the band is never reached, RiseTime is NaN. The 10 percent
      rise fraction is fixed — it is not the same as the settling
      threshold and is not configurable.
    script: scripts/stepinfo_3d.py
    depends_on: [compute-distance-signal]
    inputs:
      - name: dist
        type: object
      - name: d0
        type: float
      - name: t
        type: object
    outputs:
      - name: RiseTime
        type: float
        nullable: true

  - name: settling-time
    description: >
      Scan `dist` backward and record the last `t[k]` where `dist[k]
      > settling_threshold * d0`. The default settling threshold is
      0.02 (2 percent), matching the task verifier's
      `settling_threshold=0.02`. Backward scan is intentional — the
      drone may dip into the band and bounce out again, and SettlingTime
      is the last time it was outside.
    script: scripts/stepinfo_3d.py
    depends_on: [compute-distance-signal]
    inputs:
      - name: dist
        type: object
      - name: d0
        type: float
      - name: t
        type: object
      - name: settling_threshold
        type: float
        nullable: true
        description: Default 0.02. Override only if the task explicitly asks for a different band.
    outputs:
      - name: SettlingTime
        type: float
        nullable: true

  - name: overshoot
    description: >
      Walk `dist` forward and flip an `in_band` flag the first time
      `dist[k] <= settling_threshold * d0`. From that index onward,
      track the maximum distance seen. Overshoot_pct is
      `max_post_entry / d0 * 100`. If the band is never entered, return
      0.0 — the drone approached without oscillating past the target.
      Overshoot is defined by distance from the target, NOT by
      crossing the target on any single axis.
    script: scripts/stepinfo_3d.py
    depends_on: [compute-distance-signal]
    inputs:
      - name: dist
        type: object
      - name: d0
        type: float
      - name: settling_threshold
        type: float
        nullable: true
    outputs:
      - name: Overshoot_pct
        type: float

  - name: steady-state-error
    description: >
      `SteadyStateError = float(dist[-1])` — the final Euclidean
      distance from the target in metres. The task verifier requires
      this to be below 0.05 m for the command to count as
      successfully executed.
    script: scripts/stepinfo_3d.py
    depends_on: [compute-distance-signal]
    inputs:
      - name: dist
        type: object
    outputs:
      - name: SteadyStateError
        type: float

  - name: assemble-result
    description: >
      Return a flat dict with exactly the four keys `RiseTime`,
      `SettlingTime`, `Overshoot_pct`, `SteadyStateError`. Do not add
      `mode`, `command_id`, or any other field — the caller is
      responsible for stitching the command's mode label into the
      final `metrics_3d.json` payload. Casting to plain `float` keeps
      the JSON serialiser happy (numpy scalars are not JSON-native).
    script: scripts/stepinfo_3d.py
    depends_on: [rise-time, settling-time, overshoot, steady-state-error]
    inputs:
      - name: RiseTime
        type: float
      - name: SettlingTime
        type: float
      - name: Overshoot_pct
        type: float
      - name: SteadyStateError
        type: float
    outputs:
      - name: metrics
        type: object
        description: "{'RiseTime', 'SettlingTime', 'Overshoot_pct', 'SteadyStateError'} ready for JSON dump."

modes:
  - name: in-process
    body: >
      Import the function directly from the script:
      `from stepinfo_3d import stepinfo_3d`. Call it once per command
      inside the simulator main loop right after the per-command
      trajectory arrays are built:
      `metrics = stepinfo_3d(actual[0:3, :], waypoints[0:3, -1], time_vec)`.
      The default `settling_threshold=0.02` matches the task verifier
      and should not be changed unless an instruction explicitly says
      otherwise.
  - name: post-hoc
    body: >
      Reload `actual_trajectory.npy` for a previously saved command,
      rebuild `time_vec` via `np.arange(n) / sample_rate` (with
      `sample_rate` from `system_params.yaml`), and call
      `stepinfo_3d(actual[0:3, :], pos_target, time_vec)`. Idempotent —
      same arrays produce the same four numbers. The script also
      exposes a CLI form
      (`python scripts/stepinfo_3d.py actual.npy x y z --sample-rate ...`)
      for quick replay outside the simulator.

scenarios:
  - need: Diagonal fly-from-A-to-B command — `Fly from (0,0,1) to (1,1,2) in 3 seconds`.
    context: After the main loop, `actual` is a (15, N) matrix and `waypoints[0:3, -1] = [1, 1, 2]`. Per-axis 1D `stepinfo` would report three different settling times (one per axis) and the percent overshoots would not match what the verifier checks against.
    action: "Call `stepinfo_3d(actual[0:3, :], waypoints[0:3, -1], tv)`. The function builds the 3D distance signal, returns a single coherent set of metrics, and the orchestrator wraps them as `{'mode': 'fly', **metrics}` before writing `metrics_3d.json`."
    outcome: One row in `metrics_3d.json` with four floats that align with the task's success criteria (`SteadyStateError < 0.05`, `Overshoot_pct < 5`).
  - need: Pure takeoff command — `Take off to 2.5 m height in 5 seconds` — where only z moves.
    context: "`pos_target = [0, 0, 2.5]` and `pos_actual[0:2, :]` stay near 0. The 3D distance signal degenerates to `|z - 2.5|`, so the four metrics equal what a 1D `stepinfo` on `z` would produce."
    action: "Call `stepinfo_3d(actual[0:3, :], waypoints[0:3, -1], tv)` exactly as for diagonal flight — no special case is needed in the orchestrator."
    outcome: The same four-key payload as for diagonal flight, and the verifier accepts both with the same checks.
  - need: Hover-in-place command — `Hover at 1 m height for 2 seconds` starting at (0, 0, 1).
    context: "`d0 = || pos_actual[:, 0] - pos_target ||_2 < 1e-6`. Naively scanning rise/settling produces NaN spam and a divide-by-zero in overshoot."
    action: "The `short-circuit-already-at-target` guard returns `{RiseTime: 0, SettlingTime: 0, Overshoot_pct: 0, SteadyStateError: float(dist[-1])}` without entering the main path."
    outcome: Numbers that survive JSON serialisation and the verifier's range checks (steady-state error stays small as long as the controller holds the hover).
  - need: Short command where the controller never reaches the 2 percent band — `d0 = 0.10 m` so `band = 0.002 m` — but converges smoothly toward the target.
    context: The drone approaches monotonically, never enters the 2 cm settling band, never overshoots. A naive overshoot definition that assumed entry would divide by zero or return NaN.
    action: The overshoot step keeps `in_band = False` for the whole scan and returns `Overshoot_pct = 0.0` by definition. SettlingTime is still set from the backward scan over the full window.
    outcome: A finite four-key payload; the verifier checks against `< 5 %` and passes.

integrations:
  - partner: position-controller-trajectory-planner / motor-model-dynamics
    body: >
      Consumes the (3, n) position rows of the actual-state matrix that
      those skills produce. The contract is that row 0 is x, row 1 is
      y, row 2 is z — slice with `actual[0:3, :]`. The target is the
      last waypoint, `waypoints[0:3, -1]`, where `waypoints` comes
      from the `flight-plan-parser` output.
  - partner: plot-quadrotor
    body: >
      Scalar companion to the diagnostic figures. Typical sequence per
      command is: (1) build trajectories, (2) call `plot_quadrotor(...)`
      so the PNGs land in `plots/`, (3) call `stepinfo_3d(...)`, (4)
      stitch `{'mode': mode, **metrics}` into `metrics_3d.json`. Doing
      the plots first means a failed metrics assertion still leaves
      the diagnostic figures behind for debugging.
  - partner: quadrotor-pid-flight (orchestrator)
    body: >
      The orchestrator owns the `"mode"` field (`takeoff`, `hover`,
      `land`, `fly` — one of the four supported command types) and the
      filesystem path `/root/results/<label>/metrics_3d.json`. This
      skill returns only the four metric floats; the orchestrator
      merges in the mode and writes the file.

anti_patterns:
  - Running 1D `stepinfo` on each axis separately for diagonal flight. The axes are coupled (thrust that corrects x also affects y and z) so per-axis numbers do not describe the true convergence and the verifier's overshoot and steady-state checks will not match.
  - Hardcoding `settling_threshold=0.05` (or any other value) because that is the success cap on steady-state error. The settling band threshold is 0.02 — the success criterion is `SteadyStateError < 0.05 m`. These are unrelated quantities.
  - Using a forward scan for SettlingTime. SettlingTime is the last time the distance exceeds the band, not the first; a forward scan reports a falling edge that the drone may later cross again.
  - Defining overshoot from axis crossings (e.g. `actual_z > target_z`). Overshoot is the maximum 3D distance from the target after entering the settling band, expressed as a percentage of `d0`. Axis-crossing definitions disagree with the verifier and will fail commands that actually converged cleanly.
  - Skipping the `d0 < 1e-6` guard. Hover-in-place commands then divide by zero and emit NaNs into `metrics_3d.json`, which the verifier rejects.
  - Returning numpy scalars (`np.float64`) instead of plain floats. `json.dump` either fails outright or emits non-portable values; cast to `float(...)` before returning.
  - Adding extra keys (`mode`, `command_id`, `success`) to the dict. The orchestrator owns `mode`; downstream stitching breaks when the metric dict carries fields that conflict with the wrapper.
  - Substituting a different rise-time fraction. The contract is 10 percent; changing it silently shifts every RiseTime in the cohort.
```

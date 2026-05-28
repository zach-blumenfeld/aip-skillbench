---
name: quadrotor-pid-flight
description: End-to-end pipeline for quadrotor command-following — parses a natural-language flight command (takeoff / hover / land / fly), generates a quintic minimum-jerk trajectory clamped to per-axis acceleration limits, simulates closed-loop response under a cascaded position+attitude PID controller with first-order motor lag, tunes PID gains until specs are met (per-timestep Euclidean position error < 0.05 m, overshoot < 5%, steady-state error < 0.05 m, planned accel within limits), and writes the exact required artifacts (15×N planned/actual `.npy`, `metrics_3d.json`, `tuning_results.json`, three error plots). Use when implementing a drone/quadrotor flight-control task whose inputs are a `system_params.yaml` plus text commands and whose outputs are step-response metrics over a fixed result-folder layout.
license: Apache-2.0
compatibility: Requires Python 3.11+ with numpy, pyyaml, and matplotlib.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a2/assets/aip-schemas/procedure.schema.json
  author: aip-skillbench
  version: "0.1"
---

```yaml
purpose: >
  Given a quadrotor `system_params.yaml` (mass, inertia, motor lag, per-axis
  acceleration limits) and a natural-language command in one of four
  templates — takeoff, hover, land, or point-to-point fly — plan a smooth
  time-parameterized trajectory that respects the acceleration limits,
  simulate the closed-loop response under a cascaded position+attitude PID
  controller with first-order motor lag, tune the PID gains until all four
  success specs hold (per-timestep Euclidean position error < 0.05 m,
  overshoot < 5%, steady-state error < 0.05 m, planned accel within limits),
  and write the exact required artifacts to `/root/results/<id>/`.

trigger_when:
  - User asks to implement, run, or score a quadrotor / multirotor
    command-following task that pairs a `system_params.yaml` with text
    commands in one of these forms — "Take off to <h> m height in <t>
    seconds", "Hover at <h> m height for <t> seconds", "Land from <h> m
    height in <t> seconds", "Fly from (x,y,z) to (x',y',z') in <t> seconds".
  - Required outputs include a 15-row planned/actual trajectory `.npy`, a
    `metrics_3d.json` with `{mode, RiseTime, SettlingTime, Overshoot_pct,
    SteadyStateError}`, and a `tuning_results.json` with kp/ki/kd × pos/att.
  - Need to compute step-response metrics for a 3-D drone command with
    `settling_threshold = 0.02`.
  - Need to verify per-timestep tracking error or per-timestep planned
    acceleration against fixed numeric specs (0.05 m, 5%, accel limits).

do_not_use_when:
  - The platform is fixed-wing, VTOL, or otherwise non-quadrotor.
  - Task requires wind / disturbance modeling, GPS waypoints, vision-based
    localization, obstacle avoidance, or multi-agent coordination — this
    skill assumes a single drone, known endpoints, no disturbances.
  - The agent only needs to read trajectories that have already been
    produced; this skill is end-to-end planning + simulation + tuning, not
    post-hoc analysis.

scope_and_approval: >
  All actions are local file writes under `<results_dir>` (default
  `/root/results/<id>/`). No network access. Tuning is unsupervised
  numerical search — no human-in-the-loop checkpoint. The planner refuses
  (raises) when a requested command duration would violate physical
  acceleration limits; do not silently rescale duration without asking.

steps:
  - name: load-system-params
    description: Read mass, inertia, gravity, motor time constant, dt, and the three acceleration limits from system_params.yaml.
    script: scripts/load_system_params.py
    inputs:
      - {name: system_params_path, type: string}
    outputs:
      - {name: params, type: object, description: "mass, g, Ixx/Iyy/Izz, motor_tau, accel_limit_*, dt, tilt_limit_deg"}

  - name: parse-command
    description: Match the command text against the four supported templates and extract the mode plus numeric parameters.
    script: scripts/parse_command.py
    inputs:
      - {name: command_path, type: string}
    outputs:
      - {name: command, type: object, description: "{mode, h|p0+p1, t, raw}"}

  - name: plan-trajectory
    description: Generate the (15, max_iter) desired-state matrix using a quintic minimum-jerk profile; check the closed-form peak accel against accel_limit_up / accel_limit_down / accel_limit_horiz and raise if infeasible.
    script: scripts/plan_trajectory.py
    depends_on: [load-system-params, parse-command]
    inputs:
      - {name: command, type: object}
      - {name: params, type: object}
    outputs:
      - {name: planned, type: object, description: "{matrix: 15xN float, dt, max_iter, t_cmd, t_total, p0, p1}"}

  - name: tune-pid
    description: Evaluate defaults; if any spec fails, run a bounded scale-grid over (kp_pos, kd_pos, kp_att+kd_att) and return the best gains plus the simulated actual trajectory.
    script: scripts/tune_pid.py
    depends_on: [plan-trajectory]
    inputs:
      - {name: planned, type: object}
      - {name: params, type: object}
      - {name: command, type: object}
    outputs:
      - {name: gains, type: object, description: "kp_pos, ki_pos, kd_pos, kp_att, ki_att, kd_att — each list[float] length 3"}
      - {name: actual, type: object, description: "{matrix: 15xN float}"}
      - {name: passed, type: boolean}
      - {name: iterations, type: integer}

  - name: compute-metrics
    description: Mode-aware step-response metrics — z axis for takeoff/hover/land, largest-displacement axis for fly — with settling_threshold=0.02.
    script: scripts/compute_metrics.py
    depends_on: [tune-pid]
    inputs:
      - {name: planned, type: object}
      - {name: actual, type: object}
      - {name: command, type: object}
    outputs:
      - {name: metrics, type: object, description: "{mode, RiseTime, SettlingTime, Overshoot_pct, SteadyStateError}"}

  - name: generate-plots
    description: Write desired_vs_actual.png, errors.png, and cumulative_errors.png to <results_dir>/plots/.
    script: scripts/generate_plots.py
    depends_on: [tune-pid]
    inputs:
      - {name: planned, type: object}
      - {name: actual, type: object}
      - {name: results_dir, type: string}
    outputs:
      - {name: plot_paths, type: "list[string]"}

  - name: write-outputs
    description: Write planned_trajectory.npy, actual_trajectory.npy, metrics_3d.json, tuning_results.json with strict required-only keys and exact shapes.
    script: scripts/write_outputs.py
    depends_on: [compute-metrics, generate-plots]
    inputs:
      - {name: planned, type: object}
      - {name: actual, type: object}
      - {name: metrics, type: object}
      - {name: gains, type: object}
      - {name: results_dir, type: string}
    outputs:
      - {name: results_dir, type: string}

  - name: verify-specs
    description: Recheck all four success constraints (SSE, overshoot, planned-accel limits, per-timestep Euclidean pos error). If any fails, surface specifics so the agent can re-enter tune-pid with a wider budget.
    script: scripts/verify_specs.py
    depends_on: [write-outputs]
    inputs:
      - {name: planned, type: object}
      - {name: actual, type: object}
      - {name: metrics, type: object}
      - {name: params, type: object}
    outputs:
      - {name: passed, type: boolean}
      - {name: failures, type: "list[string]"}

modes:
  - name: single-command
    body: >
      Run the full pipeline for one command file end-to-end.
      Use `scripts/run_command.py <command_path> <results_dir>
      [system_params.yaml]` — it composes every step in order and exits
      non-zero if verify-specs reports any failure.

  - name: batch
    body: >
      Iterate every `.txt` file in a commands directory and run
      single-command mode for each. Use `scripts/run_all.py
      <commands_dir> <results_root> [system_params.yaml]`. Each command's
      artifacts go to `<results_root>/<id>/`; a summary line per command is
      printed to stdout.

  - name: replan
    body: >
      When `plan-trajectory` raises because the requested duration violates
      acceleration limits, surface the planner's reported `T_min_required`
      and either ask the user for a feasible duration or, if the task
      explicitly authorizes it, retry with `T = T_min_required * 1.05` for a
      safety margin.

search_shortcuts:
  - category: References
    body: >
      Load on demand —
      `references/dynamics-and-control.md` for the 6-DOF model + cascaded
      PID math;
      `references/trajectory-planning.md` for the quintic profile and the
      accel-limit feasibility derivation;
      `references/tuning-strategy.md` for default-gain rationale and which
      knob to turn when a spec fails;
      `references/output-spec.md` for the exact artifact schemas and the
      four-part success rubric.

scenarios:
  - need: "command: 'Take off to 10 m height in 5 seconds'; accel_limit_up=4, accel_limit_down=2, accel_limit_horiz=3."
    context: "Quintic peak vertical accel = 5.7735·10/5² ≈ 2.31 m/s², within accel_limit_up=4. Feasible; no rescale."
    action: "Plan z(t) = 10·s(t/5); pad sim to 8 s; tune from defaults; verify."
    outcome: "metrics_3d.json mode='takeoff'; SSE < 0.05 m; per-timestep Euclidean error < 0.05 m; all four specs pass."

  - need: "command: 'Fly from (0,0,5) to (3,4,5) in 4 seconds'."
    context: "Horizontal distance 5 m / 4 s → peak horiz accel ≈ 5.7735·5/16 ≈ 1.80 m/s². Within accel_limit_horiz=3."
    action: "Plan x and y as independent quintics; z constant at 5; cascaded controller converts the horizontal acceleration demand into roll/pitch references."
    outcome: "metrics on the dominant-motion axis (y, since |Δy|=4 > |Δx|=3); diagonal flight tracks within spec."

  - need: "command: 'Hover at 5 m height for 3 seconds'."
    context: "Reference is constant. Metrics interpret the initial deviation as the implicit step."
    action: "Plan constant reference; tune until station-keeping holds < 0.05 m and overshoot < 5%."
    outcome: "metrics_3d.json mode='hover'; SettlingTime captures time to enter the 2% band around the setpoint."

  - need: "command: 'Take off to 20 m height in 1 second'."
    context: "Quintic peak accel = 5.7735·20/1² ≈ 115 m/s² — far exceeds any reasonable accel_limit_up."
    action: "plan-trajectory raises with T_min_required (≈ sqrt(115/limit)·T_requested). Switch to replan mode: surface the floor to the user."
    outcome: "No artifacts written until a feasible duration is supplied."

anti_patterns:
  - Silently extending the requested command duration when accel limits are violated. The planner raises with `T_min_required` — surface it; let the agent or user decide.
  - Writing metrics_3d.json with fields beyond the five required keys, or tuning_results.json with anything other than the six required gain vectors. The schemas are strict.
  - Computing position error as a per-axis quantity. The 0.05 m spec is on the **Euclidean** distance `||M[0:3] - A[0:3]||` at every timestep.
  - Setting orientation/angular-velocity rows in the *planned* matrix from the command. Those rows are 0; the cascaded controller derives roll/pitch from the planner's acceleration row, not from a planner-supplied attitude reference.
  - Ending the simulation at `t = t_cmd`. SettlingTime and SteadyStateError need the response well past the command end — pad with `settle_pad(T) = max(3.0, 0.5·T)` seconds.
  - Tuning one global gain set across all command files. Each command file gets its own tune-pid run and its own results folder; gains tuned for a 5-s takeoff will not be optimal for a 2-s land.
  - Skipping verify-specs because the metrics look good. All four constraints must hold simultaneously — planned-accel feasibility is structural and is easy to miss when only tracking metrics.
  - Tuning by editing controller.py. Treat the controller as structural; vary only the gain inputs.
```

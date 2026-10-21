---
name: acc-pid-simulation
description: Build, tune, and evaluate an Adaptive Cruise Control (ACC) simulation in Python. Writes pid_controller.py (PIDController), acc_system.py (AdaptiveCruiseControl with cruise/follow/emergency modes, time-headway spacing, TTC emergency braking), and simulation.py (kinematic ego model driven by recorded lead-vehicle sensor CSV and vehicle_params.yaml). Grid-searches speed and distance PID gains into tuning_results.yaml, runs the full simulation to simulation_results.csv, and writes acc_report.md with rise time, overshoot, steady-state error, and minimum distance. Use for ACC, cruise control, PID speed/gap control, or vehicle-following simulation tasks.
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
  Produce a working, tuned Adaptive Cruise Control simulation from a vehicle/ACC config (YAML) and a
  recorded drive (CSV of time, ego_speed, lead_speed, distance). Scripts write the three Python
  modules, search the PID gains against the recorded drive, run the simulation, verify the CSV
  contract, and write the report. The agent steps in only when the search cannot meet a performance
  target.

trigger_when:
  - A task asks for an adaptive cruise control (ACC) simulation with PID speed and distance control.
  - A task gives vehicle_params.yaml-style ACC settings plus lead-vehicle sensor data and asks for
    tuned PID gains, simulation_results.csv, and a performance report.

do_not_use_when:
  - The task is a generic PID or control exercise with no vehicle following, set speed, or lead vehicle.
  - The task needs a dynamic vehicle model (tire forces, powertrain maps) rather than a kinematic one.

requires:
  interpreter:
    name: python
    version: "3.10"
  packages:
    - pandas
    - pyyaml

steps:
  - name: profile-inputs
    kind: execution
    description: >
      Check that the config has every key AdaptiveCruiseControl reads, and that the sensor CSV has
      time/lead_speed/distance at the config dt with the row count the duration implies. Profile the
      lead-vehicle segments, cut-ins (sensor distance jumps), and the physical rise-time bound. Flag
      every mismatch between the task statement's stated constraints and the config. A missing file
      or column fails the step.
    inputs:
      - name: config_path
        type: string
        description: Path to vehicle_params.yaml in the task container (e.g. /root/vehicle_params.yaml).
      - name: sensor_path
        type: string
        description: Path to sensor_data.csv (columns time, ego_speed, lead_speed, distance; blank lead fields mean no lead vehicle).
      - name: output_dir
        type: string
        description: Directory the deliverables go to (the task's working dir, e.g. /root). simulation.py defaults to config, sensor, and gains files next to itself.
      - name: targets
        type: object
        description: >
          Performance targets from the task statement, keys rise_time_max_s, overshoot_max_pct,
          speed_ss_error_max, distance_ss_error_max, min_distance_min, duration_s
          (e.g. 10, 5, 0.5, 2, 5, 150). Missing keys take those defaults.
      - name: constraints
        type: object
        description: >
          Constraints as the task statement gives them, to cross-check against the config: any of
          set_speed, max_acceleration, max_deceleration, time_headway, min_distance,
          emergency_ttc_threshold, dt, initial_speed. Pass an empty object if the statement gives none.
    script: scripts/profile_inputs.py
    outputs:
      - name: input_profile
        type: object
        description: Rows, expected rows, dt, initial ego speed, lead segments, sensor distance jumps, sensor min distance, the config, min feasible rise time, merged targets.
      - name: input_issues
        type: list[*]
        description: Every non-fatal mismatch or oddity found. Each one is carried into the report.
    inputs_to: build-and-tune

  - name: build-and-tune
    kind: execution
    description: >
      Write pid_controller.py, acc_system.py, and simulation.py into output_dir. Then run a two-stage
      grid search (speed loop, then distance loop), scoring each gain set by simulating the whole
      recorded drive with the delivered simulation.run_simulation. Write the best gains to
      output_dir/tuning_results.yaml.
    inputs:
      - name: config_path
        type: string
      - name: sensor_path
        type: string
      - name: output_dir
        type: string
      - name: targets
        type: object
    script: scripts/build_and_tune.py
    assets:
      - assets/pid_controller.py
      - assets/acc_system.py
      - assets/simulation.py
    outputs:
      - name: tuned_gains
        type: object
        description: The searched gains, pid_speed and pid_distance, each with kp, ki, kd.
      - name: tuning_metrics
        type: object
        description: Metrics of the searched gains, with per-target pass/fail under checks.
      - name: tuning_log
        type: list[*]
        description: One entry per search stage, with the number of gain sets simulated, the best gains, and the cost.
      - name: targets_met
        type: boolean
        description: True when the searched gains meet every performance target.
    inputs_to: by-targets

  - name: by-targets
    kind: router
    description: Report straight away when the search met every target; otherwise retune by hand first.
    branch_on: targets_met
    branches:
      "true": simulate-and-report
      "false": retune

  - name: retune
    kind: client_task
    description: >
      Diagnose the failed checks and retune the gains with acc_common.py (custom grids, or hand edits
      plus evaluate). Leave the final gains in tuning_results.yaml. Never hardcode gains into
      simulation.py and never relax a target. Report a physically infeasible target as such.
    inputs:
      - name: targets
        type: object
      - name: tuned_gains
        type: object
      - name: tuning_metrics
        type: object
      - name: output_dir
        type: string
      - name: config_path
        type: string
      - name: sensor_path
        type: string
    template: assets/retune.md
    references:
      - path: references/acc-design.md
        description: Controller structure, metric definitions, tuning rules, and the failed-check diagnosis table. Load before changing any gains.
    outputs:
      - name: retune_notes
        type: string
        description: Failed checks, what was changed, the final gains, and any check that still fails, with the reason.
    inputs_to: simulate-and-report

  - name: simulate-and-report
    kind: execution
    description: >
      Run the delivered simulation.py, which reads the gains from tuning_results.yaml, to write
      simulation_results.csv. Verify the exact column order, one row per sensor row, the time column,
      blank distance/ttc fields in cruise rows, the acceleration limits, gain bounds, and a
      byte-identical rerun. Compute the final metrics from the CSV and write acc_report.md (system
      design, tuning methodology and final gains, results table). Any failed verification fails the
      step.
    inputs:
      - name: config_path
        type: string
      - name: sensor_path
        type: string
      - name: output_dir
        type: string
      - name: targets
        type: object
      - name: input_profile
        type: object
      - name: input_issues
        type: list[*]
      - name: tuned_gains
        type: object
      - name: tuning_log
        type: list[*]
    script: scripts/simulate_and_report.py
    assets:
      - assets/acc_report_template.md
    outputs:
      - name: final_metrics
        type: object
        description: Rise time, overshoot, speed and distance steady-state errors, min distance, min TTC, mode times, and per-target checks for the final gains.
      - name: verification
        type: object
        description: Each deliverable check and its result (all true when the step succeeds).
      - name: deliverables
        type: list[*]
        description: Paths of pid_controller.py, acc_system.py, simulation.py, tuning_results.yaml, simulation_results.csv, acc_report.md.
    inputs_to: end

  - name: end
    kind: end
    description: The six deliverables in output_dir, their verification, and the final performance metrics.
    inputs:
      - name: final_metrics
        type: object
      - name: verification
        type: object
      - name: deliverables
        type: list[*]

anti_patterns:
  - Copying the sensor distance column into the simulation every step. It was measured from the human driver's car (it falls to about 2 m at a cut-in), so the controller then has no effect on the gap.
  - Embedding tuning logic or literal gains in simulation.py. It must read tuning_results.yaml at runtime.
  - Logging the state after the speed update. Each row is the state before the step, so the second row's ego_speed is 0.3 when the first command is 3.0.
  - Filling distance_error, distance, or ttc in cruise rows, or writing NaN/None text instead of leaving them blank.
  - Scoring distance steady-state error over every follow row. Stretches where the lead pulls away faster than the set speed, or where the actuator is saturated, are not steady state.
  - Relaxing a target, or hand-picking gains that only pass because the follow loop never settles (no steady rows).
  - Using yaml.load instead of yaml.safe_load, or writing the CSV with the pandas index.
```

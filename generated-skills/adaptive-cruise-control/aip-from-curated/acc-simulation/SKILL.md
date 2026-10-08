---
name: acc-simulation
description: Build, tune, and verify an Adaptive Cruise Control (ACC) vehicle simulation in Python from vehicle_params.yaml and a sensor_data.csv of lead-vehicle readings. Covers PID speed and distance control, the cruise/follow/emergency mode state machine, time-headway safe distance, time-to-collision, kinematic speed/gap updates, acceleration limits, PID gain tuning against rise time, overshoot, steady-state error, and minimum-gap targets, a simulation_results.csv export, tuning_results.yaml, and an ACC report. Use for adaptive cruise control, cruise-control PID, vehicle following, and throttle/brake control-loop simulation tasks.
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
  Deliver a working Adaptive Cruise Control simulation for a task that supplies a vehicle
  parameter YAML and a sensor CSV of lead-vehicle readings. The pack carries a tested
  reference implementation (PID with anti-windup, cruise/follow/emergency state machine,
  time-headway distance control, TTC emergency braking, kinematic closed-loop simulation,
  control metrics). Scripts profile the inputs, grid-search the PID gains against the
  task's targets, and verify the produced results CSV. The agent maps the task's file
  names and interfaces, ports the reference code into the deliverables, repairs anything
  verification flags, and writes the report from the measured numbers.

trigger_when:
  - A task asks to implement or simulate adaptive cruise control (ACC) with PID speed and distance control.
  - A task supplies vehicle_params.yaml (vehicle limits, acc_settings, pid_speed, pid_distance, simulation dt) and sensor_data.csv (time, ego_speed, lead_speed, distance).
  - A task asks to tune PID gains for vehicle speed regulation or car following against rise time, overshoot, steady-state error, or minimum-distance targets.

do_not_use_when:
  - The task is a generic PID problem with no vehicle-following component; use the reference scripts/pid_controller.py directly instead.
  - The task needs a dynamic model with tire, engine, or aerodynamic force models beyond kinematics; this pack's model is kinematic.

steps:
  - name: read-task
    kind: client_task
    description: Extract file locations, deliverable names, interfaces, output columns, and numeric targets from the task statement.
    inputs:
      - name: task_statement
        type: string
        description: The task's instructions, verbatim.
      - name: environment_dir
        type: string
        description: Absolute path of the directory holding the task's input files (e.g. /root).
    template: assets/read_task.md
    inputs_to: inspect-inputs

  - name: inspect-inputs
    kind: execution
    description: Load the params YAML (safe_load, merged over defaults) and the sensor CSV; report the config, the time grid, lead-vehicle segments, value ranges, and input warnings.
    inputs:
      - name: params_path
        type: string
      - name: sensor_path
        type: string
    script: scripts/inspect_inputs.py
    inputs_to: choose-distance-model

  - name: choose-distance-model
    kind: decision
    description: Decide how the simulated gap to the lead vehicle is obtained.
    inputs:
      - name: interface_requirements
        type: string
        description: Code-level requirements from the task, including anything it says about distance.
      - name: data_profile
        type: object
      - name: input_warnings
        type: list[*]
    questions:
      distance_model:
        type: choice
        instructions: >
          How must the gap to the lead vehicle be computed during the simulation? The
          ego speed is simulated from the controller's commands, so the recorded distance
          belongs to a different ego trajectory. Choose integrated unless the task explicitly
          says to use the sensor distance values as-is.
        criteria:
          integrated: Default. Seed the gap from the sensor distance when a lead is first detected, then propagate it with gap += (lead_speed - ego_speed) * dt using the simulated ego speed.
          sensor: The task explicitly requires feeding the recorded distance column to the controller unchanged (open-loop replay of the gap).
    thresholds:
      distance_model: 0.3
    inputs_to: tune-gains

  - name: tune-gains
    kind: execution
    description: >
      Grid-search the speed PID (on the initial cruise segment) and then the distance PID (on
      the full closed-loop run). Each candidate is scored against the targets with a 20% margin,
      plus terms for rise time, overshoot, error, emergency count, and command jerk. The tuned
      gains are written to tuning_output_path as pid_speed/pid_distance kp/ki/kd; the params
      file is never modified.
    inputs:
      - name: params_path
        type: string
      - name: sensor_path
        type: string
      - name: targets
        type: object
      - name: distance_model
        type: string
      - name: tuning_output_path
        type: string
    script: scripts/tune_gains.py
    inputs_to: build-deliverables

  - name: build-deliverables
    kind: client_task
    description: Port the reference implementation into the task's requested files and interfaces, then run the simulation script to write the results CSV.
    inputs:
      - name: deliverable_dir
        type: string
      - name: deliverables
        type: object
      - name: interface_requirements
        type: string
      - name: distance_model
        type: string
      - name: tuned_gains
        type: object
      - name: tuning_path
        type: string
      - name: results_path
        type: string
      - name: expected_columns
        type: list[*]
      - name: column_map
        type: object
        description: Task column name -> reference column name; empty when the task uses the reference names.
      - name: sensor_path
        type: string
      - name: params_path
        type: string
    template: assets/build_deliverables.md
    references:
      - path: references/acc-design.md
        description: PID, anti-windup, tuning, vehicle kinematics, TTC, state machine, metrics, and pandas/YAML handling. Load it when adapting the reference code to a different interface or rule.
    inputs_to: verify

  - name: verify
    kind: execution
    description: >
      Check the results CSV (renamed columns mapped back through column_map; unscorable output
      fails rather than passing vacuously): exact columns, one row per sensor row on the same time grid,
      mode labels, acceleration within limits, ego speed simulated rather than copied, and
      agreement with the pack reference. Score it against the targets: speed rise time,
      overshoot, and steady-state error on the initial cruise run; distance steady-state
      error on steady following; minimum gap.
    inputs:
      - name: results_path
        type: string
      - name: sensor_path
        type: string
      - name: params_path
        type: string
      - name: tuning_path
        type: string
      - name: targets
        type: object
      - name: distance_model
        type: string
      - name: expected_columns
        type: list[*]
      - name: column_map
        type: object
    script: scripts/verify_outputs.py
    inputs_to: by-verification

  - name: by-verification
    kind: router
    description: Report once everything passes; otherwise repair and verify again.
    branch_on: all_pass
    branches:
      "true": write-report
      "false": repair

  - name: repair
    kind: client_task
    description: Fix the deliverable code or gains that verification flagged, then re-run the simulation script.
    inputs:
      - name: verification
        type: object
      - name: deliverables
        type: object
      - name: deliverable_dir
        type: string
      - name: tuned_gains
        type: object
      - name: tuning_path
        type: string
      - name: targets
        type: object
    template: assets/repair.md
    references:
      - path: references/acc-design.md
        description: Tuning guidelines, gain effects, and ACC pitfalls. Load it when a target is missed or the control logic needs changing.
    inputs_to: verify

  - name: write-report
    kind: client_task
    description: Write the design, tuning, and results report from the measured numbers.
    inputs:
      - name: deliverables
        type: object
      - name: deliverable_dir
        type: string
      - name: config
        type: object
      - name: data_profile
        type: object
      - name: distance_model
        type: string
      - name: tuned_gains
        type: object
      - name: verification
        type: object
      - name: task_statement
        type: string
    template: assets/report.md
    references:
      - path: references/acc-design.md
        description: Control-design and metric definitions to explain in the report.
    inputs_to: end

  - name: end
    kind: end
    description: Deliverables written, verified against the targets, and reported.
    inputs:
      - name: results_path
        type: string
      - name: tuning_path
        type: string
      - name: tuned_gains
        type: object
      - name: verification
        type: object
      - name: all_pass
        type: boolean

anti_patterns:
  - Copying the recorded ego_speed or distance columns into the results instead of simulating them; the recording came from a different controller and dips below a safe gap.
  - Editing vehicle_params.yaml to store tuned gains; write them to the separate tuning file.
  - Differentiating the distance error in the distance PID; it contains -headway*ego_speed and the D term then chatters between the acceleration limits. Use the gap rate (lead_speed - ego_speed).
  - Letting the integral wind up while the command is saturated at max_acceleration; the speed overshoots by tens of percent.
  - Following a lead faster than set_speed; the follow command is min(speed loop, distance loop), so the ego never exceeds set_speed.
  - Writing 0, "None", or "nan" text for distance, distance_error, or ttc when no lead is detected or the lead is not approaching; leave the cell empty.
  - Inventing mode labels; use exactly cruise, follow, emergency.
  - Putting numbers in the report that did not come from the verification scorecard.
  - Resampling or dropping sensor rows; write one output row per sensor row.
```

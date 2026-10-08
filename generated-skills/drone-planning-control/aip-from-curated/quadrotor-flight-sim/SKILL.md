---
name: quadrotor-flight-sim
description: Build and run a quadrotor (drone) flight simulator from natural-language flight commands ("Take off to 2 m height in 3 seconds", "Hover at", "Fly from (x,y,z) to (x',y',z')", "Land from") and a system_params.yaml - flight-plan parser, acceleration-limited cubic trajectory planner, cascaded position/attitude PID with gain sweep, X-frame motor model with RPM limits and lag, RK45 nonlinear dynamics, 3D step-response metrics (rise/settling/overshoot/steady-state error) and desired-vs-actual plots, writing planned_trajectory.npy, metrics_3d.json, tuning_results.json and plots per command.
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
  Build and run a complete quadrotor flight simulator from natural-language flight commands:
  parse each command file into waypoints and modes, plan an acceleration-limited cubic
  trajectory, close the loop with cascaded position/attitude PID controllers over a motor model
  and nonlinear RK45 dynamics, tune the gains by sweep, and write per-command planned
  trajectories, 3D step-response metrics, tuning results and plots. The pack ships a tested
  implementation of every module (scripts/quadsim) and installs it where the task expects its
  source files, so the agent's work is reconciling the task's interfaces, judging infeasible
  commands and diagnosing failed tuning, not re-deriving the physics.

trigger_when:
  - A task gives drone/quadrotor flight commands such as "Take off to X m height in Y seconds", "Hover at X m height for Y seconds", "Fly from (x,y,z) to (x',y',z') in T seconds" or "Land from X m height in Y seconds" and asks for simulation results.
  - A task asks to implement a flight-plan parser, trajectory planner, position or attitude PID controller, motor model, quadrotor dynamics, stepinfo/step-response metrics or quadrotor plots, driven by a system_params.yaml.
  - A task asks for per-command outputs like planned_trajectory.npy, metrics_3d.json, tuning_results.json or desired-vs-actual plots for a drone simulator.

do_not_use_when:
  - The vehicle is not a multirotor (fixed-wing, ground robot) or the task is pure flight-log analysis with no simulation to build.
  - The trajectory is circular or figure-eight tracking where step-response metrics do not apply (only the plotting and dynamics parts carry over).

steps:
  - name: read-task
    kind: client_task
    description: Extract paths, the code folder and any numeric success criteria from the task statement.
    inputs:
      - name: task_statement
        type: string
        description: The task's instructions, verbatim.
    template: assets/read_task.md
    assets:
      - assets/pack_contract.md
    inputs_to: prepare

  - name: prepare
    kind: execution
    description: Install the simulator modules into workdir, parse every command file, plan each trajectory and check it against the acceleration limits.
    inputs:
      - name: params_path
        type: string
        description: system_params.yaml path.
      - name: commands_dir
        type: string
        description: Folder of NNN.txt command files.
      - name: results_dir
        type: string
        description: Root of the per-command output folders.
      - name: workdir
        type: string
        description: Folder where the task's Python source files belong.
      - name: success_criteria
        type: object
        description: Numeric pass limits stated by the task (may be empty).
    script: scripts/prepare.py
    assets:
      - assets/pack_contract.md
    timeout: 300
    inputs_to: interface-check

  - name: interface-check
    kind: decision
    description: Judge whether the installed modules and output layout already satisfy what the task requires.
    inputs:
      - name: task_statement
        type: string
      - name: pack_contract
        type: string
        description: Installed file names, signatures and output layout.
    questions:
      interfaces_match:
        type: noul
        instructions: Does the installed pack (pack_contract) already provide every source file name, function name and signature, output path, output file name and JSON key that the task statement explicitly requires?
        criteria:
          true: Everything the task names exists in the contract with the same name and shape, or the task names no specific interfaces.
          false: The task names at least one file, function, argument, output path, file name or JSON key the contract lacks or names differently.
    thresholds:
      interfaces_match: 0.2
    inputs_to: by-interface

  - name: by-interface
    kind: router
    description: Adapt the installed copies only when the task's interfaces differ.
    branch_on: interfaces_match
    branches:
      "true": by-feasibility
      "false": adapt-interfaces

  - name: adapt-interfaces
    kind: client_task
    description: Add wrappers/aliases or edit the installed copies in workdir so the task's required interfaces exist.
    inputs:
      - name: task_statement
        type: string
      - name: pack_contract
        type: string
      - name: workdir
        type: string
    template: assets/adapt_interfaces.md
    references:
      - path: references/model-reference.md
        description: Exact parser rules, trajectory, controller, motor, dynamics, metric and plot definitions. Load only if the task redefines one of them and you must change the math.
    inputs_to: by-feasibility

  - name: by-feasibility
    kind: router
    description: Commands whose cubic plan exceeds the acceleration limits need a timing decision first.
    branch_on: all_feasible
    branches:
      "true": tune-gains
      "false": handle-infeasible

  - name: handle-infeasible
    kind: client_task
    description: Decide whether to stretch segments that exceed the acceleration limits or keep the commanded timing.
    inputs:
      - name: infeasible
        type: list[*]
        description: Commands with limit violations.
      - name: params_summary
        type: object
      - name: task_statement
        type: string
    template: assets/handle_infeasible.md
    inputs_to: tune-gains

  - name: tune-gains
    kind: execution
    description: Sweep second-order PID gain sets on the shortest command per mode plus the most aggressive one and select the most conservative set within 10% of the best cost.
    inputs:
      - name: params_path
        type: string
      - name: commands_dir
        type: string
      - name: workdir
        type: string
      - name: success_criteria
        type: object
      - name: stretch_infeasible
        type: boolean
    script: scripts/tune_gains.py
    timeout: 1200
    inputs_to: run-simulations

  - name: run-simulations
    kind: execution
    description: Simulate every command and write planned_trajectory.npy, metrics_3d.json, tuning_results.json and plots per command, then re-check limits, criteria and files.
    inputs:
      - name: params_path
        type: string
      - name: commands_dir
        type: string
      - name: results_dir
        type: string
      - name: workdir
        type: string
      - name: tuning_results
        type: object
        description: Selected gains kp_pos, ki_pos, kd_pos, kp_att, ki_att, kd_att.
      - name: success_criteria
        type: object
      - name: stretch_infeasible
        type: boolean
    script: scripts/run_simulations.py
    timeout: 1800
    inputs_to: by-result

  - name: by-result
    kind: router
    description: Finish when every command passes; otherwise retune.
    branch_on: all_pass
    branches:
      "true": end
      "false": retune

  - name: retune
    kind: client_task
    description: Diagnose the failing commands and choose new gains (or fix the plan), then re-run the simulations.
    inputs:
      - name: failures
        type: list[*]
      - name: tuning_results
        type: object
      - name: tuning_top_candidates
        type: list[*]
      - name: success_criteria
        type: object
      - name: simulator_lib
        type: string
      - name: params_path
        type: string
      - name: commands_dir
        type: string
    template: assets/retune.md
    references:
      - path: references/tuning-guide.md
        description: Symptom→fix tables for the position and attitude loops, starting gains, ki limits and the gain ranges that were stable on the reference vehicle. Load before choosing new gains.
      - path: references/model-reference.md
        description: Controller, motor and dynamics equations. Load if a failure looks like a model or saturation problem rather than a gain problem.
    inputs_to: run-simulations

  - name: end
    kind: end
    description: Every command simulated, its outputs written under results_dir, and the selected gains.
    inputs:
      - name: results
        type: list[*]
        description: Per-command metrics, accel check, failures and output folder.
      - name: tuning_results
        type: object
      - name: results_dir
        type: string
      - name: all_pass
        type: boolean

anti_patterns:
  - Hardcoding dt = 0.005, time_final, or any output path; dt = 1/sample_rate from system_params.yaml and time_final = waypoint_times[-1] from the parsed plan.
  - Using a mutable default argument for a PID integral; create it with make_position_integral() / make_attitude_integral() once per run, before the loop, and pass it explicitly.
  - Matrix-multiplying the gain arrays; they are [x,y,z] / [phi,theta,psi] arrays applied element-wise, then the inertia @ in the attitude law.
  - Starting a takeoff with the motors at 0 RPM (below rpm_min); the simulator starts at hover RPM on the first trajectory sample, or the vehicle drops before the loop catches it.
  - Inserting a (0,0,0) start for land, hover or fly commands; their first command states where the vehicle already is.
  - Fitting a 2-point not-a-knot spline (it degenerates to a straight line with a velocity jump); use clamped cubics per segment.
  - Retuning gains to fix an acceleration-limit violation; the motors saturate regardless, so fix the plan's timing.
  - Large integral gains (attitude ki > 0.5, x/y position ki); wind-up shows up as x/y oscillation during z-only moves.
  - Printing progress to stdout from library code called by step scripts; the step's stdout must be one JSON object.
```

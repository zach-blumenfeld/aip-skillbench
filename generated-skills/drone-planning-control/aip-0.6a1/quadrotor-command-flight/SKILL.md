---
name: quadrotor-command-flight
description: Simulate a quadrotor flying natural-language commands ("Take off to h m height in t seconds", "Hover at h m height for t seconds", "Land from h m height in t seconds", "Fly from (x,y,z) to (x',y',z') in t seconds") from system_params.yaml — parse to waypoints, plan an acceleration-limited minimum-jerk trajectory, simulate motor lag and nonlinear dynamics with RK45, tune cascaded position/attitude PID gains per command, and write metrics_3d.json (3D rise/settling/overshoot/steady-state), tuning_results.json, planned/actual 15×N trajectory .npy files, and error plots per command. Use for drone/UAV trajectory planning, PID tuning, and step-response evaluation tasks.
metadata:
  aip-version: "0.6a1"
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
  Turn every natural-language flight command file in a folder into a simulated,
  PID-tuned quadrotor flight and its graded outputs. One script parses each command
  into waypoints, plans a minimum-jerk quintic (or a trapezoidal profile, when the
  quintic would break the accel_limit_up/down/horiz limits) 15-row desired state,
  simulates the X-frame motor model with first-order lag and the nonlinear Euler
  dynamics with RK45 at sample_rate, runs a cascaded position PID (full thrust-vector
  inversion) and attitude PID, searches a grid of their gains per command,
  and writes metrics_3d.json, tuning_results.json, planned_trajectory.npy,
  actual_trajectory.npy, and plots/ under results_dir/<label>/. Commands that fail
  the success criteria (steady-state error < 0.05 m, overshoot < 5 %, planned
  acceleration within limits, per-timestep position error < 0.05 m) or cannot be
  parsed go to you for diagnosis and one targeted retry.

trigger_when:
  - A task gives drone/quadrotor system parameters (mass, thrust_coefficient, rpm limits, inertia, sample_rate, accel limits) and text commands to fly in simulation.
  - Commands read like "Take off to 2 m height in 3 seconds", "Hover at 1 m height for 5 seconds", "Land from 2 m height in 2 seconds", or "Fly from (0,0,1) to (2,2,1) in 3 seconds".
  - You must produce per-command metrics_3d.json, tuning_results.json, planned/actual trajectory .npy files, or desired-vs-actual error plots.
  - You need to tune position and attitude PID gains so a simulated drone tracks a planned trajectory within centimetres.

do_not_use_when:
  - Flying a real drone or generating PX4/ArduPilot mission files; this is simulation only.
  - Circular, figure-eight, or other continuous-path tracking where point-to-point step metrics do not apply (use RMS or cumulative error instead).
  - Fixed-wing or other non-quadrotor vehicles.

requires:
  interpreter:
    name: python
    version: "3.10"
  packages:
    - numpy>=1.26
    - scipy>=1.13
    - matplotlib>=3.8
    - pyyaml

steps:
  - name: tune-and-simulate
    kind: execution
    description: >
      For every <label>.txt in commands_dir (sorted): parse, plan, check acceleration
      limits, simulate 19 PID gain sets with RK45, keep the best (all criteria pass,
      then smallest max tracking error), and write all outputs to results_dir/<label>/.
      Commands run in parallel across the CPUs; about 1-2 minutes for 30 commands. The
      parameters are read from params_path, never hardcoded.
    inputs:
      - name: commands_dir
        type: string
        description: Absolute path to the folder of command .txt files, one or more command lines each (in the task container /root/commands). Scripts run from their own folder, so relative paths break.
      - name: params_path
        type: string
        description: Absolute path to the drone system_params.yaml (in the task container /root/system_params.yaml).
      - name: results_dir
        type: string
        description: Absolute path to the output root; one subfolder per command label (in the task container /root/results).
    script: scripts/run_all.py
    timeout: 3600
    outputs:
      - name: report
        type: list[*]
        description: One entry per command - label, command, status (simulated|unparsed), mode, profiles, plan_feasible, accel peaks, metrics, max_pos_err, criteria, pass, gains.
      - name: failed
        type: list[*]
        description: Labels that are unparsed or fail any success criterion.
      - name: run_status
        type: string
        description: all_pass when failed is empty, else some_failed.
    inputs_to: by-run-status

  - name: by-run-status
    kind: router
    description: Finish when every command passed; otherwise diagnose and retry the failures.
    branch_on: run_status
    branches:
      all_pass: end
      some_failed: plan-retry

  - name: plan-retry
    kind: client_task
    description: Diagnose each failed command and write a retry spec - canonical rewrite, new gain base, or a skip reason.
    inputs:
      - name: report
        type: list[*]
      - name: failed
        type: list[*]
    template: assets/retry-task.md
    references:
      - path: references/quadrotor-reference.md
        description: Parser forms, planner and acceleration limits, motor/dynamics equations, controller laws, default gains, symptom-to-gain tuning table, metric definitions, output layout. Load when choosing new gains or judging feasibility.
    outputs:
      - name: retry_spec
        type: object
        description: Keyed by failed label; each value has command (string or null), gains (six-key object of 3-float lists, or null), skip_reason (string or null).
    inputs_to: rerun-failed

  - name: rerun-failed
    kind: execution
    description: Re-run each label in retry_spec (rewritten command and/or wide gain grid around the given base), overwriting that label's outputs; skipped labels are left as they are.
    inputs:
      - name: commands_dir
        type: string
      - name: params_path
        type: string
      - name: results_dir
        type: string
      - name: retry_spec
        type: object
    script: scripts/rerun_failed.py
    timeout: 3600
    outputs:
      - name: retry_report
        type: list[*]
        description: Same entry shape as report for each retried label, plus rewritten_from; skipped labels carry status skipped and reason.
      - name: still_failed
        type: list[*]
        description: Labels that still fail after the retry; report them with their reason, do not loop again.
    inputs_to: end

  - name: end
    kind: end
    description: >
      Every command has results_dir/<label>/ with metrics_3d.json, tuning_results.json,
      planned_trajectory.npy, actual_trajectory.npy, and plots/. The report (and
      retry_report/still_failed when a retry ran) states which commands meet the criteria.
    inputs:
      - name: results_dir
        type: string
      - name: report
        type: list[*]

anti_patterns:
  - Hardcoding dt = 0.005, time_final, mass, or any limit instead of reading system_params.yaml and the parsed plan; another instance of the task has different numbers.
  - Starting hover, land, or fly simulations at the origin; the drone starts where the command says it is, or the first-timestep position error alone fails the 0.05 m criterion.
  - Shortening or stretching a command's duration, or changing its heights or coordinates, to make it pass; an infeasible command is reported, not rewritten.
  - Using the small-angle thrust law F = m(g + az) and tilt = a/g for fast or diagonal flights; it loses altitude while tilted. Use F = m|a + g e3| and atan2 tilts (drone_sim.attitude_planner).
  - Planning with a clamped cubic; its acceleration step at the start of every segment doubles the tracking error. Use the quintic (zero end acceleration).
  - Using the source skills' starting gains (kp_pos 0.1, kp_att [100,100,50]) as final gains; they cannot track within 5 cm.
  - Reusing integral state across simulations (mutable default argument); build fresh integrals with make_position_integral() and make_attitude_integral() before each run.
  - Raising ki_att above 0.5; attitude integral wind-up makes x/y oscillate during z-only manoeuvres.
  - Writing outputs anywhere but results_dir/<label>/ (label = command file stem), or hardcoding the plots path.
  - Re-running the retry step in a loop; one targeted retry, then report what still fails and why.
```

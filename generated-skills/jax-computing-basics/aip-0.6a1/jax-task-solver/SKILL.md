---
name: jax-task-solver
description: Solve batches of JAX numerical-programming tasks listed in a problem.json (id, description, input .npy/.npz, output .npy) — row/column reductions, vmap elementwise maps, jax.grad of logistic loss, lax.scan RNN forward passes, jax.jit MLPs, and custom JAX code — loading each input, computing with JAX, and saving each result to its output path.
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
  Turn a problem.json of JAX programming tasks into saved .npy results. A script reads
  every task, inspects its input arrays, and proposes an op from a tested JAX catalog
  (reduce, vmap map, logistic-loss gradient, lax.scan RNN, jitted MLP); the agent
  confirms or corrects each proposal against the task's wording; a script computes
  and saves every planned task with JAX; anything outside the catalog, or any task that
  errored, goes back to the agent to write JAX code for.

trigger_when:
  - A task gives a problem.json listing JAX tasks with "id", "description", "input", "output" keys.
  - Asked to load .npy/.npz arrays, compute with JAX (jnp, vmap, grad, lax.scan, jit), and save results as .npy.
  - Asked for a row/column mean, an elementwise square via vectorization, a logistic-loss gradient, an RNN forward pass with scan, or a JIT-compiled MLP in JAX.

do_not_use_when:
  - The task needs model training loops, optimizers, or datasets beyond the given arrays (this computes single forward/gradient passes).
  - The computation must be done in a framework other than JAX (PyTorch, TensorFlow).

requires:
  interpreter:
    name: python
    version: "3.10"
  packages:
    - jax
    - jaxlib
    - numpy

steps:
  - name: inspect
    kind: execution
    description: Read problem.json, resolve each task's input/output paths against its folder, list the input arrays' names, shapes and dtypes, and propose a catalog op with args.
    inputs:
      - name: problem_path
        type: string
        description: Absolute path to problem.json (in the task container usually /app/problem.json). Relative input/output paths inside it resolve against its folder.
    script: scripts/inspect_tasks.py
    outputs:
      - name: tasks
        type: list[*]
        description: One object per task — id, description, absolute input and output paths, arrays (name -> shape, dtype), suggested_op, suggested_args, notes.
    inputs_to: plan

  - name: plan
    kind: client_task
    description: Check each suggested op against the task description and input arrays, correct it where wrong, and return the plan to execute.
    inputs:
      - name: tasks
        type: list[*]
    template: assets/plan.md
    references:
      - path: references/jax-ops.md
        description: Library API, exact formulas (logistic loss, RNN step, MLP), row/column axis conventions, and the source skill's requirements. Load when a suggestion carries notes or the description does not match a catalog op cleanly.
    outputs:
      - name: plan
        type: list[*]
        description: One entry per task, same order — {id, op, args, input, output}; op is reduce, map, logistic_grad, rnn_scan, mlp, or custom.
    inputs_to: compute

  - name: compute
    kind: execution
    description: Run every planned catalog op with JAX (float32), save each result with np.save to its output path, and report shape, dtype, finiteness and per-task status.
    inputs:
      - name: plan
        type: list[*]
    script: scripts/run_tasks.py
    timeout: 600
    outputs:
      - name: results
        type: list[*]
        description: One object per task — id, op, output, status (ok, custom, error), shape, dtype, finite, message.
      - name: status
        type: string
        description: complete when every task saved (status ok), needs_agent when any is custom or error.
    inputs_to: by-status

  - name: by-status
    kind: router
    description: Done when every task saved; otherwise the agent finishes the custom and errored tasks.
    branch_on: status
    branches:
      complete: end
      needs_agent: finish-remaining

  - name: finish-remaining
    kind: client_task
    description: Write, run, and check JAX code for every task the compute script left as custom or error, saving each to its output path.
    inputs:
      - name: plan
        type: list[*]
      - name: results
        type: list[*]
    template: assets/custom.md
    references:
      - path: references/jax-ops.md
        description: Library API to import, exact formulas and conventions, and the source skill's requirements (validation, numerical stability, side-effect-free transforms). Load before writing any custom JAX code.
    outputs:
      - name: custom_results
        type: list[*]
        description: One object per finished task — id, output, shape, dtype, how.
    inputs_to: end

  - name: end
    kind: end
    description: Every task in problem.json has its result saved as .npy at its output path; results lists what the compute script saved.
    inputs:
      - name: results
        type: list[*]

anti_patterns:
  - Resolving problem.json's relative input/output paths against the current directory instead of problem.json's folder; outputs land in the wrong place and the grader finds nothing.
  - Reducing "mean of each row" over axis 0; one value per row means axis 1 on a 2-D array.
  - Starting the RNN scan from zeros when the npz provides an initial state (init / h0); use the file's state.
  - Returning only the final RNN hidden state when the task asks for the forward pass; save the full (T, H) sequence of hidden states.
  - Putting an activation or softmax on the MLP's last layer when the description does not ask for one.
  - Writing log(1 + exp(z)) literally in the logistic loss; use jnp.logaddexp(0, z) for stability.
  - Enabling float64 (jax_enable_x64) or converting to NumPy mid-computation; keep JAX float32 arrays and convert only at save time.
  - Skipping a task or leaving one unsaved because it looked unsupported; route it to custom and write the JAX code.
  - Reading a reference/expected-output file to produce or tune a result; compute every result from the task's input.
```

---
name: jax-array-tasks
description: Solve batches of small JAX numerical tasks defined in a problem spec (e.g. problem.json with id/description/input/output) over .npy/.npz files - row/column reductions (mean, sum...), vmap elementwise maps (square...), jax.grad of logistic loss, lax.scan RNN forward passes, and jax.jit-compiled MLP forwards - and save each result as a .npy file. Use for JAX array operations, automatic differentiation, JIT compilation, scan/map/reduce, and gradient computations on given data files.
license: Proprietary. LICENSE.txt has complete terms
compatibility: Python 3 with jax, jaxlib, and numpy (the task container ships jax==0.8.2, numpy==2.4.1).
metadata:
  aip-version: "0.5a1"
  source: jax-skills (curated)
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
  Compute a batch of JAX array tasks from a problem spec and save each result as .npy.
  A script reads the spec, inspects every input file (array keys, shapes, dtypes, label
  values) and proposes an op plan; you check the plan against each task's wording; a
  second script computes every result with JAX (vmap, jax.grad, lax.scan, jax.jit),
  checks its shape and finiteness, saves it, and re-reads the file. Failed or misread
  tasks loop back through a plan repair until every result is saved.

trigger_when:
  - A task lists JAX computations (reduce, map/square, logistic gradient, RNN scan, JIT MLP) over .npy/.npz inputs with named .npy outputs, e.g. a problem.json of {id, description, input, output}.
  - Someone asks to load NumPy data into JAX, transform it (vmap, grad, scan, jit), and save the result to a NumPy file.

do_not_use_when:
  - The work is model training loops, optimizers, or large-scale ML pipelines rather than one-shot array computations.
  - The inputs are not NumPy files (images, CSV tables, text) and no array task spec exists.

steps:
  - name: survey
    kind: execution
    description: >
      Read the task list from problem_path (a JSON list of {id, description, input, output};
      or pass `tasks` inline in the state to skip the file). Input paths resolve against
      `base_dir` if given, else the folder holding problem_path - in the container that is
      usually /app or /root, where data/ lives next to problem.json. Bare output names go
      under output_dir; write outputs exactly where the task instructions say. The script
      lists every array in each input file and proposes op + params per task, tagging
      unclear points "AMBIGUOUS" in plan_warnings.
    inputs:
      - name: problem_path
        type: string
        description: Absolute path to the problem spec JSON (e.g. /app/problem.json).
      - name: output_dir
        type: string
        description: Folder where bare output names (e.g. basic_reduce.npy) are written; created if missing.
    script: scripts/survey.py
    assets:
      - assets/ops.json
    inputs_to: review-plan

  - name: review-plan
    kind: decision
    description: Check the proposed plan against each task's wording and the arrays actually on disk before anything is computed.
    inputs:
      - name: plan
        type: list[*]
        description: One entry per task with id, description, input, output, op, params, notes.
      - name: inventory
        type: list[*]
        description: Per input file, every array key with shape, dtype, and (if few) its unique values.
      - name: plan_warnings
        type: list[*]
        description: Survey notes flagged AMBIGUOUS.
    questions:
      plan_ok:
        type: noul
        instructions: >
          Does every plan entry compute exactly what its description asks, on the right arrays?
          Check: op matches the wording; a reduce over "each row" has axis 1 for a 2-D array
          (one value per row) and "each column" has axis 0; map ops keep the input shape; the
          logistic gradient uses x, y, and the file's own w with labels in {-1,+1} (or "01" if
          the labels are 0/1); the RNN uses the file's initial state when it has one, returns all
          hidden states, keeps Wx @ x_t for square Wx, and uses one convention for both matrices (x @ Wx with an (in, hidden) Wx means h @ Wh too); the MLP is relu(x@W1+b1)@W2+b2 with
          no output activation unless the description names another; output paths are where the
          task wants them. Any "unknown" op or unresolved AMBIGUOUS warning means false.
        criteria:
          true: Every entry's op, params, keys, and output path match its task; no open AMBIGUOUS item.
          false: At least one entry is unknown, misread, or still ambiguous.
    thresholds:
      plan_ok: 0.2
    inputs_to: plan-gate

  - name: plan-gate
    kind: router
    description: A correct plan goes straight to compute; anything else is repaired first.
    branch_on: plan_ok
    branches:
      "true": compute
      "false": fix-plan

  - name: fix-plan
    kind: client_task
    description: Repair the plan entries that are misread, ambiguous, unsupported, or that failed in compute.
    inputs:
      - name: plan
        type: list[*]
      - name: inventory
        type: list[*]
      - name: plan_warnings
        type: list[*]
      - name: results
        type: list[*]
        description: Last compute results (empty before the first compute).
    template: assets/fix_plan.md
    assets:
      - assets/ops.json
    references:
      - path: references/jax-ops.md
        description: The original jax-skills API, the plan entry/params schema per op, and interpretation rules (axis wording, logistic labels and stability, RNN carry/orientation, MLP layout, dtype). Load whenever you edit an entry.
    inputs_to: compute

  - name: compute
    kind: execution
    description: >
      Run every plan entry with JAX: reduce via jnp.<func>(axis), map via jax.vmap, logistic
      gradient via jax.grad of mean(logaddexp(0, -y*(x@w))), RNN via jax.lax.scan with tanh,
      MLP via jax.jit. Each result is checked for expected shape and NaN/Inf, saved with
      np.save as float32 .npy, and re-read to confirm. One failing task does not stop the others.
    inputs:
      - name: plan
        type: list[*]
    script: scripts/compute.py
    inputs_to: result-gate

  - name: result-gate
    kind: router
    description: All results saved and verified ends the run; any error goes back to plan repair with the error messages in results.
    branch_on: all_ok
    branches:
      "true": end
      "false": fix-plan

  - name: end
    kind: end
    description: Every task's result saved as .npy at its output path, with shape, dtype, and a value preview per task.
    inputs:
      - name: results
        type: list[*]
        description: Per task - id, op, saved path, status "ok", shape, dtype, min, max, preview.
      - name: all_ok
        type: boolean

anti_patterns:
  - Copying the original example's axis=0 for "mean of each row"; per-row means reduce axis 1 and give one value per row.
  - Computing the logistic loss as log(1 + exp(-y*z)) instead of logaddexp(0, -y*z), or evaluating the gradient at zeros when the file supplies w.
  - Ignoring an initial hidden state stored in the file, or returning only the last RNN state instead of the full (T, H) sequence.
  - Adding an activation on the MLP output layer, or transposing weights that are already stored (in, out).
  - Hardcoding numbers or shapes from one dataset; every value must come from the file given.
  - Side effects (prints, Python mutation) inside functions passed to vmap, scan, or jit.
  - Converting to NumPy mid-computation; stay in jnp and convert only when saving.
```

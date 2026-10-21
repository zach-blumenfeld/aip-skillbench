---
name: jax-array-tasks
description: Solve batches of small JAX programming tasks listed in a problem.json (id, description, input .npy/.npz, output .npy) — row/column reductions, vmap elementwise maps, logistic-loss gradients with jax.grad, lax.scan RNN forward passes, and jit-compiled 2-layer MLPs — then save and verify each result. Use when a task asks you to read arrays, compute with JAX, and write .npy outputs.
compatibility: Python >= 3.10 with jax and jaxlib (>= 0.4; tested 0.8.2) and numpy (>= 1.24; tested 2.4.1). No other packages or tools.
---

# JAX Array Tasks

## Trigger When

1. A problem.json file lists tasks with `id`, `description`, `input`, `output` and asks for JAX code that writes each output file.
2. A task asks to reduce an array (mean/sum/... of rows or columns), map a function over every element with vectorization (`vmap`), compute a gradient of logistic loss, run an RNN with `lax.scan`, or JIT-compile an MLP.
3. Any request to load `.npy`/`.npz` arrays, compute with JAX, and save results as `.npy`.

## Purpose

Turns each task description into a typed plan entry (which op, which axis, which function), then runs a tested JAX implementation of that op, saves the `.npy`, and cross-checks it against an independent NumPy recompute and against a `reference` folder next to problem.json if one exists. It carries the conventions that decide correctness here: row = `axis=1`, labels in {-1,+1} with a `logaddexp` loss, `h_t = tanh(Wx x_t + Wh h_{t-1} + b)` with `h0` from the file, all hidden states returned, ReLU hidden layer with a linear output, and float32 kept as is.

## Setup

Before the first script, check `python3 -c "import jax, numpy; print(jax.__version__, numpy.__version__)"`. If anything is missing, name all of it (jax, jaxlib, numpy) and install it with `pip install jax numpy` (add `--break-system-packages` on Ubuntu system Python). In the task container (Dockerfile) jax 0.8.2 and numpy 2.4.1 are already installed. All commands below run from the skill folder; `PROBLEM` is the path to problem.json (often `/app/problem.json`).

Paths in problem.json are relative to the directory holding problem.json: with `/app/problem.json`, input "data/x.npy" means `/app/data/x.npy` and output "basic_reduce.npy" is written to `/app/basic_reduce.npy`. Use `--out-dir DIR` only if the instructions name a different output folder.

## Procedure

- [ ] 1. Inspect (execution)
- [ ] 2. Classify each task (decision)
- [ ] 3. Write the plan and run (execution)
- [ ] 4. Hand-write any `other` task (client task)
- [ ] 5. Verify (execution)

### 1. Inspect — execution

```bash
python3 scripts/jax_tasks.py inspect PROBLEM
```

Prints, per task: description, resolved input/output paths, every array in the input (key, shape, dtype) and a keyword `suggested_op`. The suggestion is only a hint; step 2 decides.

### 2. Classify each task — decision

Answer these for every task, using its description and the array listing from step 1. Answer all of them for all tasks in one pass.

```yaml
operation:
  type: choice
  instructions: Which computation does the task description ask for?
  criteria:
    reduce: Collapse an array along an axis or entirely - mean, sum, max, min, prod, std, var of rows, columns, or all values.
    map: Apply one function to every element independently (square, abs, exp, ...), shape unchanged; "vectorization"/"vmap" points here.
    logistic_grad: Gradient of logistic (log) loss with respect to the weights, from an .npz with features x, labels y, weights w.
    rnn_scan: RNN / recurrent forward pass over a sequence (lax.scan), from an .npz with seq, Wx, Wh, b (optionally init).
    mlp: Forward pass of a 2-layer MLP / feed-forward net (optionally "JIT compile"), from an .npz with X, W1, b1, W2, b2.
    other: Anything not covered above, or one of the above with a twist the plan fields below cannot express (extra layer, different loss, softmax output, returning only the last hidden state, regularization term).
reduce_axis:
  type: choice
  instructions: Only for operation=reduce (others answer n/a). Which axis does the description collapse?
  criteria:
    "1": Per row - "of each row", "row-wise", "for every sample" on a 2-D (samples x features) array. Output length = number of rows.
    "0": Per column - "of each column", "column-wise", "per feature", "along axis 0". Output length = number of columns.
    all: A single scalar over every element - "overall", "total", "of the array" with no row/column qualifier.
    n/a: operation is not reduce.
fn:
  type: choice
  instructions: Which function does a reduce or map task name (directly or by a clear synonym - average = mean, "x^2"/"x*x" = square, "negate" = negative)? If it names one not listed for its operation, change operation to other.
  criteria:
    mean | sum | max | min | prod | std | var: The reduction for operation=reduce.
    square | abs | exp | log | sqrt | tanh | sigmoid | relu | negative | sin | cos: The elementwise function for operation=map.
    n/a: operation is neither reduce nor map.
```

Costly mistakes: a wrong `reduce_axis` silently produces a valid-looking array of the wrong length — reconsider any close call and confirm the expected output length against the shapes from step 1. Picking a scripted op for a task that actually has a twist is worse than picking `other`; when the description adds anything beyond the criteria above, lean `other`.

### 3. Write the plan and run — execution

Write `/tmp/jax_plan.json` (outside the output folder) with one entry per task id; every id must appear:

```json
[
  {"id": "basic_reduce", "op": "reduce", "fn": "mean", "axis": 1},
  {"id": "map_square",  "op": "map", "fn": "square"},
  {"id": "grad_logistic", "op": "logistic_grad"},
  {"id": "scan_rnn", "op": "rnn_scan"},
  {"id": "jit_mlp", "op": "mlp", "hidden": "relu", "output": "none"},
  {"id": "something_new", "op": "other"}
]
```

Map answers to fields: `operation` → `op`; `reduce_axis` "1"/"0" → `"axis": 1`/`0`, all → `"axis": null` (a list such as `[0, 1]` is also accepted); `fn` → `"fn"`. Optional fields:

- `"array_key"` — for reduce/map on an `.npz` with several arrays, which one to use.
- `"keys"` — map canonical names to `.npz` keys when auto-matching fails, e.g. `{"x": "features", "w": "theta"}`. Canonical names: logistic `x,y,w`; rnn `seq,Wx,Wh,b,init`; mlp `X,W1,b1,W2,b2`.
- `"y_transform": "pm1"` — logistic only; converts labels {0,1} → {-1,+1}. Use it only if the script warns that labels are {0,1} *and* the description treats them as binary classes; otherwise keep labels as given.
- `"use_init": false` — rnn only; ignore an `init` array and start from zeros (only if the description says so).
- `"hidden"`, `"output"` — mlp activations, one of relu, tanh, sigmoid, gelu, none. Default relu / none (logits, no softmax); change only if the description names another.

```bash
python3 scripts/jax_tasks.py run PROBLEM /tmp/jax_plan.json
```

It validates the plan first (exit 2 with a list of problems — fix the plan and rerun), then for each task computes in JAX, saves the `.npy`, and prints `numpy-check` and, when a `reference` folder next to problem.json holds a file of the same name, `reference` lines. Exit 0 means every computed task passed; exit 1 means a `MISMATCH`, `ERROR`, or NaN — read the line, revisit the step-2 answer for that task (axis first), fix the plan, rerun. `other` tasks print `SKIPPED` and go to step 4. Never copy a reference file into an output; the check exists to catch mistakes, and other task instances have none.

What each op computes (so you can judge a mismatch):

| op | computation |
|---|---|
| reduce | `jnp.<fn>(a, axis=axis)` |
| map | `jax.vmap(f)(a)` with elementwise `f` (square is `x*x`) |
| logistic_grad | `jax.grad(lambda w: mean(logaddexp(0, -y * (x @ w))))(w)`, evaluated at the file's `w` |
| rnn_scan | `lax.scan` of `h = tanh(Wx @ x_t + Wh @ h + b)`, `h0` = `init` if present else zeros; returns all states `(T, H)`. If `Wx` is `(D_in, H)` and not square, uses `x_t @ Wx` |
| mlp | `jax.jit(lambda x: act_out(act_h(x @ W1 + b1) @ W2 + b2))(X)`; transposed weights are detected from shapes |

### 4. Hand-write `other` tasks — client task

For each `other` entry, write a short JAX script that loads the input, computes what the description asks, and saves the result to the task's resolved output path as a plain `.npy`. Reuse the helpers:

```python
import sys; sys.path.insert(0, "/path/to/jax-array-tasks/scripts")  # this skill's scripts/ folder
import jax, jax.numpy as jnp
import jax_tasks as jt
d = jt.load("/app/data/input.npz")        # dict of jnp arrays (.npz) or one jnp array (.npy)
out = jax.jit(lambda a: ...)(d["x"])      # JAX ops: jax.grad, jax.vmap, jax.lax.scan, jax.jit
jt.save(out, "/app/result.npy")           # np.save(np.asarray(out))
```

Keep float32, write the function pure (no side effects inside `vmap`/`scan`/`jit`), use `jnp.logaddexp`/`jax.nn` functions for stable log/exp, and check input shapes before computing.

### 5. Verify — execution

```bash
python3 scripts/jax_tasks.py verify PROBLEM --plan /tmp/jax_plan.json
```

Confirms every output exists, loads, is finite, and (for scripted ops) matches the NumPy recompute and any reference file. Finish only on `ALL OK`; on a failure fix that task and rerun steps 3–5.

## Gotchas

- "Mean of each row" is `axis=1` (output length = rows). The original library example uses `axis=0`; do not copy it.
- Logistic labels are {-1,+1} and the loss is `log(1 + exp(-y·(x@w)))`; compute it with `logaddexp(0, ·)` for stability. The gradient is taken at the `w` stored in the file, not at zeros.
- Use the `.npz` `init` vector as the RNN initial state when it exists (it may be non-zero in another instance); return every hidden state, not just the last.
- The MLP has no softmax: output is the raw second-layer logits.
- Do not enable `jax_enable_x64` or cast to float64; inputs are float32 and outputs should stay float32.
- Save with `np.save(path, np.asarray(x))` so the file is a plain `.npy` (no pickle); load `.npz` with `np.load` and convert to `jnp`.

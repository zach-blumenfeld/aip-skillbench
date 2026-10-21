# Source and provenance: jax-array-tasks

## Provenance

`source/jax-skills/` holds verbatim copies of the curated skill set `jax-skills`:

- `SKILL.md`: function catalog (load, save, map_op, reduce_op, logistic_grad, rnn_scan, jit_run), output requirements, best practices, example workflow
- `jax_skills.py`: reference implementation of those functions
- `jax_load.skill`, `jax_save.skill`, `jax_map.skill`, `jax_reduce.skill`, `jax_grad.skill`, `jax_scan.skill`, `jax_jit.skill`: one YAML-like interface spec per function (inputs, outputs, implementation pointer)

Task context, read but not copied (it is task input, not skill material): `instruction.md` (problem.json schema: id/description/input/output) and the environment Dockerfile (Ubuntu 24.04, python3, jax/jaxlib 0.8.2, numpy 2.4.1; files under /app). The environment's `generate_data.py` and `problem.json` confirmed the conventions the skill uses (row = axis 1, labels from `sign`, `init` used as h0, ReLU MLP with linear output). Its `reference/` outputs are used only as a check by `verify` and never as answers.

## Intent

A downstream agent gets a problem.json with several small JAX tasks. The skill turns each description into a typed plan entry, computes it with a tested JAX implementation, saves a plain float32 `.npy`, and cross-checks it against an independent NumPy recompute (and a reference folder when one exists). Anything the scripted ops can't express is handed to the agent as a client task, with helper functions.

## Component-kind choices

| Component | Kind | Why |
|---|---|---|
| 1. Inspect tasks and input arrays | execution (`jax_tasks.py inspect`) | Reading files, listing keys/shapes, and resolving paths is deterministic. It gathers the information the decision needs, so the decision isn't made blind. |
| 2. Classify each task (`operation`, `reduce_axis`, `fn`) | decision (choice ×3) | Mapping a natural-language description to an op and axis is a judgment, but the answer space is fixed (the ops the library supports, plus `other`). The keyword `suggested_op` is only a hint because keyword rules break on wording like "sum of squares". |
| 3. Validate plan, compute, save, cross-check | execution (`jax_tasks.py run`) | The op math (vmap map, reduce, jax.grad of the logaddexp loss, lax.scan RNN, jitted MLP), key aliasing, weight-orientation detection, and plan validation are all code. |
| 4. Tasks outside the op set | client_task | Needs new JAX code written by the agent. Helpers (`load`/`save`) are importable from the script. |
| 5. Verify all outputs | execution (`jax_tasks.py verify`) | Existence, loadability, finiteness, and numeric comparison are deterministic. It also covers client-task outputs. |

All logic lives in one script with three subcommands, because inspect, run, and verify share the loaders and ops.

## Completeness check: source item → where it lives

| Source item | Location in skill |
|---|---|
| `load(path)`: .npz → dict, .npy → jnp array | `jax_tasks.load` (also .json); step 4 snippet |
| `save(data, path)` → np.save(np.array) | `jax_tasks.save`; Gotchas (plain .npy) |
| `map_op` square via `jax.vmap(lambda x: x*x)`; ValueError on unknown op | `map_op` (square = `x*x` under vmap, more fns added); plan validation rejects unknown fn |
| `reduce_op` mean over axis; unknown op error | `reduce_op` (mean plus sum/max/min/prod/std/var); validation; `reduce_axis` decision |
| `logistic_grad`: jax.grad of mean(logaddexp(0, -y·x@w)) | `logistic_grad`; op table; Gotchas |
| Logistic loss formula `mean(log(1+exp(-y*(x@w))))` | op table, Gotchas |
| `rnn_scan`: step tanh(Wx@x + Wh@h + b), h0 zeros(Wh.shape[0]), lax.scan, return hseq | `rnn_scan`. h0 = npz `init` if present, else zeros (matches the environment oracle). Returns all states. |
| `jit_run(fn, args)` = jax.jit(fn)(*args) | `mlp` is jax.jit-compiled; map/logistic use `jax.jit`; step 4 snippet uses `jax.jit` |
| .skill interface specs (inputs/outputs per function) | op table and plan fields (canonical names x,y,w / seq,Wx,Wh,b / X,W1,b1,W2,b2) |
| Arrays must be jnp-compatible / convertible from lists | `load` converts to jnp; json lists accepted |
| Save as .npy/.npz/JSON/pickle | Narrowed to plain .npy, because the task outputs are `.npy` paths (see drops) |
| Validate input types and shapes | `_rnn_orient`/`_orient_w` shape checks, reduce axis range check, key presence check; step 4 "check input shapes" |
| Maintain numerical stability | logaddexp; step 4 note on `jnp.logaddexp`/`jax.nn`; NaN/Inf detection in run/verify |
| Meaningful error messages for unsupported ops / invalid input | PLAN INVALID listing, key-not-found message naming available keys, axis-range error |
| Prefer jnp arrays; convert to NumPy only when saving | `load` returns jnp; `save` converts; step 4 snippet |
| Avoid side effects inside vmap/scan | step 4 "write the function pure" |
| Validate shapes for map_op, reduce_op, rnn_scan | as above |
| Use JIT for compute-heavy functions | jit in run; step 4 |
| JIT note: input shapes must be consistent across calls | Each task jits once on fixed shapes, so the note has no separate action |
| Example workflow (load → map → reduce → grad → scan → save) | Procedure steps 1–5 |
| Avoid unnecessary NumPy conversions | covered by "prefer jnp" behavior in `load`/ops |

## Deliberate drops

- `license: Proprietary. LICENSE.txt has complete terms`: frontmatter metadata of the source collection. No LICENSE.txt was supplied, and the field isn't actionable for the task.
- Pickle/JSON as output formats: the task's outputs are `.npy` paths and graders load them with `np.load`. Pickle would also need `allow_pickle`. JSON input loading is kept.
- The source example `reduce_op(arr, "mean", axis=0)` with no task context: kept only as a Gotcha warning, because copying it would compute column means when the task asks for "mean of each row".
- Descriptive notes ("designed for scientific computing, ML prototyping", "emphasizes JAX-native operations", "speeds up repeated calls"): background with no action.
- `jit_run` as a general wrapper taking an arbitrary callable: not an op by itself. Its behavior (jax.jit then call) is applied inside the scripted ops and in the client-task snippet.

## Additions beyond the source (from the task environment)

- RNN `init` key used as h0 when present, plus `use_init` override. Non-square `Wx` orientation is detected from shapes.
- MLP op (ReLU hidden, linear output, jitted): the source has `jit_run` but no MLP, and the task requires one.
- Key aliasing and `keys`/`array_key` overrides, so other instances with renamed arrays work.
- {0,1}-label warning and `y_transform: pm1`.
- NumPy cross-check and reference comparison.

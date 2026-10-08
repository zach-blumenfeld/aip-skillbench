# Source and provenance: jax-array-tasks

## Provenance

Compiled from the curated Agent Skill `jax-skills`. All of it is copied verbatim into `source/jax-skills/`:

| file | content |
|---|---|
| `SKILL.md` | Freeform skill: output requirements, the 7-function API, best practices, example workflow, notes |
| `jax_skills.py` | Reference implementations: `load`, `save`, `map_op`, `reduce_op`, `logistic_grad`, `rnn_scan`, `jit_run` |
| `jax_load.skill`, `jax_save.skill`, `jax_map.skill`, `jax_reduce.skill`, `jax_grad.skill`, `jax_scan.skill`, `jax_jit.skill` | One mini-manifest per function (name, description, typed inputs/outputs, implementation pointer) |

The task environment it was built for (Dockerfile: Ubuntu 24.04, python3, `jax==0.8.2`, `jaxlib==0.8.2`,
`numpy==2.4.1`) holds a `problem.json` list of `{id, description, input, output}` tasks over `.npy`/`.npz`
files. The seven curated skills describe one workflow: load, then transform (map / reduce / grad / scan / jit),
then save. They are compiled into a single graph that runs every task in the spec.

## Intent

Given a problem spec, compute each task with JAX and save it as `.npy`, getting the semantic details right
(axis wording, label encoding, initial RNN state, weight orientation, MLP layout). Every number comes from
the input files; nothing is hardcoded.

## Graph and step-kind choices

```
survey (execution) -> review-plan (decision) -> plan-gate (router)
     true  -> compute (execution) -> result-gate (router) -> true -> end
     false -> fix-plan (client_task) -> compute              false -> fix-plan
```

| step | kind | why |
|---|---|---|
| `survey` | execution | Reading the spec, resolving paths, listing npz keys/shapes/dtypes/label values, and mapping wording to op + params ("each row" -> axis 1, `{0,1}` labels -> `2y-1`, `init` -> h0, shape-based weight orientation) are deterministic rules over structured input. NumPy only, so it is fast. |
| `review-plan` | decision (noul `plan_ok`, threshold 0.2) | Whether a proposed op actually matches free-text task wording is a judgment, but the answer space is yes/no. The checklist of known pitfalls lives in the question's instructions. The threshold is low-ish because computing a misread task silently gives a wrong file. |
| `plan-gate`, `result-gate` | router | Branch on `plan_ok` / `all_ok`. |
| `fix-plan` | client_task | Repairing a plan entry (choosing keys, axis, orientation, or flagging an unsupported op) needs the agent to write a corrected structure. It loads `references/jax-ops.md` and the op catalog `assets/ops.json`. |
| `compute` | execution | The JAX math itself: deterministic. One script runs all tasks; it checks shape and finiteness, saves with `np.save`, and re-reads the file. Errors are reported per task, so the loop back to `fix-plan` carries exact messages. |
| `end` | end | `results` (per-task saved path, shape, dtype, preview) and `all_ok`. |

Two scripts instead of one: `survey` must not pay the JAX import cost or crash if JAX is missing before the
plan is reviewed, and `compute` is rerun on its own in the repair loop.

## Supporting files

- `scripts/survey.py`: spec loading, file inspection, op/param proposal.
- `scripts/compute.py`: the JAX implementations, adapted from `jax_skills.py` (same math; ops extended,
  see below), plus validation and saving.
- `assets/ops.json`: op catalog and keyword vocab, shared by survey (via stdin assets) and the fix-plan template.
- `assets/fix_plan.md`: fix-plan template.
- `references/jax-ops.md`: original API table, plan entry schema, interpretation rules.

## Completeness check (source -> body)

| source item | where it lives now |
|---|---|
| Arrays must be JAX-compatible (`jnp.array`) | compute.py `load()` -> `jnp.asarray`; anti-pattern "Converting to NumPy mid-computation" |
| Save as `.npy`/`.npz`/JSON/pickle | Task outputs are `.npy`, so compute saves `.npy` via `np.save`; survey flags non-`.npy` output names. JSON/pickle: see drops |
| Validate input types and shapes | compute.py `need(...)` checks per op (x 2-D, y length, w shape, Wh square, b/h0 shape, Wx fit, axis range) plus expected output shape |
| Maintain numerical stability | `logaddexp(0, -y*z)` in compute.py; anti-pattern; jax-ops.md rule; NaN/Inf check on every result |
| Meaningful errors for unsupported ops / invalid inputs | per-task `error` strings listing the supported values; the result-gate loop surfaces them |
| `load(path)`: `.npz` -> dict, `.npy` -> array | compute.py `load()`; survey `describe()`; jax-ops.md table |
| `save(data, path)` -> `np.save(path, np.array(data))` | compute.py `run_one` (`np.save` of `np.asarray`), reload check; jax-ops.md |
| `map_op(array, "square")` via `jax.vmap(lambda x: x*x)` | compute.py `op_map` (`MAP_FUNCS["square"] = v*v`, `jax.vmap`) |
| `reduce_op(array, "mean", axis)` via `jnp.mean` | compute.py `op_reduce` |
| Unknown op -> `ValueError` | compute.py `need(op in OPS / func in ...)` -> per-task error |
| `logistic_grad`: `jax.grad` of `mean(log(1+exp(-y*(x@w))))` | compute.py `op_logistic_grad`; compute step description; jax-ops.md |
| `rnn_scan`: `lax.scan`, `tanh(Wx@x + Wh@h + b)`, h0 = zeros(Wh.shape[0]), returns all hidden states | compute.py `op_rnn_scan` (zeros when no h0 key; uses file's `init` when present, as the task data provides one); review-plan question; anti-pattern |
| `jit_run(fn, args)` -> `jax.jit(fn)(*args)` | every compute op is wrapped in `jax.jit`; MLP explicitly `jax.jit(mlp)` |
| JIT: speeds repeated calls; input shapes must be consistent | jax-ops.md "JIT" rule |
| `.skill` manifests: typed inputs/outputs per function | plan params per op (`references/jax-ops.md` table, `assets/ops.json`) |
| Best practice: prefer `jnp`, convert to NumPy only when saving | anti-pattern; compute.py converts only at save |
| Best practice: avoid side effects in vmap/scan fns | anti-pattern; jax-ops.md |
| Best practice: validate shapes for map/reduce/scan | compute.py checks |
| Best practice: use JIT for compute-heavy functions | compute.py jits every op |
| Best practice: save as `.npy` or pickle/json | see Save row |
| Example workflow (load -> map -> reduce -> grad -> scan -> save) | the survey -> compute graph; ops are in the same order in compute.py |
| Example `reduce_op(arr2, "mean", axis=0)` | Deliberately not copied as a default: wording decides the axis ("each row" -> 1). Recorded as an anti-pattern and a jax-ops.md rule |
| Description keywords (array ops, autodiff, JIT, scans, map/reduce, gradients) | frontmatter `description` |
| `license` | frontmatter `license` |

### Knowledge added beyond the curated source (from the task environment)

- 2-layer MLP: `relu(x@W1+b1)@W2+b2`, output layer linear, jitted (the source has only generic `jit_run`).
- Row/column/per-sample axis wording, label `{0,1}` -> `{-1,+1}`, RNN `init` carry, shape-based weight orientation.
  When `Wx` is stored `(in, hidden)` both matrices use the row-vector convention (`x @ Wx + h @ Wh`); a
  fresh-agent test caught the survey mixing conventions, which is now fixed in survey.py, review-plan, and jax-ops.md.
- Problem-spec handling: relative input paths resolve against the spec's folder; bare output names go into `output_dir`.
- Extra map funcs (abs, exp, log, sqrt, tanh, relu, sigmoid, negative, sin, cos) and reduce funcs (sum, max,
  min, prod, std, var, median), so wording variants do not fall into the repair loop.

## Deliberate-drop log

| dropped | rationale |
|---|---|
| Saving to JSON or pickle | Tasks name `.npy` outputs and the original `save()` only writes `.npy`. Pickle loading is also disabled (`allow_pickle=False`) for safety. |
| "Convertible from Python lists" | Inputs are always NumPy files here; inline lists can be passed in a plan only via a file. |
| `jit_run` as a general "run any callable" step | A JSON state cannot carry a callable. JIT is applied inside every compute op instead. |
| Note "designed for scientific computing, ML prototyping, dynamic array transformations" | Background; covered by `description`. |
| "Emphasizes JAX-native ops, autodiff, JIT" | Background, already reflected in the implementation. |
| `import jax_skills as jx` usage snippets | Calling convention of a module the pack does not expose. Same math lives in compute.py. |

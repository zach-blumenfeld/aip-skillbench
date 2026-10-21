# Source and compilation notes for `jax-task-solver`

## Provenance

`jax-skills/` is a verbatim copy of the curated skill this AIP skill was compiled from:

| File | What it is |
|---|---|
| `jax-skills/SKILL.md` | Freeform skill: output requirements, the `jax_skills` API (load, save, map_op, reduce_op, logistic_grad, rnn_scan, jit_run), best practices, an example workflow |
| `jax-skills/jax_skills.py` | Reference implementation of that API |
| `jax-skills/jax_{load,save,map,reduce,grad,scan,jit}.skill` | One-op manifests: name, description, typed inputs/outputs, implementation pointer into `jax_skills.py` |

The target task (instruction.md): a `problem.json` lists tasks (`id`, `description`,
`input` .npy/.npz, `output` .npy); every task must be computed with JAX and saved.
In the container, `problem.json`, `data/`, and outputs sit under `/app` (WORKDIR), with
jax/jaxlib 0.8.2 and numpy 2.4.1 on Ubuntu 24.04's python3 (3.12).

## Intent

One procedure that handles a whole problem.json: a deterministic script proposes the
op for each task, the agent confirms it against the wording, a script computes and
saves everything the catalog covers, and the agent writes JAX code only for what is left.

## Component-kind choices

| Step | Kind | Why |
|---|---|---|
| `inspect` | execution | Reading JSON, resolving paths, listing npz keys/shapes, keyword-matching descriptions to ops, and mapping npz keys to roles are all deterministic. |
| `plan` | client_task | Interpreting a free-text task description against the catalog is judgment over a *list* of tasks; a decision step answers questions about a single input and cannot return a per-task structured plan. The script's suggestion is the default, so the agent only corrects it. |
| `compute` | execution | The math (vmap map, reduce, jax.grad logistic loss, lax.scan RNN, jitted MLP) is fixed code in `scripts/jax_skills.py`; scripting it keeps it exact and fast. Per-task failures are reported, not raised, so one bad task does not lose the others. |
| `by-status` | router | Branches on the script's `status` (`complete` / `needs_agent`). |
| `finish-remaining` | client_task | Tasks outside the catalog need generated code. |

Scripts: `jax_skills.py` (shared library, adapted from the source), `inspect_tasks.py`,
`run_tasks.py`. The two execution steps get separate entry scripts because each must
print exactly its own declared outputs.

## Mapping source → skill

| Source item | Where it lives now |
|---|---|
| `load(path)`: .npy → array, .npz → dict | `scripts/jax_skills.py::load` (npz values converted to jax arrays); used by `compute` |
| `save(data, path)` → .npy | `jax_skills.py::save` (also creates parent folders) |
| `map_op(array, "square")` via vmap | `jax_skills.py::map_op`; catalog extended (exp, abs, sqrt, …) with the same vmap approach; plan template lists the fns |
| `reduce_op(array, "mean", axis)` | `jax_skills.py::reduce_op`; catalog extended (sum, max, std, …); axis wording rules in inspect script, plan template, reference, anti-pattern |
| `logistic_grad`: jax.grad of mean(log(1+exp(-y·(x@w)))) | `jax_skills.py::logistic_grad` (logaddexp form, same as source code); formula in plan template and reference |
| `rnn_scan`: lax.scan, tanh, returns hidden-state sequence | `jax_skills.py::rnn_scan`; "return all states" in reference and anti-patterns |
| `jit_run(fn, args)`; notes on speed and consistent shapes | `jax_skills.py::jit_run`, used by `mlp`; shape note in reference |
| Requirements: arrays JAX-compatible / list-convertible | reference "Requirements" |
| Save as .npy/.npz/JSON/pickle | reference (save .npy at the task's exact output path; others only if the path asks) |
| Validate input types and shapes | shape checks in every library op; inspect lists shapes; reference |
| Numerical stability | logaddexp in logistic loss; anti-pattern; reference |
| Meaningful error messages | library ops raise messages naming the array and shape; `compute` reports them per task; custom template tells the agent to read them |
| Best practice: prefer jnp, convert to NumPy only when saving | library design; anti-pattern; reference; custom template |
| Best practice: no side effects in vmap/scan | reference; custom template |
| Best practice: validate shapes for map/reduce/scan | library ops |
| Best practice: JIT compute-heavy functions | `mlp` runs under `jax.jit`; reference |
| Note: scientific computing / ML prototyping scope | frontmatter description, purpose |
| `.skill` manifests (typed inputs/outputs per op) | one library function each; inputs/outputs carried by the function signatures and the plan template's `args` schema |

## Additions beyond the source (from the task's own conventions)

- **RNN initial state.** The source `rnn_scan` always starts from zeros. Task npz files
  can carry an initial state (`init`); the procedure uses it when present and zeros only
  when absent. The source's zero start is the fallback.
- **2-layer MLP under jit.** The source has only `jit_run`. Added `mlp` (relu between
  layers, linear output, any depth W1..Wn/b1..bn) since "implement and JIT compile an MLP"
  is a task type.
- **Path resolution.** problem.json paths are relative to its own folder; scripts run
  from the skill's scripts/ folder, so the inspect script makes every path absolute.
- **Fallback for anything else.** A `custom` op and the `finish-remaining` step cover
  descriptions outside the catalog (e.g. softmax, other losses) and per-task errors.

## Deliberate drops

| Dropped | Rationale |
|---|---|
| `license: Proprietary. LICENSE.txt has complete terms` | No LICENSE.txt was supplied with the source; the line is kept in the verbatim copy here, but the compiled skill does not claim a license file it does not ship. |
| Example Workflow code block (load → square → mean → grad → scan → save) | Redundant: the procedure itself runs that pipeline per task, and each call is in `jax_skills.py`. |
| `.skill` manifest `name`/`description` strings | Redundant with the library function names and docstrings. |
| The source's unknown-op `ValueError("Unknown op")` wording | Replaced by messages listing the supported ops (same behaviour, more useful). |

# jax-skills (AIP) — source notes

## Origin

Curated from the SkillsBench task `jax-computing-basics` skill at
`vendor/skillsbench/tasks/jax-computing-basics/environment/skills/jax-skills/`.

The original skill ships:

- A `SKILL.md` (Anthropic Agent Skill format) describing seven primitive ops.
- `jax_skills.py` — the Python module implementing those ops.
- Per-op `.skill` files declaring inputs/outputs in a custom YAML schema.

This AIP rewrite preserves all of that material and adds an end-to-end
solver script that pins the deterministic dispatch from `problem.json` task
ids to concrete operations.

## Schema choice

The procedure schema (`procedure.schema.json`, v0.3a3) fits because the
skill encodes a multi-step workflow: parse `problem.json`, dispatch each
subtask to a typed JAX operation, save the result. Steps are
script-backed where the logic is deterministic.

No other AIP schema in the bundled set (only `procedure.schema.json` is
available) is more specific to library-API-usage skills, and procedures
already model script-graph execution cleanly.

## What is scripted vs left to the agent

Scripted (`scripts/solve_problems.py`):

- `id -> operation` dispatch table over the closed set of subtask ids
  (`basic_reduce`, `map_square`, `grad_logistic`, `scan_rnn`, `jit_mlp`).
  This is a deterministic lookup over structured input.
- `.npz` key unpacking for each op (which arrays to pull out and in
  what positional order).
- The 2-layer MLP definition (`relu(X @ W1 + b1) @ W2 + b2`) that
  `jit_mlp` needs, since `jax_skills.jit_run` is generic.

Left to the agent (prose):

- Reading the task instruction and confirming `problem.json` matches the
  expected schema (`id`, `description`, `input`, `output`).
- Falling back to the lower-level `jax_skills` primitives if the
  benchmark introduces a new subtask id that the dispatch table does not
  cover.

## Files

- `procedure.schema.json` — AIP procedure schema this skill validates against.
- `ORIGINAL_SKILL.md` — verbatim copy of the original Anthropic Agent Skill markdown.
- `jax_grad.skill`, `jax_jit.skill`, `jax_load.skill`, `jax_map.skill`,
  `jax_reduce.skill`, `jax_save.skill`, `jax_scan.skill` — per-op
  inputs/outputs declarations from the original skill, kept verbatim as
  reference for the toolkit's API contract.

## Completeness check

Every line of the original `SKILL.md` is mapped into the AIP body:

| Original section                | AIP body location                              |
|---------------------------------|------------------------------------------------|
| Array compatibility rules       | `anti_patterns` + `scope_and_approval`         |
| Operation validation rules      | `anti_patterns`                                |
| `load(path)`                    | step `read-input`                              |
| `save(data, path)`              | step `save-output`                             |
| `map_op(array, op)`             | step `compute` -> `one_of: map-square`         |
| `reduce_op(array, op, axis)`    | step `compute` -> `one_of: basic-reduce`       |
| `logistic_grad(x, y, w)`        | step `compute` -> `one_of: grad-logistic`      |
| `rnn_scan(seq, Wx, Wh, b)`      | step `compute` -> `one_of: scan-rnn`           |
| `jit_run(fn, args)`             | step `compute` -> `one_of: jit-mlp`            |
| Best practices                  | `anti_patterns`                                |
| Example workflow                | `scenarios`                                    |
| Notes on JAX-native ops         | `purpose`                                      |

The toolkit itself (`scripts/jax_skills.py`) is the implementation source
of truth for the operations.

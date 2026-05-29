# yaml-config — AIP conversion notes

## Source
`original-SKILL.md` is the curated SkillsBench skill verbatim from
`vendor/skillsbench/tasks/adaptive-cruise-control/environment/skills/yaml-config/SKILL.md`.

It documents Python YAML I/O patterns the agent should follow when loading
`vehicle_params.yaml` and writing `tuning_results.yaml` in the Adaptive Cruise
Control task.

## Schema choice
`procedure.schema.json` — this is a structured procedure for reading and
writing YAML config files. Each rule (safe_load, error handling, dump options,
merge-with-defaults) maps cleanly onto a step with inputs/outputs.

## Script vs prose vs assets
The skill is consumed by an agent that **writes its own Python code** (e.g.,
`simulation.py`, a tuning script). The agent does not invoke this skill at
runtime — it adapts the patterns into its own files.

That makes `assets/` the right home for the code patterns, not `scripts/`:

- `assets/read_yaml.py` — safe-read template (`yaml.safe_load`, error handling).
- `assets/write_yaml.py` — safe-write template (`default_flow_style=False`,
  `sort_keys=False`).
- `assets/load_with_defaults.py` — optional-config loader with shallow merge.

The steps in `SKILL.md` are prose nodes that point at these templates; there
is no `scripts/` because no step's logic is a deterministic transform the
skill itself needs to execute on structured inputs.

## Source-to-body mapping
Every distinct piece of `original-SKILL.md` is captured below.

| Source content | Where it landed |
|----------------|-----------------|
| `yaml.safe_load` usage | `safe-read` step + `assets/read_yaml.py` + anti-pattern on `yaml.load` |
| Nested access example (`config['section']['key']`) | implied by `safe-read` outputs (nested dict); not re-stated — adds no agent value |
| `yaml.dump` with `default_flow_style=False`, `sort_keys=False` | `safe-write` step + `assets/write_yaml.py` |
| `allow_unicode=True` option | `safe-write` step description + `write_yaml.py` parameter |
| `try/except FileNotFoundError / yaml.YAMLError` block | `handle-errors` step + `assets/read_yaml.py::read_yaml_or_default` |
| `load_config(filepath, defaults)` helper with shallow merge | `merge-with-defaults` step + `assets/load_with_defaults.py` |

Nothing from the original was dropped. The nested-access example is
captured by the output `type: object` on `safe-read`, which is sufficient.

## Notable additions over the original
- Anti-pattern list (sort_keys, empty-file None, uncaught errors) — derived
  from the same rules already in the original, just made explicit.
- `load_with_defaults.py` callouts that the merge is shallow — important
  because the ACC task's configs are nested (`pid_speed.kp`, etc.). The
  original is silent on this and would mislead an agent who copy-pastes it
  for nested merging.

# yaml-config — AIP compile notes

## Source

Curated Agent Skill at
`vendor/skillsbench/tasks/adaptive-cruise-control/environment/skills/yaml-config/SKILL.md`.

The original skill is a four-snippet patterns doc covering: `safe_load` for
reads, block-style writes with preserved key order, FileNotFoundError /
YAMLError handling, and an "optional config with defaults" merge pattern.

## Schema choice

`procedure.schema.json` from `aip-schemas/`. The skill is small but the work
it guides is procedural — pick an operation (read / write / load-with-defaults),
call the right helper, fall back appropriately on errors. Procedure is the
only published v0.3a2 schema and the natural fit; no new schema was authored.

## Body design

The four source snippets all reduce to two helpers and one error-handling
policy. Rather than ask the agent to retype `yaml.safe_load` + try/except
boilerplate at every call site (where it tends to drift: `yaml.load`, missing
`sort_keys=False`, silent except), they live in `scripts/yaml_io.py`:

- `safe_load_yaml(path)` — raw read; raises on missing file or parse error.
- `load_config(path, defaults)` — read-with-fallback; matches the source
  "optional config loading" pattern exactly.
- `safe_dump_yaml(data, path)` — write with `default_flow_style=False`,
  `sort_keys=False`, `allow_unicode=True` baked in.

The script is also CLI-callable so a step can shell out when an importable
runtime isn't available.

The SKILL.md body keeps three script-backed steps (`read-yaml`,
`load-with-defaults`, `write-yaml`) and an `anti_patterns` list that calls
out the specific footguns the source snippets were teaching against
(`yaml.load`, flow style, key sorting, silent FileNotFoundError).

## Source-content classification

| Source content                                  | Disposition  | Where                                           |
|-------------------------------------------------|--------------|-------------------------------------------------|
| `yaml.safe_load` for reads                      | Mapped       | `read-yaml` step + script + anti-patterns       |
| Nested access (`config['section']['key']`)      | Deliberate drop | Generic Python; nothing skill-specific to add |
| `default_flow_style=False`, `sort_keys=False`   | Mapped       | Baked into `safe_dump_yaml`; called out in step |
| `allow_unicode=True` option                     | Mapped       | Default in `safe_dump_yaml`                     |
| try/except FileNotFoundError → defaults         | Mapped       | `load_config` script                            |
| try/except YAMLError → defaults                 | Mapped       | `load_config` script (with stderr log)          |
| `load_config(filepath, defaults)` helper        | Mapped       | `load_config` script + `load-with-defaults` step |

No source content dropped silently.

## Compatibility

The host environment (Dockerfile at
`vendor/skillsbench/tasks/adaptive-cruise-control/environment/Dockerfile`)
already provides Python 3 and PyYAML, since the task itself reads
`vehicle_params.yaml` and writes `tuning_results.yaml`. No additional
dependencies introduced.

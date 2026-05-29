---
name: yaml-config
description: Use this skill when reading or writing YAML configuration files in Python — loading vehicle parameters (vehicle_params.yaml), writing tuned PID gains (tuning_results.yaml), handling missing or malformed config files, or merging an optional config over defaults. Enforces yaml.safe_load over yaml.load, block-style dumps with stable key order, and explicit error handling for FileNotFoundError and yaml.YAMLError.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a3
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a3/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Patterns for reading and writing YAML configuration files in Python. Always
  use yaml.safe_load (never yaml.load — it allows arbitrary code execution),
  dump in block style with stable key order, handle FileNotFoundError and
  yaml.YAMLError explicitly, and merge optional configs over defaults so
  missing keys fall back cleanly. Code templates live under assets/ — copy
  and adapt them into the task's own .py files (e.g., simulation.py, a tuning
  script that emits tuning_results.yaml).

trigger_when:
  - Reading a YAML config file in Python (e.g., vehicle_params.yaml, tuning_results.yaml).
  - Writing a Python dict to a YAML file (e.g., saving tuned PID gains).
  - Loading an optional config that may not exist yet; need defaults as fallback.
  - Handling YAML parse errors or missing config files without crashing.
  - Choosing yaml.dump options for human-readable, diff-friendly output.

do_not_use_when:
  - The file format is JSON, TOML, or INI — different libraries and conventions.
  - The data is CSV or tabular — see csv-processing.

steps:
  - name: safe-read
    description: >
      Open the file and parse with yaml.safe_load. Coerce the result with `or {}`
      so an empty file becomes {} instead of None. Returns the parsed dict
      (nested dicts preserved). Template at assets/read_yaml.py.
    inputs:
      - name: path
        type: string
        description: Path to the YAML file to read.
    outputs:
      - name: config
        type: object
        description: Parsed YAML contents as a (possibly nested) Python dict.

  - name: handle-errors
    description: >
      Wrap reads in try/except when the file may be missing or malformed.
      Catch FileNotFoundError (config absent) and yaml.YAMLError (parse failed).
      For required configs, re-raise or exit; for optional configs, fall back
      to defaults. Template at assets/read_yaml.py (`read_yaml_or_default`).
    inputs:
      - name: path
        type: string
      - name: defaults
        type: object
        nullable: true
        description: Optional fallback dict to return when the file is missing or unparseable.
    outputs:
      - name: config
        type: object

  - name: merge-with-defaults
    description: >
      For optional configs (e.g., tuning_results.yaml before tuning has run):
      load the file (or {} when missing) and shallow-merge over a defaults dict
      so loaded keys overwrite defaults and unset keys fall through. Template at
      assets/load_with_defaults.py. NOTE the merge is shallow — for nested keys
      like `pid_speed.kp` you must recurse manually or replace the whole inner
      dict.
    inputs:
      - name: path
        type: string
      - name: defaults
        type: object
        description: Fallback values. Loaded file overwrites these at the top level.
    outputs:
      - name: merged-config
        type: object

  - name: safe-write
    description: >
      Dump a Python dict with yaml.dump using `default_flow_style=False` (block
      style — readable, diff-friendly), `sort_keys=False` (preserve insertion
      order so the output matches the expected structure), and
      `allow_unicode=True` only when the data contains non-ASCII characters.
      Template at assets/write_yaml.py.
    inputs:
      - name: data
        type: object
        description: Python dict (may be nested) to serialize.
      - name: path
        type: string
        description: Output file path.
    outputs:
      - name: written-path
        type: string

scenarios:
  - need: Load vehicle_params.yaml to access acc_settings.set_speed, vehicle.mass, etc.
    action: Apply `safe-read` with path='vehicle_params.yaml'. Access nested values via `config['acc_settings']['set_speed']`.
    outcome: Nested dict ready for the AdaptiveCruiseControl constructor.

  - need: Write tuning_results.yaml after auto-tuning PID gains for speed and distance loops.
    action: "Build the dict {'pid_speed': {'kp': ..., 'ki': ..., 'kd': ...}, 'pid_distance': {...}}, then apply `safe-write`. `sort_keys=False` preserves the pid_speed/pid_distance order the task expects."
    outcome: tuning_results.yaml on disk, ready for simulation.py to load at runtime.

  - need: simulation.py needs to load tuned PID gains, but the tuning step may not have run yet.
    action: Apply `merge-with-defaults` with path='tuning_results.yaml' and defaults pulled from vehicle_params.yaml's `pid_speed` / `pid_distance` blocks. Remember the merge is shallow — supply complete inner dicts in defaults.
    outcome: Simulation runs with tuned gains if available, baseline gains otherwise.

anti_patterns:
  - Using yaml.load instead of yaml.safe_load — allows arbitrary code execution from untrusted YAML.
  - Calling yaml.dump without default_flow_style=False — produces inline JSON-like output that's hard to read and review in diffs.
  - Omitting sort_keys=False on yaml.dump — the default sorts keys alphabetically, scrambling the expected pid_speed/pid_distance ordering.
  - Letting yaml.safe_load return None for an empty file — always coerce via `loaded or {}` before treating it as a dict.
  - Letting FileNotFoundError or yaml.YAMLError bubble up uncaught when the config is optional (e.g., tuning_results.yaml before tuning ran).
  - Using dict.update for nested config merges — it's shallow; nested dicts like `pid_speed` will be wholly replaced, not merged key-by-key.
```

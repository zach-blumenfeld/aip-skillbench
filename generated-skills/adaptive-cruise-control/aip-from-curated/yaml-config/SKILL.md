---
name: yaml-config
description: Use this skill when reading or writing YAML configuration files, loading vehicle parameters, or handling config file parsing with proper error handling.
compatibility: Requires Python 3 with PyYAML.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a2/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Safely read and write YAML configuration files in this project — including
  vehicle_params.yaml and tuning_results.yaml. Wraps three patterns the agent
  must not get wrong: yaml.safe_load on every read (never yaml.load), block
  style with preserved key order on every write, and a defaults-merge fallback
  for optional config files.

trigger_when:
  - Loading vehicle_params.yaml or any other YAML config file.
  - Writing tuning_results.yaml or any other YAML output the task requires.
  - Parsing user-supplied YAML where missing-file or parse errors must not crash.
  - About to call yaml.load, yaml.dump, or open() on a .yaml/.yml path.

do_not_use_when:
  - Reading or writing JSON, TOML, INI, or CSV files.
  - The data lives in a Python literal and never touches disk.

steps:
  - name: read-yaml
    description: >
      Read a YAML file using yaml.safe_load. Returns the parsed object (usually
      a dict). Use when the file is required and a missing file or parse error
      should propagate. For optional config with fallback, use load-with-defaults
      instead.
    script: scripts/yaml_io.py
    inputs:
      - name: path
        type: string
        description: Path to the YAML file.
    outputs:
      - name: config
        type: object
        description: Parsed YAML content.

  - name: load-with-defaults
    description: >
      Load a YAML config file with a defaults fallback. Missing file or parse
      error returns a copy of defaults; on success, loaded keys shallow-merge
      over defaults so explicit YAML wins. Use for optional config files where
      the program should keep running with sensible defaults.
    script: scripts/yaml_io.py
    inputs:
      - name: path
        type: string
      - name: defaults
        type: object
        nullable: true
        description: Default values; returned as-is when the file is missing or unparseable.
    outputs:
      - name: config
        type: object

  - name: write-yaml
    description: >
      Serialize a dict to a YAML file using block style with preserved key
      order (default_flow_style=False, sort_keys=False, allow_unicode=True).
      These options are not optional for this project — downstream consumers
      depend on key order and on readable block formatting.
    script: scripts/yaml_io.py
    inputs:
      - name: path
        type: string
      - name: data
        type: object
        description: Mapping to serialize.
    outputs:
      - name: path
        type: string
        description: The path written.

scenarios:
  - need: Load vehicle parameters at the top of acc_system.py.
    action: Call load_config('vehicle_params.yaml') from scripts/yaml_io.py (no defaults — the file is required).
    outcome: Nested dict accessed as config['acc_settings']['set_speed'], etc.

  - need: Read PID gains from tuning_results.yaml at the start of simulation.py.
    action: safe_load_yaml('tuning_results.yaml').
    outcome: Dict with pid_speed and pid_distance sub-mappings, each holding kp/ki/kd.

  - need: Write tuning_results.yaml after PID tuning completes.
    context: Downstream simulation.py reads keys by name and expects the documented order (pid_speed before pid_distance, kp before ki before kd).
    action: "safe_dump_yaml({'pid_speed': {...}, 'pid_distance': {...}}, 'tuning_results.yaml')."
    outcome: Block-style YAML with keys in insertion order; no flow-style braces, no alphabetical reordering.

anti_patterns:
  - "Calling yaml.load instead of yaml.safe_load — allows arbitrary object construction from untrusted input."
  - "Omitting default_flow_style=False — yaml.dump emits inline mappings like {a: 1, b: 2} for short dicts, which is harder to diff and reads as a JSON-ish blob."
  - "Omitting sort_keys=False — alphabetical key reordering breaks readers that expect documented order (e.g. pid_speed before pid_distance)."
  - "Catching FileNotFoundError and silently returning an empty dict when the caller actually requires the file — hides missing-config bugs. Use load-with-defaults only when defaults are intended."
  - "Swallowing yaml.YAMLError without logging — parse errors disappear into an empty dict and the program runs on stale assumptions."
```

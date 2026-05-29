"""Template: safely write a Python dict to a YAML file.

Copy / adapt into your task code (e.g., tuning script that emits
tuning_results.yaml). The skill teaches patterns; this file is a reference
snippet, not an invoked library.

Required dump options:
  - default_flow_style=False  -> block style (human-readable)
  - sort_keys=False           -> preserve insertion order
Optional:
  - allow_unicode=True        -> needed only if data contains non-ASCII text
"""
import yaml


def write_yaml(data, path, allow_unicode=False):
    """Dump `data` to `path` in block style with stable key order."""
    with open(path, "w") as f:
        yaml.dump(
            data,
            f,
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=allow_unicode,
        )


if __name__ == "__main__":
    # Example: write tuning_results.yaml in the exact structure the ACC task expects.
    tuning_results = {
        "pid_speed": {"kp": 0.5, "ki": 0.05, "kd": 0.0},
        "pid_distance": {"kp": 0.3, "ki": 0.02, "kd": 0.0},
    }
    write_yaml(tuning_results, "tuning_results.yaml")

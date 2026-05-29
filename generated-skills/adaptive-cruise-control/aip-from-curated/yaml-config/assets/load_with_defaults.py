"""Template: load an optional YAML file, merging on top of a defaults dict.

Use this pattern when a config file is optional (may not exist yet) and any
missing keys should fall back to defaults. Loaded values OVERWRITE defaults
at the top level.

Note: this is a shallow merge. If you need nested dicts to be merged key-by-key
(e.g., loaded `pid_speed.kp` overrides default `pid_speed.kp` while keeping
default `pid_speed.ki`), recurse manually — yaml.safe_load returns plain dicts
and Python's dict.update is shallow.
"""
import os
import yaml


def load_config(filepath, defaults=None):
    """Load config file, returning `defaults` (merged-under) if missing.

    Args:
        filepath: path to the YAML file.
        defaults: dict of fallback values. Missing keys in the file fall back to these.

    Returns:
        dict with loaded values layered over defaults (shallow merge).
    """
    if defaults is None:
        defaults = {}

    if not os.path.exists(filepath):
        return defaults

    with open(filepath, "r") as f:
        loaded = yaml.safe_load(f) or {}

    result = defaults.copy()
    result.update(loaded)
    return result


if __name__ == "__main__":
    # Example: PID gains with sensible fallbacks if tuning_results.yaml is absent.
    defaults = {
        "pid_speed": {"kp": 0.1, "ki": 0.01, "kd": 0.0},
        "pid_distance": {"kp": 0.1, "ki": 0.01, "kd": 0.0},
    }
    gains = load_config("tuning_results.yaml", defaults)
    print(gains)

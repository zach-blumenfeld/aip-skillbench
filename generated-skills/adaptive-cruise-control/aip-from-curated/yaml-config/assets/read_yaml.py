"""Template: safely read a YAML config file into a Python dict.

Copy / adapt into your task code (e.g., simulation.py). The skill teaches
patterns; this file is a reference snippet, not an invoked library.

Rules enforced:
  - yaml.safe_load (never yaml.load) — prevents arbitrary code execution.
  - Coerce empty-file None into {} via `or {}`.
  - Catch FileNotFoundError and yaml.YAMLError when the config is optional.
"""
import yaml


def read_yaml(path):
    """Read a YAML file and return its contents as a dict.

    Raises FileNotFoundError if the file is missing and yaml.YAMLError
    if the file cannot be parsed. Callers that need fallback behavior
    should wrap this in try/except (see read_yaml_or_default below).
    """
    with open(path, "r") as f:
        return yaml.safe_load(f) or {}


def read_yaml_or_default(path, defaults=None):
    """Read a YAML file, returning `defaults` if the file is missing or unreadable."""
    if defaults is None:
        defaults = {}
    try:
        with open(path, "r") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        return defaults
    except yaml.YAMLError as e:
        print(f"YAML parse error in {path}: {e}")
        return defaults


if __name__ == "__main__":
    import sys

    config = read_yaml(sys.argv[1])
    print(config)

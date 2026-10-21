#!/usr/bin/env python3
"""
Write the bundled parallel_solution.py template to solution_path.

stdin : {"state": {workspace_dir, solution_path}, "assets": {"parallel_solution": <source>}, ...}
stdout: {"installed_path", "installed_bytes"}
"""

import ast
import json
import os
import shutil
import sys


def main():
    payload = json.load(sys.stdin)
    state = payload["state"]
    source = payload.get("assets", {}).get("parallel_solution")
    if not source:
        # Fall back to the file on disk (cwd is this script's folder).
        here = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(here, "..", "assets", "parallel_solution.py")) as f:
            source = f.read()
    ast.parse(source)  # refuse to install something that does not parse

    target = os.path.abspath(state["solution_path"])
    if not os.path.isdir(state["workspace_dir"]):
        sys.exit(f"workspace_dir not found: {state['workspace_dir']}")
    if os.path.isfile(target):
        with open(target) as f:
            if f.read() != source:
                shutil.copyfile(target, target + ".bak")  # keep a differing prior version
    with open(target, "w") as f:
        f.write(source)
    json.dump({"installed_path": target, "installed_bytes": len(source.encode())}, sys.stdout)


if __name__ == "__main__":
    main()

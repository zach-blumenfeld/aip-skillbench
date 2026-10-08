"""Step `write-solution`: render the canonical solution template to solution_path.

Substitutes function_name for the template's placeholder and writes the file
(creating parent folders). The written module needs only pymatgen and sympy.
"""
import sys
sys.dont_write_bytecode = True  # keep the skill folder free of __pycache__

import os

from _common import emit, fail, read_payload, render, template_source


def main():
    state, assets = read_payload()
    solution_path = state.get("solution_path")
    function_name = state.get("function_name")
    if not solution_path or not function_name:
        fail("solution_path and function_name are required")
    src = render(template_source(assets), function_name)
    solution_path = os.path.abspath(os.path.expanduser(solution_path))
    os.makedirs(os.path.dirname(solution_path), exist_ok=True)
    with open(solution_path, "w") as fh:
        fh.write(src)
    emit({"solution_path": solution_path, "solution_written": True,
          "solution_source": "canonical template (assets/solution_template.py)"})


if __name__ == "__main__":
    main()

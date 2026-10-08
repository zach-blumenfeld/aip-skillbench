"""Step `verify-solution`: import the written solution and run it on every CIF.

Checks, per file: the function exists and runs; the result is JSON-serializable.
Standard convention: the result holds `wyckoff_multiplicity_dict` and
`wyckoff_coordinates_dict`, their keys match, multiplicities sum to the site
count, and both equal the canonical analysis from `analyze-cifs` exactly.
Custom convention: content cannot be checked generically, so each output is
returned side by side with the canonical analysis (`comparisons`) for the
client to review against the task's stated format.
"""
import sys
sys.dont_write_bytecode = True  # keep the skill folder free of __pycache__

import importlib.util
import json
import os
import sys

from _common import call_quietly, emit, fail, read_payload

KEYS = ("wyckoff_multiplicity_dict", "wyckoff_coordinates_dict")


def load(path):
    sys.path.insert(0, os.path.dirname(path))
    spec = importlib.util.spec_from_file_location("solution_under_test", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    state, _ = read_payload()
    path = os.path.abspath(os.path.expanduser(state.get("solution_path", "")))
    fname = state.get("function_name")
    convention = state.get("output_convention", "standard")
    analyses = {a["path"]: a for a in state.get("analyses", [])}
    files = state.get("cif_files") or list(analyses)
    problems, outputs, comparisons = [], {}, {}

    if not os.path.isfile(path):
        fail(f"solution file not found: {path}")
    try:
        mod = load(path)
    except Exception as exc:
        emit({"verification_passed": False,
              "verification": {"problems": [f"import failed: {type(exc).__name__}: {exc}"]}})
        return
    fn = getattr(mod, fname, None)
    if not callable(fn):
        emit({"verification_passed": False,
              "verification": {"problems": [f"function {fname!r} not defined in {path}"]}})
        return

    for cif in files:
        name = os.path.basename(cif)
        try:
            out, _ = call_quietly(fn, cif)
        except Exception as exc:
            problems.append(f"{name}: raised {type(exc).__name__}: {exc}")
            continue
        try:
            json.dumps(out)
        except TypeError as exc:
            problems.append(f"{name}: result is not JSON-serializable ({exc})")
            out = json.loads(json.dumps(out, default=str))
        outputs[name] = out
        ref = analyses.get(cif)
        if convention != "standard" and ref:
            comparisons[name] = {
                "output": out,
                "canonical": {k: ref.get(k) for k in KEYS + ("spacegroup_symbol", "num_sites", "error") if k in ref},
            }
        if convention == "standard":
            if not isinstance(out, dict) or any(k not in out for k in KEYS):
                problems.append(f"{name}: result must be a dict with keys {list(KEYS)}")
                continue
            m, c = out[KEYS[0]], out[KEYS[1]]
            if set(m) != set(c):
                problems.append(f"{name}: letter keys differ between the two dicts")
            if ref and "error" not in ref:
                if m and ref.get("num_sites") and sum(m.values()) != ref["num_sites"]:
                    problems.append(f"{name}: multiplicities sum to {sum(m.values())}, expected {ref['num_sites']} sites")
                for k in KEYS:
                    if out[k] != ref.get(k):
                        problems.append(f"{name}: {k} differs from canonical analysis: got {out[k]}, expected {ref.get(k)}")

    emit({"verification_passed": not problems,
          "verification": {"solution_path": path, "function_name": fname,
                           "output_convention": convention, "files_checked": len(files),
                           "problems": problems, "outputs": outputs,
                           **({"comparisons": comparisons,
                               "review": "custom convention: outputs are not auto-compared; check each against "
                                         "its canonical analysis and the task's format before finishing"}
                              if convention != "standard" else {})}})


if __name__ == "__main__":
    main()

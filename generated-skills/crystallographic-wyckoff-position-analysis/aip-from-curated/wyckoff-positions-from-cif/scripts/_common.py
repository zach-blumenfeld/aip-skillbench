"""Shared helpers for the wyckoff-positions-from-cif step scripts.

Each step script reads one JSON object on stdin ({"currentState", "assets",
"expects"}) and writes one JSON object on stdout. Library warnings go to the
result's `notes`, never to stdout.
"""
import glob
import json
import os
import sys
import types
import warnings

PLACEHOLDER = "__FUNCTION_NAME__"
HERE = os.path.dirname(os.path.abspath(__file__))

# Library deprecation chatter must not reach stderr; call_quietly() still records
# warnings raised while reading a CIF.
warnings.filterwarnings("ignore")


def read_payload():
    raw = sys.stdin.read()
    payload = json.loads(raw) if raw.strip() else {}
    return payload.get("currentState", {}), payload.get("assets", {}) or {}


def emit(obj):
    sys.stdout.write(json.dumps(obj))
    sys.stdout.write("\n")


def fail(message, **extra):
    emit({"error": message, **extra})
    sys.exit(1)


def template_source(assets):
    src = assets.get("solution_template")
    if src:
        return src
    with open(os.path.join(HERE, "..", "assets", "solution_template.py")) as fh:
        return fh.read()


def render(src, function_name):
    if not function_name.isidentifier():
        fail(f"function_name {function_name!r} is not a valid Python identifier")
    return src.replace(PLACEHOLDER, function_name)


def load_module_from_source(src, name="wyckoff_solution"):
    mod = types.ModuleType(name)
    exec(compile(src, name, "exec"), mod.__dict__)
    return mod


def expand_cif_paths(paths):
    """Accept CIF files and/or directories (all *.cif inside, sorted)."""
    files, missing = [], []
    for p in paths:
        p = os.path.expanduser(str(p))
        if os.path.isdir(p):
            found = sorted(glob.glob(os.path.join(p, "*.cif")) + glob.glob(os.path.join(p, "*.CIF")))
            files.extend(found)
            if not found:
                missing.append(f"{p} (directory has no .cif files)")
        elif os.path.isfile(p):
            files.append(p)
        else:
            missing.append(p)
    seen, out = set(), []
    for f in files:
        a = os.path.abspath(f)
        if a not in seen:
            seen.add(a)
            out.append(a)
    return out, missing


def call_quietly(fn, *args):
    """Run fn, returning (result, [warning messages])."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = fn(*args)
    msgs = []
    for w in caught:
        m = str(w.message).strip()
        if "OLD_ERROR_HANDLING" in m:  # pymatgen deprecation chatter, not about the file
            continue
        if m and m not in msgs:
            msgs.append(m)
    return result, msgs

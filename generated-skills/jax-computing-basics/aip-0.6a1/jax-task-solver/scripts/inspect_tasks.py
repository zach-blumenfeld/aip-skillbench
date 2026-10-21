"""Read problem.json, inspect every task's input file, and suggest an op from the catalog.

stdin:  {"state": {"problem_path": "/abs/path/problem.json"}, ...}
stdout: {"tasks": [ {id, description, input, output, arrays, suggested_op, suggested_args, notes}, ... ]}

Relative `input`/`output` paths in problem.json resolve against problem.json's folder
(the script's own cwd is the skill's scripts/ folder, so never against cwd).
"""
import json
import os
import re
import sys

import numpy as np

from jax_skills import mlp_input_key, mlp_layers, resolve_roles

REDUCE_WORDS = [  # (regex, fn) — checked in order
    (r"\bstandard deviation\b|\bstd\b", "std"),
    (r"\bvariance\b|\bvar\b", "var"),
    (r"\bmedian\b", "median"),
    (r"\bargmax\b|\bindex of (the )?max", "argmax"),
    (r"\bargmin\b|\bindex of (the )?min", "argmin"),
    (r"\bmean\b|\baverage\b|\bavg\b", "mean"),
    (r"\bsum\b|\btotal\b", "sum"),
    (r"\bproduct\b|\bprod\b", "prod"),
    (r"\bmax(imum)?\b|\blargest\b", "max"),
    (r"\bmin(imum)?\b|\bsmallest\b", "min"),
    (r"\bnorm\b", "norm"),
]
MAP_WORDS = [
    (r"\bsquare[- ]root\b|\bsqrt\b", "sqrt"),
    (r"\bsquar(e|es|ed|ing)\b", "square"),
    (r"\bcube\b", "cube"),
    (r"\babsolute\b|\babs\b", "abs"),
    (r"\blog1p\b", "log1p"),
    (r"\bexp(onential)?\b", "exp"),
    (r"\blog(arithm)?\b", "log"),
    (r"\bnegat(e|ive)\b", "negative"),
    (r"\breciprocal\b", "reciprocal"),
    (r"\brelu\b", "relu"),
    (r"\bsigmoid\b", "sigmoid"),
    (r"\btanh\b", "tanh"),
    (r"\bsin(e)?\b", "sin"),
    (r"\bcos(ine)?\b", "cos"),
]


def describe(path):
    if not os.path.exists(path):
        return None, f"input file not found: {path}"
    try:
        if path.endswith(".npz"):
            with np.load(path) as z:
                return {k: {"shape": list(z[k].shape), "dtype": str(z[k].dtype)} for k in z.files}, None
        a = np.load(path)
        return {"<array>": {"shape": list(a.shape), "dtype": str(a.dtype)}}, None
    except Exception as e:  # noqa: BLE001
        return None, f"cannot read {path}: {e}"


def reduce_axis(desc, ndim):
    if re.search(r"\b(each|every|per) row\b|\brow[- ]?wise\b|\bacross (the )?columns\b|\bover (the )?columns\b|\balong axis ?1\b|\baxis ?= ?1\b", desc):
        return (1 if ndim == 2 else -1), ("rows of a >2-D array: axis -1 chosen, confirm" if ndim > 2 else None)
    if re.search(r"\b(each|every|per) column\b|\bcolumn[- ]?wise\b|\bacross (the )?rows\b|\bover (the )?rows\b|\balong axis ?0\b|\baxis ?= ?0\b", desc):
        return 0, None
    if re.search(r"\b(all|every) elements?\b|\boverall\b|\bglobal\b|\bentire\b|\bwhole\b|\bscalar\b", desc):
        return None, None
    return None, "no axis named in the description: full reduction (axis null) assumed, confirm"


def suggest(desc, arrays):
    d = desc.lower()
    names = [] if arrays is None else list(arrays)
    single = arrays is not None and list(arrays) == ["<array>"]
    notes = []

    if re.search(r"\bgrad", d):
        if not re.search(r"\blogistic\b|\blog[- ]loss\b|\bbinary cross[- ]entropy\b", d):
            return "custom", {}, ["gradient of a loss other than logistic: write it with jax.grad (custom)"]
        keys, missing = resolve_roles("logistic_grad", names)
        if missing:
            notes.append(f"logistic_grad roles not found in npz: {missing}; map them in args.keys")
        return "logistic_grad", {"keys": keys}, notes
    if re.search(r"\bscan\b|\brnn\b|\brecurren", d):
        keys, missing = resolve_roles("rnn_scan", names)
        if missing:
            notes.append(f"rnn_scan roles not found in npz: {missing}; map them in args.keys")
        if "init" not in keys:
            notes.append("no initial-state key in npz: h0 = zeros(H)")
        return "rnn_scan", {"keys": keys}, notes
    if re.search(r"\bmlp\b|\bmulti-?layer perceptron\b|\bfeed-?forward\b|\bneural net", d):
        ws, bs = mlp_layers(names)
        act = "relu"
        for a in ("tanh", "sigmoid", "gelu"):
            if re.search(rf"\b{a}\b", d):
                act = a
        if not re.search(r"\b(relu|tanh|sigmoid|gelu)\b", d):
            notes.append("activation not named: relu between layers, linear output (standard default)")
        m = re.search(r"\b(\d+|two|three|four)[- ]layer", d)
        if m:
            n = {"two": 2, "three": 3, "four": 4}.get(m.group(1)) or int(m.group(1))
            if n != len(ws):
                notes.append(f"description says {n} layers but npz has {len(ws)} weight matrices")
        if None in bs:
            notes.append("some weight matrices have no matching bias key")
        return "mlp", {"keys": {"X": mlp_input_key(names), "weights": ws, "biases": bs},
                       "activation": act}, notes

    elementwise = re.search(r"\belement|\bvectori[sz]|\bvmap\b|\bmap\b", d)
    map_fn = next((fn for pat, fn in MAP_WORDS if re.search(pat, d)), None)
    red_fn = next((fn for pat, fn in REDUCE_WORDS if re.search(pat, d)), None)
    if map_fn and (elementwise or not red_fn):
        args = {"fn": map_fn}
        if not single:
            notes.append("npz input: set args.array_key to the array to map")
        return "map", args, notes
    if red_fn:
        ndim = len(arrays["<array>"]["shape"]) if single else 2
        axis, note = reduce_axis(d, ndim)
        if note:
            notes.append(note)
        if not single:
            notes.append("npz input: set args.array_key to the array to reduce")
        return "reduce", {"fn": red_fn, "axis": axis}, notes
    return "custom", {}, ["no catalog op matches: write the JAX code yourself (custom)"]


def main():
    payload = json.load(sys.stdin)
    problem_path = payload["state"]["problem_path"]
    if not os.path.isabs(problem_path):
        sys.exit(f"problem_path must be absolute (scripts run from the skill folder): {problem_path}")
    if not os.path.exists(problem_path):
        sys.exit(f"problem.json not found: {problem_path}")
    with open(problem_path) as f:
        problems = json.load(f)
    if isinstance(problems, dict):
        problems = problems.get("tasks") or problems.get("problems") or [problems]
    base = os.path.dirname(problem_path)

    tasks = []
    for i, p in enumerate(problems):
        for k in ("input", "output"):
            if k not in p:
                sys.exit(f"task {p.get('id', i)} has no {k!r} key")
        inp = p["input"] if os.path.isabs(p["input"]) else os.path.join(base, p["input"])
        out = p["output"] if os.path.isabs(p["output"]) else os.path.join(base, p["output"])
        arrays, err = describe(inp)
        desc = p.get("description", "")
        if err:
            op, args, notes = "custom", {}, [err]
        else:
            op, args, notes = suggest(desc, arrays)
        tasks.append({"id": str(p.get("id", i)), "description": desc, "input": inp, "output": out,
                      "arrays": arrays, "suggested_op": op, "suggested_args": args, "notes": notes})
    json.dump({"tasks": tasks}, sys.stdout)


if __name__ == "__main__":
    main()

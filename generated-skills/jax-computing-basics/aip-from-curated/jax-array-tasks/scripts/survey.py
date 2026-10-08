"""Survey a JAX array-task spec: load the task list, inspect every input file, propose a plan.

stdin : {"currentState": {"problem_path", "output_dir", ["base_dir"], ["tasks"]}, "assets": {"ops": ...}, "expects": ...}
stdout: {"inventory": [...], "plan": [...], "plan_warnings": [...]}

Only numpy is needed here (no JAX import), so this step is fast.
"""
import json
import os
import re
import sys

import numpy as np


def fail(msg):
    print(json.dumps({"error": msg}))
    sys.exit(1)


def describe(path):
    """Return ({key: {"shape", "dtype", "unique" (if few)}}, is_npz). key None for .npy."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"input file not found: {path}")
    if path.endswith(".npz"):
        with np.load(path, allow_pickle=False) as z:
            arrays = {k: z[k] for k in z.files}
        is_npz = True
    else:
        arrays = {None: np.load(path, allow_pickle=False)}
        is_npz = False
    info = {}
    for k, a in arrays.items():
        entry = {"shape": list(a.shape), "dtype": str(a.dtype)}
        if a.size and a.size <= 100000:
            u = np.unique(a)
            if len(u) <= 4 and a.size >= 8:  # label-like vectors only, not tiny weight arrays
                entry["unique"] = [float(v) for v in u]
            if np.issubdtype(a.dtype, np.floating) and not np.all(np.isfinite(a)):
                entry["non_finite"] = True
        info["" if k is None else k] = entry
    return info, is_npz


def best_match(text, table):
    """Pick the table key whose keyword matches text as a whole word; longest keyword wins."""
    best, best_len = None, 0
    for name, kws in table.items():
        for kw in kws:
            if re.search(r"(?<![a-z0-9])" + re.escape(kw) + r"(?![a-z0-9])", text) and len(kw) > best_len:
                best, best_len = name, len(kw)
    return best


def find_key(keys, *cands):
    low = {k.lower(): k for k in keys}
    for c in cands:
        if c.lower() in low:
            return low[c.lower()]
    return None


def pick_array_key(info, notes):
    keys = [k for k in info if k != ""]
    if not keys:
        return None
    if len(keys) == 1:
        return keys[0]
    k = find_key(keys, "x", "X", "arr", "array", "data")
    if k is None:
        k = keys[0]
    notes.append(f"npz holds several arrays {keys}; chose '{k}' - confirm it is the one the task means")
    return k


def reduce_axis(text, ndim, notes):
    """Translate row/column wording into an axis. 'mean of each row' reduces across columns."""
    if re.search(r"\b(each|every|per|of the|by|across)\s+rows?\b|\brow[- ]?wise\b|\brows\b|\brow\b"
                 r"|\b(each|every|per)[- ](sample|observation|example|record|data ?point)s?\b", text):
        notes.append("'row' wording: one value per row -> reduce over the last axis (axis=1 for 2-D)")
        return ndim - 1 if ndim >= 2 else 0
    if re.search(r"\b(each|every|per|of the|by|across)\s+columns?\b|\bcolumn[- ]?wise\b|\bcolumns?\b|\bfeatures?\b", text):
        notes.append("'column' wording: one value per column -> reduce over axis 0")
        return 0
    m = re.search(r"\baxis\s*=?\s*(-?\d+)", text)
    if m:
        return int(m.group(1))
    if re.search(r"\b(all|overall|global|entire|whole|total)\b", text):
        return None
    notes.append("AMBIGUOUS: no axis wording found; defaulted to axis=None (all elements) - confirm")
    return None


def propose(task, info, is_npz, ops):
    text = (str(task.get("id", "")) + " " + str(task.get("description", ""))).lower().replace("_", " ")
    keys = [k for k in info if k != ""]
    notes = []
    params = {}

    has = lambda *names: all(find_key(keys, n) for n in names)
    if re.search(r"\bmlp\b|perceptron|multi-?layer|\blayers?\b|feed-?forward", text) or has("W1", "W2"):
        op = "mlp_forward"
        x_key = find_key(keys, "X", "x", "inputs", "input")
        layers, i = [], 1
        while find_key(keys, f"W{i}"):
            layers.append([find_key(keys, f"W{i}"), find_key(keys, f"b{i}")])
            i += 1
        if not layers:
            notes.append("AMBIGUOUS: no W1/W2... keys found; fill layers by hand")
        act = best_match(text, {a: [a] for a in ops["activations"]}) or "relu"
        if act == "relu" and "relu" not in text:
            notes.append("activation not named in description; defaulted to relu on hidden layers (final layer linear)")
        w_side = "right"
        if x_key and layers and layers[0][0]:
            xd, wsh = info[x_key]["shape"][-1], info[layers[0][0]]["shape"]
            if wsh[0] != xd and wsh[-1] == xd:
                w_side = "left"
                notes.append("W1 is stored (out, in); using x @ W.T")
        params = {"x_key": x_key, "layers": layers, "activation": act, "w_side": w_side}
    elif re.search(r"\brnn\b|recurren|\bscan\b|hidden state", text) or has("Wx", "Wh") or has("W_ih", "W_hh") or has("W_in", "W_rec"):
        op = "rnn_scan"
        seq_key = find_key(keys, "seq", "sequence", "xs", "x", "inputs")
        wx = find_key(keys, "Wx", "W_x", "Wxh", "W_xh", "W_ih", "Wih", "W_in", "Win", "U")
        wh = find_key(keys, "Wh", "W_h", "Whh", "W_hh", "W_rec", "Wrec", "W")
        b = find_key(keys, "b", "bias", "bh", "b_h")
        h0 = find_key(keys, "init", "h0", "h_init", "initial", "hidden0")
        if h0 is None:
            notes.append("no initial-state array in file; h0 = zeros(H)")
        else:
            notes.append(f"initial hidden state taken from '{h0}'")
        wx_side, wh_side = "left", "left"
        if seq_key and wx:
            d, wsh = info[seq_key]["shape"][-1], info[wx]["shape"]
            if wsh[-1] != d and wsh[0] == d:
                wx_side = wh_side = "right"
                notes.append("Wx is stored (in, hidden): row-vector convention, so x @ Wx and h @ Wh (one convention for both)")
            elif wsh[0] == wsh[-1]:
                notes.append("Wx is square, so orientation cannot be inferred from shapes; using the jax-skills convention Wx @ x")
        params = {"seq_key": seq_key, "Wx_key": wx, "Wh_key": wh, "b_key": b, "h0_key": h0,
                  "wx_side": wx_side, "wh_side": wh_side, "activation": "tanh"}
    elif re.search(r"grad|logistic|log[- ]?loss|cross[- ]?entropy", text) or has("x", "y", "w"):
        op = "logistic_grad"
        x_key, y_key, w_key = find_key(keys, "x", "X", "features"), find_key(keys, "y", "labels", "t"), find_key(keys, "w", "weights", "theta", "W")
        labels = "pm1"
        if y_key and "unique" in info[y_key]:
            u = set(info[y_key]["unique"])
            if u <= {0.0, 1.0}:
                labels = "01"
                notes.append("labels are {0,1}; mapped to {-1,+1} via 2y-1 (identical to binary cross-entropy)")
        if w_key is None:
            notes.append("AMBIGUOUS: no weight vector in file; compute will use w = zeros(D) - confirm")
        params = {"x_key": x_key, "y_key": y_key, "w_key": w_key, "labels": labels}
    else:
        mfunc = best_match(text, ops["map_funcs"])
        rfunc = best_match(text, ops["reduce_funcs"])
        is_map = bool(re.search(r"\bmap\b|elementwise|element-wise|each element|every element|vectori[sz]", text))
        key = pick_array_key(info, notes) if is_npz else None
        ndim = len(info[key if key is not None else ""]["shape"])
        if rfunc and not is_map:
            op = "reduce"
            params = {"key": key, "func": rfunc, "axis": reduce_axis(text, ndim, notes)}
        elif mfunc:
            op = "map"
            params = {"key": key, "func": mfunc}
        else:
            op = "unknown"
            notes.append("AMBIGUOUS: could not classify this task; set op and params by hand")
    if any(v is None for k, v in params.items() if k.endswith("_key") and k != "h0_key" and not (op == "logistic_grad" and k == "w_key")):
        notes.append("AMBIGUOUS: a required array key was not found in the file; fill it by hand")
    return op, params, notes


def main():
    payload = json.load(sys.stdin)
    state = payload.get("currentState", {})
    ops = payload.get("assets", {}).get("ops")
    ops = json.loads(ops) if isinstance(ops, str) else ops
    if not ops:
        here = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(here, "..", "assets", "ops.json")) as f:
            ops = json.load(f)

    problem_path = state.get("problem_path") or ""
    tasks = state.get("tasks")
    if not tasks:
        if not problem_path or not os.path.exists(problem_path):
            fail(f"problem_path does not exist: {problem_path!r}")
        with open(problem_path) as f:
            tasks = json.load(f)
        if isinstance(tasks, dict):
            tasks = tasks.get("tasks") or tasks.get("problems") or [tasks]
    base = state.get("base_dir") or (os.path.dirname(os.path.abspath(problem_path)) if problem_path else os.getcwd())
    out_dir = state.get("output_dir")
    if not out_dir:
        fail("output_dir is required")
    out_dir = os.path.abspath(out_dir)

    inventory, plan, warnings = [], [], []
    for i, t in enumerate(tasks):
        tid = str(t.get("id", f"task{i}"))
        inp = t.get("input", "")
        inp_abs = inp if os.path.isabs(inp) else os.path.join(base, inp)
        out = t.get("output") or f"{tid}.npy"
        out_abs = out if os.path.isabs(out) else os.path.join(out_dir, out)
        try:
            info, is_npz = describe(inp_abs)
        except Exception as e:  # keep going so every problem is reported at once
            warnings.append(f"{tid}: {e}")
            plan.append({"id": tid, "description": t.get("description", ""), "input": inp_abs, "output": out_abs,
                         "op": "unknown", "params": {}, "notes": [f"AMBIGUOUS: {e}"]})
            continue
        inventory.append({"id": tid, "input": inp_abs, "arrays": info})
        op, params, notes = propose(t, info, is_npz, ops)
        if not out_abs.endswith(".npy"):
            notes.append("output does not end in .npy; np.save will append .npy - confirm the expected name")
        plan.append({"id": tid, "description": t.get("description", ""), "input": inp_abs, "output": out_abs,
                     "op": op, "params": params, "notes": notes})
        warnings += [f"{tid}: {n}" for n in notes if n.startswith("AMBIGUOUS")]

    print(json.dumps({"inventory": inventory, "plan": plan, "plan_warnings": warnings, "output_dir": out_dir, "results": []}))


if __name__ == "__main__":
    main()

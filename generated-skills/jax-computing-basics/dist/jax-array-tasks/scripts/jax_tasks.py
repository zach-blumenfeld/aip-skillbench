#!/usr/bin/env python3
"""Solve problem.json-style JAX array tasks: inspect -> plan -> run -> verify.

Requires: Python >= 3.10, jax (+ jaxlib) >= 0.4, numpy >= 1.24. No other packages.

Subcommands
  inspect PROBLEM            list every task, its input file's arrays (key/shape/dtype)
                             and a keyword-based suggested op (a hint, not an answer)
  run PROBLEM PLAN           validate PLAN, compute each planned task in JAX, save the
                             outputs, cross-check each against an independent NumPy
                             implementation (and a reference dir if one exists)
  verify PROBLEM [--plan P]  check every task's output file exists, loads, is finite,
                             and (when available) matches the NumPy recompute / reference

Paths in problem.json ("input", "output") are resolved relative to the directory that
contains problem.json unless absolute. Override the output dir with --out-dir.

Importable too: `sys.path.insert(0, "<skill>/scripts"); import jax_tasks as jt` gives
load(), save(), and the op functions (map_op, reduce_op, logistic_grad, rnn_scan, mlp).
"""
import argparse
import json
import os
import sys

import numpy as np

try:
    import jax
    import jax.numpy as jnp
except ImportError:  # pragma: no cover
    sys.exit("ERROR: jax is not installed. Install jax+jaxlib (pip install jax) and retry.")

RTOL, ATOL = 1e-5, 1e-5
OPS = ("reduce", "map", "logistic_grad", "rnn_scan", "mlp", "other")
REDUCE_FNS = ("mean", "sum", "max", "min", "prod", "std", "var")
MAP_FNS = ("square", "abs", "exp", "log", "sqrt", "tanh", "sigmoid", "relu", "negative", "sin", "cos")
ACTIVATIONS = ("relu", "tanh", "sigmoid", "gelu", "none")

# Key aliases for .npz inputs (matched case-sensitively first, then case-insensitively).
KEY_ALIASES = {
    "logistic_grad": {"x": ["x", "X", "features", "inputs"], "y": ["y", "labels", "targets"],
                      "w": ["w", "W", "weights", "theta", "true_w"]},
    "rnn_scan": {"seq": ["seq", "x", "X", "inputs", "sequence", "xs"], "Wx": ["Wx", "W_x", "Wxh", "W_xh"],
                 "Wh": ["Wh", "W_h", "Whh", "W_hh"], "b": ["b", "bias", "bh", "b_h"],
                 "init": ["init", "h0", "h_init", "initial", "init_h"]},
    "mlp": {"X": ["X", "x", "inputs"], "W1": ["W1", "w1"], "b1": ["b1"], "W2": ["W2", "w2"], "b2": ["b2"]},
}
OPTIONAL_KEYS = {"rnn_scan": {"init"}}

# Keyword hints for `inspect` only. The agent decides; these just pre-fill.
HINTS = [
    (("logistic",), "logistic_grad"),
    (("rnn", "scan", "recurren"), "rnn_scan"),
    (("mlp", "multilayer", "multi-layer", "perceptron"), "mlp"),
    (("mean", "sum", "average", "max", "min", "reduce", "std", "variance"), "reduce"),
    (("square", "elementwise", "element-wise", "each element", "vmap", "vectoriz"), "map"),
]


# ---------------------------------------------------------------- load / save
def load(path):
    """.npz -> dict of jnp arrays; .npy -> jnp array; .json -> jnp array or dict."""
    if path.endswith(".npz"):
        with np.load(path) as z:
            return {k: jnp.asarray(z[k]) for k in z.files}
    if path.endswith(".json"):
        with open(path) as f:
            obj = json.load(f)
        if isinstance(obj, dict):
            return {k: jnp.asarray(v) for k, v in obj.items()}
        return jnp.asarray(obj)
    return jnp.asarray(np.load(path, allow_pickle=False))


def save(data, path):
    """Save as a plain .npy (NumPy array, dtype preserved). Creates parent dirs."""
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    np.save(path, np.asarray(data))


# ---------------------------------------------------------------- JAX ops
def map_op(array, fn="square"):
    f = {
        "square": lambda v: v * v, "abs": jnp.abs, "exp": jnp.exp, "log": jnp.log, "sqrt": jnp.sqrt,
        "tanh": jnp.tanh, "sigmoid": jax.nn.sigmoid, "relu": jax.nn.relu, "negative": jnp.negative,
        "sin": jnp.sin, "cos": jnp.cos,
    }[fn]
    if array.ndim == 0:
        return f(array)
    return jax.vmap(f)(array)  # vectorized over the leading axis; f is elementwise


def reduce_op(array, fn="mean", axis=None):
    return getattr(jnp, fn)(array, axis=axis)


def logistic_grad(x, y, w):
    """Gradient wrt w of mean(log(1 + exp(-y * (x @ w)))), labels y in {-1,+1}."""
    def loss(w_):
        logits = x @ w_
        return jnp.mean(jnp.logaddexp(0.0, -y * logits))  # stable log(1+exp(.))
    return jax.grad(loss)(w)


def _rnn_orient(seq, Wx):
    """Return True if Wx multiplies on the left (Wx @ x_t), else x_t @ Wx."""
    d_in = seq.shape[-1]
    if Wx.shape[1] == d_in:
        return True  # (H, D_in): the source convention; also chosen when square
    if Wx.shape[0] == d_in:
        return False
    raise ValueError(f"Wx shape {Wx.shape} incompatible with seq feature dim {d_in}")


def rnn_scan(seq, Wx, Wh, b, h0=None):
    """h_t = tanh(Wx x_t + Wh h_{t-1} + b) via lax.scan; returns all hidden states (T, H)."""
    left = _rnn_orient(seq, Wx)
    H = Wh.shape[0]
    h0 = jnp.zeros(H, dtype=seq.dtype) if h0 is None else h0

    def step(h, x):
        xin = Wx @ x if left else x @ Wx
        h_new = jnp.tanh(xin + Wh @ h + b)
        return h_new, h_new

    _, hseq = jax.lax.scan(step, h0, seq)
    return hseq


def _act(name):
    return {"relu": jax.nn.relu, "tanh": jnp.tanh, "sigmoid": jax.nn.sigmoid,
            "gelu": jax.nn.gelu, "none": lambda v: v}[name]


def _orient_w(X_dim, W):
    if W.shape[0] == X_dim:
        return W
    if W.ndim == 2 and W.shape[1] == X_dim:
        return W.T
    raise ValueError(f"weight shape {W.shape} incompatible with input dim {X_dim}")


def mlp(X, W1, b1, W2, b2, hidden="relu", output="none"):
    """JIT-compiled 2-layer MLP: out = act_out(act_h(X @ W1 + b1) @ W2 + b2)."""
    W1o = _orient_w(X.shape[-1], W1)
    W2o = _orient_w(W1o.shape[-1], W2)
    ah, ao = _act(hidden), _act(output)

    @jax.jit
    def f(x):
        h = ah(jnp.dot(x, W1o) + b1)
        return ao(jnp.dot(h, W2o) + b2)

    return f(X)


# ---------------------------------------------------------------- NumPy cross-checks
def _np_act(name, v):
    return {"relu": lambda a: np.maximum(a, 0), "tanh": np.tanh, "sigmoid": lambda a: 1 / (1 + np.exp(-a)),
            "gelu": None, "none": lambda a: a}[name](v)


def np_check(op, args, opts):
    with np.errstate(all="ignore"):  # NaN/Inf are reported by the caller, not as warnings
        return _np_check(op, args, opts)


def _np_check(op, args, opts):
    a = {k: (None if v is None else np.asarray(v, dtype=np.float64)) for k, v in args.items()}
    if op == "map":
        fn = opts["fn"]
        npf = {"square": np.square, "abs": np.abs, "exp": np.exp, "log": np.log, "sqrt": np.sqrt,
               "tanh": np.tanh, "sigmoid": lambda v: 1 / (1 + np.exp(-v)), "relu": lambda v: np.maximum(v, 0),
               "negative": np.negative, "sin": np.sin, "cos": np.cos}[fn]
        return npf(a["array"])
    if op == "reduce":
        return getattr(np, opts["fn"])(a["array"], axis=opts.get("axis"))
    if op == "logistic_grad":
        x, y, w = a["x"], a["y"], a["w"]
        m = -y * (x @ w)
        s = 1 / (1 + np.exp(-m))  # d/dm log(1+e^m)
        return x.T @ (s * -y) / x.shape[0]
    if op == "rnn_scan":
        seq, Wx, Wh, b = a["seq"], a["Wx"], a["Wh"], a["b"]
        left = _rnn_orient(seq, Wx)
        h = np.zeros(Wh.shape[0]) if a.get("init") is None else a["init"]
        out = []
        for x in seq:
            h = np.tanh((Wx @ x if left else x @ Wx) + Wh @ h + b)
            out.append(h)
        return np.stack(out)
    if op == "mlp":
        if "gelu" in (opts.get("hidden"), opts.get("output")):
            return None
        W1 = _orient_w(a["X"].shape[-1], a["W1"])
        W2 = _orient_w(W1.shape[-1], a["W2"])
        h = _np_act(opts.get("hidden", "relu"), a["X"] @ W1 + a["b1"])
        return _np_act(opts.get("output", "none"), h @ W2 + a["b2"])
    return None


# ---------------------------------------------------------------- plumbing
def read_problem(path):
    with open(path) as f:
        tasks = json.load(f)
    if isinstance(tasks, dict):
        tasks = tasks.get("tasks", [tasks])
    for t in tasks:
        for k in ("id", "input", "output"):
            if k not in t:
                sys.exit(f"ERROR: task {t} lacks required key '{k}'")
    return tasks


def resolve(base, p):
    return p if os.path.isabs(p) else os.path.normpath(os.path.join(base, p))


def describe(obj):
    if isinstance(obj, dict):
        return {k: f"shape={tuple(v.shape)} dtype={v.dtype}" for k, v in obj.items()}
    return f"shape={tuple(obj.shape)} dtype={obj.dtype}"


def hint(desc):
    d = desc.lower()
    for words, op in HINTS:
        if any(w in d for w in words):
            return op
    return "other"


def pick_keys(op, data, override):
    """Map canonical arg names -> npz keys using override, then aliases."""
    out = {}
    for canon, aliases in KEY_ALIASES[op].items():
        key = (override or {}).get(canon)
        if key is None:
            for al in aliases:
                if al in data:
                    key = al
                    break
        if key is None:
            low = {k.lower(): k for k in data}
            for al in aliases:
                if al.lower() in low:
                    key = low[al.lower()]
                    break
        if key is None or key not in data:
            if canon in OPTIONAL_KEYS.get(op, ()):
                out[canon] = None
                continue
            raise ValueError(f"cannot find array for '{canon}' (have keys {sorted(data)}); "
                             f"set plan \"keys\": {{\"{canon}\": \"<npz key>\"}}")
        out[canon] = key
    return out


def single_array(data, entry):
    if isinstance(data, dict):
        key = entry.get("array_key")
        if key is None:
            if len(data) != 1:
                raise ValueError(f"input has keys {sorted(data)}; set plan \"array_key\"")
            key = next(iter(data))
        return data[key]
    return data


def validate_entry(e, task_ids):
    errs = []
    if e.get("id") not in task_ids:
        errs.append(f"plan id {e.get('id')!r} not in problem.json ids {sorted(task_ids)}")
    op = e.get("op")
    if op not in OPS:
        errs.append(f"{e.get('id')}: op {op!r} not one of {OPS}")
    if op == "reduce":
        if e.get("fn") not in REDUCE_FNS:
            errs.append(f"{e['id']}: reduce fn {e.get('fn')!r} not one of {REDUCE_FNS}")
        if "axis" not in e:
            errs.append(f"{e['id']}: reduce needs explicit \"axis\" (int, list of ints, or null for all)")
    if op == "map" and e.get("fn") not in MAP_FNS:
        errs.append(f"{e['id']}: map fn {e.get('fn')!r} not one of {MAP_FNS}")
    if op == "mlp":
        for k in ("hidden", "output"):
            if e.get(k, "relu" if k == "hidden" else "none") not in ACTIVATIONS:
                errs.append(f"{e['id']}: mlp {k} activation {e.get(k)!r} not one of {ACTIVATIONS}")
    return errs


def compute(e, data):
    """Return (jax_result, numpy_check_or_None)."""
    op = e["op"]
    if op in ("map", "reduce"):
        arr = single_array(data, e)
        if op == "map":
            args, opts = {"array": arr}, {"fn": e["fn"]}
            res = jax.jit(map_op, static_argnums=1)(arr, e["fn"])
        else:
            ax = e["axis"]
            ax = tuple(ax) if isinstance(ax, list) else ax
            if ax is not None:
                for a_ in (ax if isinstance(ax, tuple) else (ax,)):
                    if not -arr.ndim <= a_ < arr.ndim:
                        raise ValueError(f"axis {a_} out of range for array of ndim {arr.ndim}")
            args, opts = {"array": arr}, {"fn": e["fn"], "axis": ax}
            res = reduce_op(arr, e["fn"], ax)
        return res, np_check(op, args, opts)
    if not isinstance(data, dict):
        raise ValueError(f"op {op} needs a .npz input with named arrays")
    keys = pick_keys(op, data, e.get("keys"))
    args = {c: (None if k is None else data[k]) for c, k in keys.items()}
    print(f"    keys used: { {c: k for c, k in keys.items()} }")
    if op == "logistic_grad":
        yv = np.unique(np.asarray(args["y"]))
        if set(yv.tolist()) <= {0.0, 1.0}:
            print("    WARNING: labels are in {0,1}; the loss assumes {-1,+1}. Decide label_encoding "
                  "(plan \"y_transform\": \"pm1\" converts y -> 2y-1).")
        if e.get("y_transform") == "pm1":
            args["y"] = 2 * args["y"] - 1
        res = jax.jit(logistic_grad)(args["x"], args["y"], args["w"])
        return res, np_check(op, args, {})
    if op == "rnn_scan":
        h0 = args.get("init")
        if e.get("use_init", True) is False:
            h0 = None
        args["init"] = h0
        print(f"    h0: {'zeros' if h0 is None else 'from npz'}; Wx side: "
              f"{'Wx @ x_t' if _rnn_orient(args['seq'], args['Wx']) else 'x_t @ Wx'}")
        res = rnn_scan(args["seq"], args["Wx"], args["Wh"], args["b"], h0)
        return res, np_check(op, args, {})
    if op == "mlp":
        hid, out = e.get("hidden", "relu"), e.get("output", "none")
        res = mlp(args["X"], args["W1"], args["b1"], args["W2"], args["b2"], hid, out)
        return res, np_check(op, args, {"hidden": hid, "output": out})
    raise ValueError(f"op {op} is not computed by this script")


def compare(name, got, want):
    got = np.asarray(got)
    want = np.asarray(want)
    if got.shape != want.shape:
        return f"{name}: SHAPE MISMATCH got {got.shape} vs {want.shape}"
    ok = np.allclose(got, want, rtol=RTOL, atol=ATOL, equal_nan=True)
    err = float(np.nanmax(np.abs(got.astype(np.float64) - want))) if got.size else 0.0
    return f"{name}: {'OK' if ok else 'MISMATCH'} (max abs diff {err:.2e})" + ("" if ok else " <-- FIX")


def ref_dir(base, arg):
    if arg:
        return arg
    d = os.path.join(base, "reference")
    return d if os.path.isdir(d) else None


# ---------------------------------------------------------------- commands
def cmd_inspect(a):
    base = os.path.dirname(os.path.abspath(a.problem))
    for t in read_problem(a.problem):
        p = resolve(base, t["input"])
        print(f"- id: {t['id']}\n  description: {t.get('description', '')}\n  input: {p}\n"
              f"  output: {resolve(a.out_dir or base, t['output'])}\n  suggested_op: {hint(t.get('description', ''))}")
        try:
            print(f"  arrays: {json.dumps(describe(load(p)))}")
        except Exception as ex:  # noqa: BLE001
            print(f"  arrays: ERROR loading input: {ex}")


def cmd_run(a):
    base = os.path.dirname(os.path.abspath(a.problem))
    out_base = a.out_dir or base
    tasks = {t["id"]: t for t in read_problem(a.problem)}
    with open(a.plan) as f:
        plan = json.load(f)
    errs = [m for e in plan for m in validate_entry(e, tasks)]
    missing = sorted(set(tasks) - {e.get("id") for e in plan})
    if missing:
        errs.append(f"plan has no entry for task ids {missing} (use op \"other\" for hand-written ones)")
    if errs:
        print("PLAN INVALID:\n  " + "\n  ".join(errs))
        sys.exit(2)
    rdir = ref_dir(base, a.reference)
    failed = False
    for e in plan:
        t = tasks[e["id"]]
        outp = resolve(out_base, t["output"])
        print(f"[{e['id']}] op={e['op']}" + (f" fn={e.get('fn')}" if "fn" in e else "")
              + (f" axis={e.get('axis')}" if "axis" in e else ""))
        if e["op"] == "other":
            print(f"    SKIPPED: client task - write JAX code yourself, save to {outp}, then run verify")
            continue
        try:
            data = load(resolve(base, t["input"]))
            res, chk = compute(e, data)
            res = jax.block_until_ready(res)
            if not np.all(np.isfinite(np.asarray(res))):
                print("    WARNING: result contains NaN/Inf")
                failed = True
            save(res, outp)
            print(f"    saved {outp}  {describe(np.asarray(res))}")
            if chk is not None:
                msg = compare("numpy-check", res, chk)
                failed |= "OK" not in msg
                print("    " + msg)
            if rdir and os.path.exists(os.path.join(rdir, os.path.basename(t["output"]))):
                msg = compare("reference", res, np.load(os.path.join(rdir, os.path.basename(t["output"]))))
                failed |= "OK" not in msg
                print("    " + msg)
        except Exception as ex:  # noqa: BLE001
            failed = True
            print(f"    ERROR: {type(ex).__name__}: {ex}")
    sys.exit(1 if failed else 0)


def cmd_verify(a):
    base = os.path.dirname(os.path.abspath(a.problem))
    out_base = a.out_dir or base
    plan = {}
    if a.plan:
        with open(a.plan) as f:
            plan = {e["id"]: e for e in json.load(f)}
    rdir = ref_dir(base, a.reference)
    failed = False
    for t in read_problem(a.problem):
        outp = resolve(out_base, t["output"])
        if not os.path.exists(outp):
            print(f"[{t['id']}] MISSING {outp}")
            failed = True
            continue
        try:
            got = np.load(outp, allow_pickle=False)
        except Exception as ex:  # noqa: BLE001
            print(f"[{t['id']}] UNLOADABLE {outp}: {ex}")
            failed = True
            continue
        line = f"[{t['id']}] {outp} {describe(got)}"
        if not np.all(np.isfinite(got)):
            line += " NON-FINITE"
            failed = True
        print(line)
        e = plan.get(t["id"])
        if e and e.get("op") not in (None, "other"):
            try:
                _, chk = compute(e, load(resolve(base, t["input"])))
                if chk is not None:
                    msg = compare("numpy-check", got, chk)
                    failed |= "OK" not in msg
                    print("    " + msg)
            except Exception as ex:  # noqa: BLE001
                print(f"    numpy-check ERROR: {ex}")
                failed = True
        if rdir and os.path.exists(os.path.join(rdir, os.path.basename(t["output"]))):
            msg = compare("reference", got, np.load(os.path.join(rdir, os.path.basename(t["output"]))))
            failed |= "OK" not in msg
            print("    " + msg)
    print("ALL OK" if not failed else "SOME CHECKS FAILED")
    sys.exit(1 if failed else 0)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("inspect", "run", "verify"):
        p = sub.add_parser(name)
        p.add_argument("problem", help="path to problem.json")
        if name == "run":
            p.add_argument("plan", help="path to plan.json")
        if name == "verify":
            p.add_argument("--plan", help="plan.json, enables the NumPy recompute check")
        p.add_argument("--out-dir", help="directory outputs are relative to (default: problem.json's dir)")
        if name != "inspect":
            p.add_argument("--reference", help="dir of expected .npy files to compare against "
                                               "(default: <problem dir>/reference if it exists)")
    a = ap.parse_args()
    {"inspect": cmd_inspect, "run": cmd_run, "verify": cmd_verify}[a.cmd](a)


if __name__ == "__main__":
    main()

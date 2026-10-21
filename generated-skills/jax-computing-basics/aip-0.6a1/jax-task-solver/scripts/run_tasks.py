"""Execute the confirmed plan with JAX and save each result to its output path.

stdin:  {"state": {"plan": [ {id, op, args, input, output}, ... ]}, ...}
stdout: {"results": [ {id, op, output, status, shape, dtype, finite, message}, ... ],
         "status": "complete" | "needs_agent"}

Task status: "ok" (saved), "custom" (op is custom, left for the agent), "error" (the op
raised: bad key, shape mismatch, unreadable file; nothing saved). Any non-ok task makes
the overall status "needs_agent".
"""
import json
import sys

import numpy as np

import jax_skills as jx


def pick(data, key, role):
    if key not in data:
        raise KeyError(f"{role}: key {key!r} not in npz (keys: {sorted(data)})")
    return data[key]


def single_array(data, args):
    if isinstance(data, dict):
        key = args.get("array_key")
        if key is None:
            if len(data) != 1:
                raise ValueError(f"npz has several arrays {sorted(data)}: set args.array_key")
            key = next(iter(data))
        return pick(data, key, "array_key")
    return data


def run_one(task):
    op, args = task["op"], task.get("args") or {}
    data = jx.load(task["input"])
    names = list(data) if isinstance(data, dict) else []
    if op == "map":
        return jx.map_op(single_array(data, args), args["fn"])
    if op == "reduce":
        return jx.reduce_op(single_array(data, args), args["fn"], args.get("axis"))
    if op in ("logistic_grad", "rnn_scan"):
        if not isinstance(data, dict):
            raise ValueError(f"{op} needs an .npz input with named arrays")
        keys, missing = jx.resolve_roles(op, names)
        keys.update(args.get("keys") or {})
        missing = [r for r in missing if r not in keys]
        if missing:
            raise KeyError(f"{op}: no npz key for roles {missing} (keys: {sorted(names)})")
        if op == "logistic_grad":
            return jx.logistic_grad(pick(data, keys["x"], "x"), pick(data, keys["y"], "y"),
                                    pick(data, keys["w"], "w"))
        h0 = pick(data, keys["init"], "init") if keys.get("init") else None
        return jx.rnn_scan(pick(data, keys["seq"], "seq"), pick(data, keys["Wx"], "Wx"),
                           pick(data, keys["Wh"], "Wh"), pick(data, keys["b"], "b"), h0)
    if op == "mlp":
        if not isinstance(data, dict):
            raise ValueError("mlp needs an .npz input with X and W1..Wn, b1..bn")
        k = args.get("keys") or {}
        ws, bs = jx.mlp_layers(names)
        xk = k.get("X") or jx.mlp_input_key(names)
        ws, bs = k.get("weights") or ws, k.get("biases") or bs
        if xk is None or not ws or None in bs:
            raise KeyError(f"mlp: cannot pair X / W_i / b_i from npz keys {sorted(names)}")
        return jx.mlp(pick(data, xk, "X"), [pick(data, w, "W") for w in ws],
                      [pick(data, b, "b") for b in bs], args.get("activation", "relu"))
    raise ValueError(f"unknown op {op!r}")


def main():
    plan = json.load(sys.stdin)["state"]["plan"]
    results = []
    for task in plan:
        r = {"id": str(task.get("id")), "op": task.get("op"), "output": task.get("output"),
             "status": "ok", "shape": None, "dtype": None, "finite": None, "message": ""}
        if task.get("op") == "custom":
            r["status"], r["message"] = "custom", "no catalog op: write the JAX code (see references)"
        else:
            try:
                out = run_one(task)
                arr = np.asarray(out)
                jx.save(arr, task["output"])
                r.update(shape=list(arr.shape), dtype=str(arr.dtype),
                         finite=bool(np.all(np.isfinite(arr))) if arr.dtype.kind in "fc" else True)
                if not r["finite"]:
                    r["message"] = "result has NaN/Inf: check the formula and inputs"
            except Exception as e:  # noqa: BLE001 - reported per task, the agent fixes it
                r["status"], r["message"] = "error", f"{type(e).__name__}: {e}"
        results.append(r)
    status = "complete" if all(r["status"] == "ok" for r in results) else "needs_agent"
    json.dump({"results": results, "status": status}, sys.stdout)


if __name__ == "__main__":
    main()

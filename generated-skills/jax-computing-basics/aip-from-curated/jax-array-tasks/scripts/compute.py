"""Execute a reviewed JAX task plan: compute every result with JAX, save it as .npy, verify the file.

stdin : {"currentState": {"plan": [...]}, "assets": {...}, "expects": ...}
stdout: {"results": [...], "all_ok": bool}

Ops follow the curated jax-skills implementations (source/jax-skills/jax_skills.py):
JAX arrays throughout, NumPy only at the file boundary.
"""
import json
import os
import sys

import numpy as np

try:
    import jax
    import jax.numpy as jnp
except ImportError as e:  # the container ships jax==0.8.2; say so plainly if it is missing
    print(json.dumps({"error": f"JAX is not importable ({e}); install jax/jaxlib or run where they exist",
                      "results": [], "all_ok": False}))
    sys.exit(1)

MAP_FUNCS = {
    "square": lambda v: v * v,
    "abs": jnp.abs, "exp": jnp.exp, "log": jnp.log, "sqrt": jnp.sqrt, "tanh": jnp.tanh,
    "relu": jax.nn.relu, "sigmoid": jax.nn.sigmoid, "negative": jnp.negative,
    "sin": jnp.sin, "cos": jnp.cos,
}
REDUCE_FUNCS = {
    "mean": jnp.mean, "sum": jnp.sum, "max": jnp.max, "min": jnp.min, "prod": jnp.prod,
    "std": jnp.std, "var": jnp.var, "median": jnp.median,
}
ACTIVATIONS = {"relu": jax.nn.relu, "tanh": jnp.tanh, "sigmoid": jax.nn.sigmoid,
               "gelu": jax.nn.gelu, "identity": lambda v: v}


def load(path):
    """jax-skills load(): dict of arrays for .npz, one array for .npy."""
    if path.endswith(".npz"):
        with np.load(path, allow_pickle=False) as z:
            return {k: jnp.asarray(z[k]) for k in z.files}
    return jnp.asarray(np.load(path, allow_pickle=False))


def get(data, key, what):
    if not isinstance(data, dict):
        return data
    if key is None or key not in data:
        raise KeyError(f"{what}: key {key!r} not in file (has {sorted(data)})")
    return data[key]


def need(cond, msg):
    if not cond:
        raise ValueError(msg)


def op_reduce(data, p):
    a = get(data, p.get("key"), "array")
    func = p.get("func", "mean")
    need(func in REDUCE_FUNCS, f"unsupported reduce func {func!r}; supported {sorted(REDUCE_FUNCS)}")
    axis = p.get("axis")
    if axis is not None:
        axis = int(axis)
        need(-a.ndim <= axis < a.ndim, f"axis {axis} out of range for shape {a.shape}")
    out = jax.jit(lambda v: REDUCE_FUNCS[func](v, axis=axis))(a)
    exp = () if axis is None else tuple(s for i, s in enumerate(a.shape) if i != axis % a.ndim)
    return out, exp


def op_map(data, p):
    a = get(data, p.get("key"), "array")
    func = p.get("func", "square")
    need(func in MAP_FUNCS, f"unsupported map func {func!r}; supported {sorted(MAP_FUNCS)}")
    f = MAP_FUNCS[func]
    # vectorised with vmap over the leading axis, as jax-skills map_op does
    out = jax.jit(jax.vmap(f))(a) if a.ndim >= 1 else jax.jit(f)(a)
    return out, tuple(a.shape)


def op_logistic_grad(data, p):
    x = get(data, p.get("x_key"), "x").astype(jnp.float32)
    y = get(data, p.get("y_key"), "y").astype(jnp.float32)
    need(x.ndim == 2, f"x must be 2-D (N, D), got {x.shape}")
    y = y.reshape(-1)
    need(y.shape[0] == x.shape[0], f"y has {y.shape[0]} labels but x has {x.shape[0]} rows")
    if p.get("w_key") is None:
        w = jnp.zeros(x.shape[1], jnp.float32)
    else:
        w = get(data, p["w_key"], "w").astype(jnp.float32)
    need(w.shape == (x.shape[1],), f"w shape {w.shape} must be ({x.shape[1]},)")
    if p.get("labels") == "01":
        y = 2.0 * y - 1.0

    def loss(w):
        logits = x @ w
        return jnp.mean(jnp.logaddexp(0.0, -y * logits))  # stable log(1 + exp(-y*z))

    return jax.jit(jax.grad(loss))(w), tuple(w.shape)


def op_rnn_scan(data, p):
    seq = get(data, p.get("seq_key"), "seq")
    Wx, Wh, b = get(data, p.get("Wx_key"), "Wx"), get(data, p.get("Wh_key"), "Wh"), get(data, p.get("b_key"), "b")
    need(seq.ndim == 2, f"seq must be (T, D), got {seq.shape}")
    H = Wh.shape[0]
    need(Wh.shape == (H, H), f"Wh must be square, got {Wh.shape}")
    need(b.shape == (H,), f"b shape {b.shape} must be ({H},)")
    h0 = jnp.zeros(H, seq.dtype) if p.get("h0_key") is None else get(data, p["h0_key"], "h0")
    need(h0.shape == (H,), f"h0 shape {h0.shape} must be ({H},)")
    wx_left = p.get("wx_side", "left") == "left"
    wh_left = p.get("wh_side", "left") == "left"
    act = ACTIVATIONS[p.get("activation", "tanh")]
    xin = lambda xt: Wx @ xt if wx_left else xt @ Wx
    hin = lambda h: Wh @ h if wh_left else h @ Wh
    need((Wx.shape[1] if wx_left else Wx.shape[0]) == seq.shape[1],
         f"Wx {Wx.shape} does not fit inputs of size {seq.shape[1]} with wx_side={p.get('wx_side', 'left')}")

    def step(h, xt):
        h_new = act(xin(xt) + hin(h) + b)
        return h_new, h_new

    _, hseq = jax.jit(lambda h, s: jax.lax.scan(step, h, s))(h0, seq)
    return hseq, (seq.shape[0], H)


def op_mlp_forward(data, p):
    x = get(data, p.get("x_key"), "x")
    layers = p.get("layers") or []
    need(layers, "layers is empty")
    Ws = [get(data, wk, "W") for wk, _ in layers]
    bs = [None if bk is None else get(data, bk, "b") for _, bk in layers]
    right = p.get("w_side", "right") == "right"
    act = ACTIVATIONS[p.get("activation", "relu")]

    def mlp(x):
        h = x
        for i, (W, b) in enumerate(zip(Ws, bs)):
            h = h @ W if right else h @ W.T
            if b is not None:
                h = h + b
            if i < len(Ws) - 1:  # activation on hidden layers only; output layer stays linear
                h = act(h)
        return h

    out = jax.jit(mlp)(x)
    last = Ws[-1].shape[-1] if right else Ws[-1].shape[0]
    return out, tuple(x.shape[:-1]) + (last,)


OPS = {"reduce": op_reduce, "map": op_map, "logistic_grad": op_logistic_grad,
       "rnn_scan": op_rnn_scan, "mlp_forward": op_mlp_forward}


def run_one(item):
    res = {"id": item.get("id"), "op": item.get("op"), "output": item.get("output")}
    try:
        op = item.get("op")
        need(op in OPS, f"unsupported op {op!r}; supported {sorted(OPS)}")
        out, expected = OPS[op](load(item["input"]), item.get("params") or {})
        out = np.asarray(jax.device_get(out))
        need(out.shape == tuple(expected), f"result shape {out.shape} != expected {tuple(expected)}")
        need(np.all(np.isfinite(out)), "result contains NaN/Inf")
        path = item["output"]
        os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
        np.save(path, out)  # jax-skills save(): np.save(path, np.array(data))
        saved = path if path.endswith(".npy") else path + ".npy"
        back = np.load(saved)
        need(back.shape == out.shape and np.array_equal(back, out), "reloaded file differs from result")
        flat = out.reshape(-1)
        res.update(status="ok", saved=saved, shape=list(out.shape), dtype=str(out.dtype),
                   min=float(flat.min()) if flat.size else None, max=float(flat.max()) if flat.size else None,
                   preview=[round(float(v), 6) for v in flat[:6]])
    except Exception as e:
        res.update(status="error", error=f"{type(e).__name__}: {e}")
    return res


def main():
    state = json.load(sys.stdin).get("currentState", {})
    plan = state.get("plan") or []
    results = [run_one(item) for item in plan]
    print(json.dumps({"results": results, "all_ok": bool(results) and all(r["status"] == "ok" for r in results)}))


if __name__ == "__main__":
    main()

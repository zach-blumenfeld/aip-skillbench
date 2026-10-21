"""JAX operation library (adapted from source/jax-skills/jax_skills.py).

Every op validates shapes, runs in JAX, and returns a jax.Array; conversion to NumPy
happens only in save(). JAX's default float32 precision is kept (x64 stays off) so
results match a plain `jnp` reference computed the same way.
"""
import os

import jax
import jax.numpy as jnp
import numpy as np


# ---------- load / save ----------

def load(path):
    """.npy -> jax array; .npz -> dict of name -> jax array."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"input file not found: {path}")
    if path.endswith(".npz"):
        with np.load(path) as z:
            return {k: jnp.asarray(z[k]) for k in z.files}
    if path.endswith(".npy"):
        return jnp.asarray(np.load(path))
    raise ValueError(f"unsupported input format (need .npy or .npz): {path}")


def save(data, path):
    """Save to .npy (np.save appends .npy if missing). Creates parent folders."""
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    np.save(path, np.asarray(data))


# ---------- map (elementwise, via vmap) ----------

MAP_FNS = {
    "square": lambda v: v * v,
    "cube": lambda v: v * v * v,
    "sqrt": jnp.sqrt,
    "abs": jnp.abs,
    "exp": jnp.exp,
    "log": jnp.log,
    "log1p": jnp.log1p,
    "negative": jnp.negative,
    "reciprocal": lambda v: 1.0 / v,
    "relu": jax.nn.relu,
    "sigmoid": jax.nn.sigmoid,
    "tanh": jnp.tanh,
    "sin": jnp.sin,
    "cos": jnp.cos,
    "double": lambda v: 2 * v,
    "increment": lambda v: v + 1,
}


def map_op(array, fn):
    if fn not in MAP_FNS:
        raise ValueError(f"unknown map fn {fn!r}; supported: {sorted(MAP_FNS)}")
    array = jnp.asarray(array)
    f = MAP_FNS[fn]
    if array.ndim == 0:
        return f(array)
    # vmap over the leading axis; the elementwise fn handles the rest.
    return jax.vmap(f)(array)


# ---------- reduce ----------

REDUCE_FNS = {
    "mean": jnp.mean,
    "sum": jnp.sum,
    "max": jnp.max,
    "min": jnp.min,
    "prod": jnp.prod,
    "std": jnp.std,
    "var": jnp.var,
    "median": jnp.median,
    "argmax": jnp.argmax,
    "argmin": jnp.argmin,
    "norm": lambda a, axis=None: jnp.linalg.norm(a, axis=axis),
}


def reduce_op(array, fn, axis):
    if fn not in REDUCE_FNS:
        raise ValueError(f"unknown reduce fn {fn!r}; supported: {sorted(REDUCE_FNS)}")
    array = jnp.asarray(array)
    if axis is not None and not (-array.ndim <= axis < array.ndim):
        raise ValueError(f"axis {axis} out of range for array of shape {array.shape}")
    return REDUCE_FNS[fn](array, axis=axis)


# ---------- logistic-loss gradient ----------

def logistic_grad(x, y, w):
    """grad_w of mean(log(1 + exp(-y * (x @ w)))), labels y in {-1, +1}.
    logaddexp(0, z) == log(1 + exp(z)) without overflow."""
    x, y, w = jnp.asarray(x), jnp.asarray(y), jnp.asarray(w)
    if x.ndim != 2:
        raise ValueError(f"x must be 2-D (N, D), got {x.shape}")
    if w.shape != (x.shape[1],):
        raise ValueError(f"w must have shape ({x.shape[1]},), got {w.shape}")
    if y.shape != (x.shape[0],):
        raise ValueError(f"y must have shape ({x.shape[0]},), got {y.shape}")

    def loss(w):
        logits = x @ w
        return jnp.mean(jnp.logaddexp(0, -y * logits))

    return jax.grad(loss)(w)


# ---------- RNN forward pass with lax.scan ----------

def rnn_scan(seq, Wx, Wh, b, h0=None):
    """h_t = tanh(Wx @ x_t + Wh @ h_{t-1} + b); returns every hidden state, shape (T, H).
    h0 is the provided initial state (npz key `init`/`h0`); zeros only when absent."""
    seq, Wx, Wh, b = map(jnp.asarray, (seq, Wx, Wh, b))
    if seq.ndim != 2:
        raise ValueError(f"seq must be 2-D (T, input_dim), got {seq.shape}")
    H = Wh.shape[0]
    if Wh.shape != (H, H):
        raise ValueError(f"Wh must be square, got {Wh.shape}")
    if Wx.shape != (H, seq.shape[1]):
        raise ValueError(f"Wx must be (H={H}, input_dim={seq.shape[1]}), got {Wx.shape}")
    if b.shape != (H,):
        raise ValueError(f"b must be ({H},), got {b.shape}")
    h0 = jnp.zeros(H, dtype=seq.dtype) if h0 is None else jnp.asarray(h0)
    if h0.shape != (H,):
        raise ValueError(f"initial state must be ({H},), got {h0.shape}")

    def step(h, x):
        h_new = jnp.tanh(Wx @ x + Wh @ h + b)
        return h_new, h_new

    _, hseq = jax.lax.scan(step, h0, seq)
    return hseq


# ---------- JIT-compiled MLP ----------

ACTIVATIONS = {"relu": jax.nn.relu, "tanh": jnp.tanh, "sigmoid": jax.nn.sigmoid,
               "gelu": jax.nn.gelu, "identity": lambda v: v}


def mlp(X, weights, biases, activation="relu"):
    """Dense layers x @ W + b; activation between layers, none after the last (logits)."""
    if activation not in ACTIVATIONS:
        raise ValueError(f"unknown activation {activation!r}; supported: {sorted(ACTIVATIONS)}")
    if len(weights) != len(biases) or not weights:
        raise ValueError("need one bias per weight matrix and at least one layer")
    X = jnp.asarray(X)
    weights = [jnp.asarray(W) for W in weights]
    biases = [jnp.asarray(bb) for bb in biases]
    d = X.shape[-1]
    for i, (W, bb) in enumerate(zip(weights, biases), 1):
        if W.ndim != 2 or W.shape[0] != d or bb.shape != (W.shape[1],):
            raise ValueError(f"layer {i}: W {W.shape} / b {bb.shape} do not chain from width {d}")
        d = W.shape[1]
    act = ACTIVATIONS[activation]

    def forward(x, Ws, bs):
        h = x
        for i, (W, bb) in enumerate(zip(Ws, bs)):
            h = jnp.dot(h, W) + bb
            if i < len(Ws) - 1:
                h = act(h)
        return h

    return jit_run(forward, (X, weights, biases))


def jit_run(fn, args):
    return jax.jit(fn)(*args)


# ---------- npz key roles ----------

# Role -> accepted npz key names, matched case-sensitively first, then case-insensitively.
ROLE_CANDIDATES = {
    "logistic_grad": {"x": ["x", "X", "features", "inputs", "data"],
                      "y": ["y", "Y", "labels", "targets", "t"],
                      "w": ["w", "W", "weights", "theta", "true_w", "w_init", "w0"]},
    "rnn_scan": {"seq": ["seq", "x", "xs", "inputs", "sequence", "X"],
                 "Wx": ["Wx", "W_x", "wx", "W_xh", "Wxh"],
                 "Wh": ["Wh", "W_h", "wh", "W_hh", "Whh"],
                 "b": ["b", "bias", "b_h", "bh"],
                 "init": ["init", "h0", "h_0", "h_init", "initial_state", "hidden"]},
}
OPTIONAL_ROLES = {"rnn_scan": {"init"}}


def find_key(names, candidates):
    for c in candidates:
        if c in names:
            return c
    lower = {n.lower(): n for n in names}
    for c in candidates:
        if c.lower() in lower:
            return lower[c.lower()]
    return None


def resolve_roles(op, names):
    """Map each role of `op` to an npz key. Returns (keys, missing_required_roles)."""
    keys, missing = {}, []
    for role, cands in ROLE_CANDIDATES.get(op, {}).items():
        k = find_key(names, cands)
        if k is not None:
            keys[role] = k
        elif role not in OPTIONAL_ROLES.get(op, set()):
            missing.append(role)
    return keys, missing


def mlp_layers(names):
    """Pair W1..Wn with b1..bn (any case). Returns (weight_keys, bias_keys) in layer order."""
    import re
    ws, bs = {}, {}
    for n in names:
        m = re.fullmatch(r"[Ww]_?(\d+)", n)
        if m:
            ws[int(m.group(1))] = n
        m = re.fullmatch(r"[Bb]_?(\d+)", n)
        if m:
            bs[int(m.group(1))] = n
    idx = sorted(ws)
    return [ws[i] for i in idx], [bs.get(i) for i in idx]


def mlp_input_key(names):
    return find_key(names, ["X", "x", "inputs", "data", "features"])

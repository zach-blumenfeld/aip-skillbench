# JAX ops reference (compiled from the curated jax-skills)

Load this when a plan entry is `unknown`, AMBIGUOUS, or a compute result failed, and you must
set `op`/`params` by hand.

## The original jax-skills API (source/jax-skills/jax_skills.py)

| skill        | function                      | math / behaviour                                                    |
|--------------|-------------------------------|---------------------------------------------------------------------|
| jax-load     | `load(path)`                  | `.npz` -> `dict(np.load(path))`; `.npy` -> `jnp.array(np.load(path))` |
| jax-save     | `save(data, path)`            | `np.save(path, np.array(data))` (`.npy`; np.save appends `.npy` if missing) |
| jax-map      | `map_op(array, "square")`     | `jax.vmap(lambda x: x * x)(array)`; only "square" in the original     |
| jax-reduce   | `reduce_op(array, "mean", axis)` | `jnp.mean(array, axis=axis)`; only "mean" in the original           |
| jax-grad     | `logistic_grad(x, y, w)`      | `jax.grad(lambda w: mean(logaddexp(0, -y * (x @ w))))(w)`           |
| jax-scan     | `rnn_scan(seq, Wx, Wh, b)`    | `lax.scan`, `h_t = tanh(Wx @ x_t + Wh @ h_{t-1} + b)`, `h0 = zeros(Wh.shape[0])`, returns all h_t |
| jax-jit      | `jit_run(fn, args)`           | `jax.jit(fn)(*args)`                                                |

Unsupported op names raise `ValueError` in the original; compute.py reports them per task instead.

## Plan entry shape (what scripts/compute.py consumes)

```json
{"id": "...", "input": "/abs/in.npz", "output": "/abs/out.npy", "op": "<op>", "params": {...}}
```

| op            | params                                                                                          |
|---------------|-------------------------------------------------------------------------------------------------|
| reduce        | `key` (npz key, null for .npy), `func` (mean,sum,max,min,prod,std,var,median), `axis` (int or null = all) |
| map           | `key`, `func` (square,abs,exp,log,sqrt,tanh,relu,sigmoid,negative,sin,cos)                     |
| logistic_grad | `x_key`, `y_key`, `w_key` (null = zeros(D)), `labels` ("pm1" or "01")                          |
| rnn_scan      | `seq_key`, `Wx_key`, `Wh_key`, `b_key`, `h0_key` (null = zeros), `wx_side`/`wh_side` ("left" = W @ v, "right" = v @ W), `activation` |
| mlp_forward   | `x_key`, `layers` ([[W1,b1],[W2,b2],...]), `activation` (hidden layers only), `w_side` ("right" = x @ W, "left" = x @ W.T) |

## Interpretation rules

- **Axis wording.** "mean of each row" / "row-wise" / "per row" = one value per row = reduce over the
  column axis = `axis=1` for a 2-D array (result length = number of rows). "each column" / "per
  feature" = `axis=0`. The original SKILL.md example uses `axis=0`; do not copy it blindly.
- **Elementwise map.** vmap over the leading axis gives the same result as applying the function to
  every element; the shape is preserved.
- **Logistic loss** is `mean(log(1 + exp(-y * (x @ w))))` with labels in {-1, +1}. Use
  `logaddexp(0, -y*z)` for numerical stability, never `log(1 + exp(...))`. Evaluate the gradient at the
  `w` stored in the file (it is the point of evaluation, even if named `true_w`). Labels in {0, 1}
  must be mapped with `2y - 1` first.
- **RNN scan.** Scan over axis 0 of `seq` (time). If the file has an initial state (`init`, `h0`),
  use it as the carry; otherwise zeros. Output is every hidden state stacked, shape `(T, H)`, not just
  the last one. With square `Wx`, orientation cannot be read from shapes: keep `Wx @ x_t`.
  If `Wx` is stored `(in, hidden)` the data uses the row-vector convention: `x_t @ Wx + h @ Wh + b`.
  Never mix the two conventions.
- **2-layer MLP.** `relu(x @ W1 + b1) @ W2 + b2`, no activation on the output, wrapped in `jax.jit`.
  Weights stored `(in, out)` multiply on the right. Output shape `(N, out_dim)`.
- **dtype.** JAX defaults to float32; keep it. Save with `np.save` after `np.asarray(...)`.
- **Side effects.** Keep functions passed to vmap/scan/jit pure (no prints, no Python-side mutation).
- **JIT.** Shapes must stay consistent across calls; jit pays off for compute-heavy or repeated calls.

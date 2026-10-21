# JAX ops reference (for custom / errored tasks)

Load this when writing JAX code yourself: a `custom` task, or a task the compute
script reported as `error`. The catalog ops live in `scripts/jax_skills.py`; import it
(`sys.path.insert(0, "<skill>/scripts"); import jax_skills as jx`) rather than
re-implementing them.

## Library API (`scripts/jax_skills.py`)

| Function | Does | Returns |
|---|---|---|
| `load(path)` | `.npy` → jax array; `.npz` → dict name → jax array | array or dict |
| `save(data, path)` | `np.save(path, np.asarray(data))`, creates parent folders | — |
| `map_op(array, fn)` | elementwise fn via `jax.vmap` over the leading axis | same shape |
| `reduce_op(array, fn, axis)` | `jnp.<fn>(array, axis=axis)` | reduced array |
| `logistic_grad(x, y, w)` | `jax.grad` of `mean(logaddexp(0, -y * (x @ w)))` w.r.t. w | (D,) |
| `rnn_scan(seq, Wx, Wh, b, h0=None)` | `lax.scan` of `h = tanh(Wx @ x + Wh @ h + b)`; h0 zeros if None | (T, H) all states |
| `mlp(X, weights, biases, activation)` | jitted dense stack, activation between layers, linear last | (N, out) |
| `jit_run(fn, args)` | `jax.jit(fn)(*args)` | fn's result |

## Formulas and conventions

- Logistic loss: `mean(log(1 + exp(-y * (x @ w))))`, labels in {-1, +1}. Write
  `log(1 + exp(z))` as `jnp.logaddexp(0, z)`: same value, no overflow. Differentiate
  with `jax.grad(loss)(w)` at the `w` stored in the file. Use the formula as written
  even if labels look like {0, 1}; mention it in your answer.
- RNN: weights act on column vectors (`Wx @ x_t`, `Wh @ h`), so `Wx` is (H, input_dim)
  and `Wh` is (H, H). Return the stacked hidden states (the scan's `ys`), not just the
  final carry, unless the description asks for the final state only. Seed the carry
  with the file's initial state (`init` / `h0`) when it has one.
- MLP: `relu(x @ W1 + b1) @ W2 + b2`; no softmax or activation on the output unless the
  description asks. Wrap the forward function in `jax.jit` and call it.
- Row/column wording: "each row" → reduce axis 1 (one value per row); "each column" →
  axis 0.
- Vectorization: "using vectorization" / "vmap" means `jax.vmap(f)(x)` with an
  elementwise `f`; the output shape equals the input shape.

## Requirements carried from the source skill

- Arrays must be JAX-compatible (`jnp.asarray`) or convertible from Python lists.
- Validate input types and shapes before computing; fail with a message naming the
  offending array and its shape.
- Keep numerically stable forms (`logaddexp`, `jax.nn.sigmoid`, `jax.nn.log_softmax`).
- Prefer JAX arrays for every operation; convert to NumPy only when saving.
- Keep functions passed to `vmap`, `scan`, and `jit` free of side effects (no prints,
  no appends to outer lists, no file I/O).
- JIT needs consistent input shapes across calls; recompiles on new shapes.
- Save results as `.npy` at the exact output path the task names (the grader reads
  that file). `.npz`, JSON, or pickle only if the task's output path says so.

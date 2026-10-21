The compute script ran the plan and saved what it could. Some tasks are not done:
their `status` is `custom` (no catalog op fits) or `error` (the op raised; nothing was
saved for that task). Finish each of them with JAX.

Plan:

{plan}

Compute results:

{results}

For every result whose status is not `ok`:

1. If it is an `error`, read the message first. A wrong npz key or axis in the plan
   is fixed by writing the corrected computation directly; do not just retry.
2. Write a short Python script (in a scratch folder, never inside the skill folder) that
   loads the task's `input` with numpy (`np.load`; .npz gives named arrays), converts
   with `jnp.asarray`, computes the description with JAX (`jax.numpy`, `jax.vmap`,
   `jax.grad`, `jax.lax.scan`, `jax.jit` as the description asks), and saves with
   `np.save(output, np.asarray(result))` to the task's exact `output` path.
   You may `import jax_skills` from this skill's `scripts/` folder (add it to sys.path)
   for load/save and the catalog ops.
3. Keep JAX's default float32 (do not enable x64). Do not convert to NumPy before the
   final save. Keep functions passed to vmap/scan/jit free of side effects.
4. Run it, then reload the saved file and check its shape against what the description
   implies and that it holds no NaN/Inf.

Answer with `custom_results`: one object per task you finished,
`{{"id", "output", "shape", "dtype", "how"}}`, where `how` is one line on the computation.

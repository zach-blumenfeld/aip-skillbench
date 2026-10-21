Confirm the op plan for every task in problem.json. The inspect script read each task's
input file and proposed an op from the catalog; you check each proposal against the
task's `description` and the input `arrays` (names, shapes), fix it where it is wrong,
and return the plan the compute script will execute.

Tasks (with suggested_op, suggested_args, notes):

{tasks}

For each task, emit one plan entry:

    {{"id": ..., "op": ..., "args": {{...}}, "input": <task input path>, "output": <task output path>}}

Keep `input` and `output` exactly as the task gives them (already absolute). One entry
per task, in the same order; never drop a task.

Op catalog (`op` → `args`):

- `reduce` → `{{"fn": mean|sum|max|min|prod|std|var|median|argmax|argmin|norm, "axis": int|null, "array_key"?: str}}`.
  "each row" / "per row" / "row-wise" → axis 1 on a 2-D array (one value per row, shape (rows,)).
  "each column" → axis 0. No axis named, or "all elements" → null (scalar).
- `map` → `{{"fn": square|cube|sqrt|abs|exp|log|log1p|negative|reciprocal|relu|sigmoid|tanh|sin|cos|double|increment, "array_key"?: str}}`.
  Elementwise via jax.vmap; output shape equals input shape.
- `logistic_grad` → `{{"keys": {{"x": .., "y": .., "w": ..}}}}`. Gradient w.r.t. w of
  mean(log(1 + exp(-y * (x @ w)))), computed with jax.grad and logaddexp; output shape (D,).
- `rnn_scan` → `{{"keys": {{"seq": .., "Wx": .., "Wh": .., "b": .., "init"?: ..}}}}`.
  h_t = tanh(Wx @ x_t + Wh @ h_{{t-1}} + b) with jax.lax.scan; output is every hidden
  state, shape (T, H). Map `init` whenever the npz has an initial state (`init`, `h0`);
  zeros are used only when it has none.
- `mlp` → `{{"keys": {{"X": .., "weights": [W1, ..., Wn], "biases": [b1, ..., bn]}}, "activation": relu|tanh|sigmoid|gelu|identity}}`.
  x @ W + b per layer, activation between layers, no activation on the last layer
  (raw outputs), the whole forward pass under jax.jit. relu unless the description names another.
- `custom` → `{{}}` plus a `"spec"` string saying exactly what to compute, when no catalog
  op fits the description. You will write that JAX code yourself in a later step.

Use `array_key` only when a reduce/map task's input is an .npz (name the array to use).
Read the description literally: "mean of each row" of a (10, 5) array is shape (10,),
not (5,). If the description asks for something the catalog op does not compute
exactly (a different loss, an output activation, a softmax, only the final hidden
state), choose `custom` rather than forcing a near-miss op.

Answer with `plan`: the list of entries.

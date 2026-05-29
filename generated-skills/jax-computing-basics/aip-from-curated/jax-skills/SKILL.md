---
name: jax-skills
description: "High-performance numerical computing and machine learning workflows using JAX. Supports array loading/saving, elementwise vmap operations, axis reductions, automatic differentiation (logistic loss), scan-based RNN forward passes, and JIT compilation of arbitrary functions (including 2-layer MLPs). Use when the task asks to solve numerical/ML subtasks listed in a problem.json file, or any time JAX primitives (jnp, jax.grad, jax.lax.scan, jax.jit, jax.vmap) are the right tool."
license: Proprietary. LICENSE.txt has complete terms
compatibility: Requires Python 3.11+, jax, jaxlib, numpy. CPU-only is sufficient for the curated benchmark.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a3
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a3/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Solve numerical computing and ML subtasks with JAX using the bundled
  jax_skills toolkit. The toolkit (scripts/jax_skills.py) ships seven
  primitive ops — load, save, map_op, reduce_op, logistic_grad, rnn_scan,
  jit_run — covering array IO, vectorized maps, axis reductions, automatic
  differentiation, scan-based RNN forward passes, and JIT compilation.
  Prefer JAX-native primitives (jnp.array, jax.grad, jax.lax.scan, jax.jit,
  jax.vmap) end-to-end; only convert to NumPy when writing files. The
  bundled solve_problems.py orchestrator handles the closed set of
  benchmark subtask ids (basic_reduce, map_square, grad_logistic, scan_rnn,
  jit_mlp) in one command.

trigger_when:
  - The task supplies a problem.json that lists subtasks with id, description, input, and output fields.
  - The user asks to compute row/column reductions (mean, etc.) over a JAX array.
  - The user asks to apply an elementwise function (square, etc.) via jax.vmap.
  - The user asks for the gradient of a logistic loss with respect to weights.
  - The user asks for an RNN forward pass via jax.lax.scan.
  - The user asks to JIT-compile a function — including small MLPs — with jax.jit.
  - The user asks to load .npy or .npz files into JAX arrays, or to save a JAX result to .npy.

do_not_use_when:
  - The task explicitly requires PyTorch, TensorFlow, or another non-JAX framework.
  - The work is pure NumPy/SciPy with no need for autodiff, vmap, scan, or JIT.
  - The subtask id falls outside the dispatch set AND cannot be expressed with the primitives in jax_skills.py — write standard JAX code directly.

scope_and_approval: >
  Read input arrays from the paths the task supplies; write only the output
  files named by each subtask's `output` field. Do not modify problem.json,
  the data/ directory, or any reference/ directory. All JAX operations are
  pure functions with no network or filesystem side effects beyond the
  declared output writes.

steps:
  - name: locate-skill-root
    description: >
      Resolve the absolute path of this skill folder (the directory
      containing SKILL.md). The toolkit and orchestrator live under
      scripts/ relative to that root. Typical mount point in the
      benchmark container is /app/skills/jax-skills; do not hardcode —
      inspect the environment.

  - name: load-toolkit
    description: >
      Insert scripts/ onto sys.path, then `import jax_skills as jx`. The
      module exposes load, save, map_op, reduce_op, logistic_grad,
      rnn_scan, jit_run. Source of truth is scripts/jax_skills.py.
    script: scripts/jax_skills.py
    depends_on: [locate-skill-root]
    outputs:
      - name: jx
        type: object
        description: The imported jax_skills module bound as `jx`.

  - name: read-problem
    description: >
      Open problem.json (default cwd; the harness mounts it at /app/problem.json
      in the benchmark) and parse it as a list of {id, description, input, output}
      objects. The IDs in this benchmark are basic_reduce, map_square,
      grad_logistic, scan_rnn, jit_mlp.
    outputs:
      - name: tasks
        type: list[object]
        description: Ordered subtasks to process.

  - name: run-orchestrator
    description: >
      Preferred path for the curated benchmark. Run
      `python scripts/solve_problems.py problem.json <output_dir> <input_base_dir>`
      to dispatch every known subtask id to its operation and write outputs
      verbatim. In the benchmark container, output_dir and input_base_dir
      are both /app, so `cd /app && python <skill>/scripts/solve_problems.py`
      works. The script raises ValueError on any unknown id; fall through
      to the manual `compute` step in that case.
    script: scripts/solve_problems.py
    depends_on: [load-toolkit, read-problem]
    inputs:
      - name: tasks
        type: list[object]
    outputs:
      - name: outputs-written
        type: list[string]
        description: Absolute paths of files written.

  - name: compute
    description: >
      Manual fallback. For each subtask, pick exactly one branch by `id`
      (preferred) or by interpreting `description` (fallback when an id is
      unfamiliar). Loaders, expected .npz keys, and op signatures are
      pinned in the one_of entries below — follow them exactly so outputs
      match the reference within rtol=1e-5, atol=1e-6.
    depends_on: [load-toolkit, read-problem]
    inputs:
      - name: jx
        type: object
      - name: tasks
        type: list[object]
    outputs:
      - name: results
        type: list[object]
        description: One JAX array per subtask, in subtask order.
    one_of:
      - "basic_reduce — Description: row mean of x. Load x = jx.load(input) (.npy). Compute jx.reduce_op(x, 'mean', axis=1). Output shape (N,)."
      - "map_square — Description: elementwise square via vectorization. Load x = jx.load(input) (.npy). Compute jx.map_op(x, 'square') — backed by jax.vmap(lambda v: v*v). Output shape == input shape."
      - "grad_logistic — Description: gradient of logistic loss. Load d = jx.load(input) (.npz) — keys x, y, w. Compute jx.logistic_grad(d['x'], d['y'], d['w']). Loss is mean(logaddexp(0, -y * (x @ w))). Output shape (D,)."
      - "scan_rnn — Description: RNN forward via scan. Load d = jx.load(input) (.npz) — keys seq, Wx, Wh, b (data also stores init but jax_skills.rnn_scan uses an internal jnp.zeros init). Compute jx.rnn_scan(d['seq'], d['Wx'], d['Wh'], d['b']). Output is the sequence of hidden states with tanh activation."
      - "jit_mlp — Description: JIT-compile a 2-layer MLP. Load d = jx.load(input) (.npz) — keys X, W1, b1, W2, b2. Define mlp(X,W1,b1,W2,b2) = relu(X @ W1 + b1) @ W2 + b2 using jax.nn.relu. Compute jx.jit_run(mlp, (d['X'], d['W1'], d['b1'], d['W2'], d['b2']))."

  - name: save-output
    description: >
      For each computed result, write to the subtask's `output` path with
      jx.save (np.save under the hood). The orchestrator already does
      this; only invoke explicitly when running the manual compute fallback.
      Output dtype follows the input (float32 in the curated benchmark) —
      do not upcast.
    script: scripts/jax_skills.py
    depends_on: [run-orchestrator]
    inputs:
      - name: results
        type: list[object]
      - name: tasks
        type: list[object]
    outputs:
      - name: output-paths
        type: list[string]

modes:
  - name: orchestrated
    body: >
      Default for the curated benchmark. Run
      `python scripts/solve_problems.py problem.json /app /app` from any
      working directory after locating the skill. One command writes every
      expected output file; the test harness then runs pytest against the
      reference arrays.
  - name: manual
    body: >
      Use when problem.json contains an id outside the dispatch set, or
      when debugging a single subtask. Import jax_skills directly, follow
      the `compute` step's one_of entries for loader keys and op
      signatures, then call jx.save per subtask.

scenarios:
  - need: Five-subtask problem.json with the canonical ids.
    context: >
      Mounted skill at /app/skills/jax-skills; problem.json + data/ at /app.
      All input files are float32.
    action: >
      `python /app/skills/jax-skills/scripts/solve_problems.py /app/problem.json /app /app`
    outcome: >
      basic_reduce.npy, map_square.npy, grad_logistic.npy, scan_rnn.npy,
      jit_mlp.npy written under /app; pytest passes shape and allclose checks.
  - need: A new subtask id `softmax_row` appears in problem.json.
    context: >
      Orchestrator raises ValueError because softmax_row is not in DISPATCH.
    action: >
      Load the input with jx.load, compute jnp.exp(x) / jnp.sum(jnp.exp(x), axis=1, keepdims=True)
      (or use jax.nn.softmax), then jx.save to the declared output path.
      Run the orchestrator first for the known ids, then handle the new one
      manually.
    outcome: Mixed orchestrator + manual run completes all subtasks.

anti_patterns:
  - Re-implementing reduce_op, map_op, logistic_grad, or rnn_scan inline when jax_skills already supplies them — duplicated code drifts from the reference quickly.
  - Using a non-tanh activation in the RNN scan, or a non-zero initial hidden state — both diverge numerically from the reference.
  - Using a non-relu activation in the MLP, or shuffling the layer order — the reference is `relu(X @ W1 + b1) @ W2 + b2`.
  - Saving as a list/dict pickle or .npz when the task asks for .npy — the verifier loads with np.load and compares with np.allclose on a single array.
  - Upcasting float32 inputs to float64; the reference arrays are float32 and tolerance is rtol=1e-5, atol=1e-6.
  - Introducing side effects (prints to stdout that the verifier parses, file writes outside the declared output paths) inside functions passed to jax.vmap, jax.lax.scan, or jax.jit — JAX traces these and the behavior is undefined.
  - Validating array shapes loosely (e.g., assuming axis=0 for reduce_op when the description says row mean — that is axis=1 for a 2-D matrix).
  - Calling jx.load on a .npz expecting a single array — it returns a dict; index it by key.
```

#!/usr/bin/env python3
"""Solve every subtask listed in a problem.json file using the jax_skills toolkit.

Each subtask is dispatched by its `id` field to a fixed operation:

  basic_reduce  -> jx.reduce_op(x, "mean", axis=1)
  map_square    -> jx.map_op(x, "square")
  grad_logistic -> jx.logistic_grad(x, y, w)            (npz keys: x, y, w)
  scan_rnn      -> jx.rnn_scan(seq, Wx, Wh, b)          (npz keys: seq, Wx, Wh, b)
  jit_mlp       -> jx.jit_run(mlp, (X, W1, b1, W2, b2)) where
                   mlp(X, W1, b1, W2, b2) = relu(X @ W1 + b1) @ W2 + b2
                   (npz keys: X, W1, b1, W2, b2)

The dispatch table is closed over the IDs in the curated jax-computing-basics
benchmark. Unknown IDs raise ValueError — fall back to writing JAX code by hand
using the jax_skills primitives.

Usage:
    python solve_problems.py [PROBLEM_JSON] [OUTPUT_DIR] [INPUT_BASE_DIR]

Defaults:
    PROBLEM_JSON   = "problem.json"
    OUTPUT_DIR     = current working directory
    INPUT_BASE_DIR = current working directory (input paths are joined to this)

Output files are written as .npy files (np.save), preserving float32 dtype
from the source data so downstream allclose checks succeed.
"""

import json
import os
import sys
from pathlib import Path

import jax
import jax.numpy as jnp
import numpy as np

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import jax_skills as jx  # noqa: E402


def _load_npz(path):
    with np.load(path) as data:
        return {k: jnp.array(data[k]) for k in data.files}


def solve_basic_reduce(input_path):
    arr = jx.load(input_path)
    return jx.reduce_op(arr, "mean", axis=1)


def solve_map_square(input_path):
    arr = jx.load(input_path)
    return jx.map_op(arr, "square")


def solve_grad_logistic(input_path):
    d = _load_npz(input_path)
    return jx.logistic_grad(d["x"], d["y"], d["w"])


def solve_scan_rnn(input_path):
    d = _load_npz(input_path)
    return jx.rnn_scan(d["seq"], d["Wx"], d["Wh"], d["b"])


def solve_jit_mlp(input_path):
    d = _load_npz(input_path)

    def mlp(X, W1, b1, W2, b2):
        h = jax.nn.relu(jnp.dot(X, W1) + b1)
        return jnp.dot(h, W2) + b2

    return jx.jit_run(mlp, (d["X"], d["W1"], d["b1"], d["W2"], d["b2"]))


DISPATCH = {
    "basic_reduce": solve_basic_reduce,
    "map_square": solve_map_square,
    "grad_logistic": solve_grad_logistic,
    "scan_rnn": solve_scan_rnn,
    "jit_mlp": solve_jit_mlp,
}


def solve_all(problem_path, output_dir, input_base_dir):
    problem_path = Path(problem_path)
    output_dir = Path(output_dir)
    input_base_dir = Path(input_base_dir)

    with open(problem_path) as f:
        tasks = json.load(f)

    written = []
    for task in tasks:
        tid = task["id"]
        if tid not in DISPATCH:
            raise ValueError(
                f"Unknown task id {tid!r}. Supported ids: {sorted(DISPATCH)}. "
                "Write the computation by hand using jax_skills primitives."
            )
        in_path = input_base_dir / task["input"]
        result = DISPATCH[tid](str(in_path))
        out_path = output_dir / task["output"]
        out_path.parent.mkdir(parents=True, exist_ok=True)
        jx.save(result, str(out_path))
        written.append(str(out_path))
    return written


def main(argv):
    problem_path = argv[1] if len(argv) > 1 else "problem.json"
    output_dir = argv[2] if len(argv) > 2 else os.getcwd()
    input_base_dir = argv[3] if len(argv) > 3 else os.getcwd()
    written = solve_all(problem_path, output_dir, input_base_dir)
    for p in written:
        print(p)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

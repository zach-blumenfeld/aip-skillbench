# Fix what the evaluation found

Deliverable: `{deliverable_path}`

Verdict (failures block completion; warnings are worth fixing if cheap):

{verdict}

Last measurement: {verification}

Plan: {plan}

Requirements: {requirements}

Fix every failure, then re-run the same harness on the same inputs and worker counts and report a fresh `verification`. The usual causes:

- **Outputs differ.** Read the first differing path in `comparison_detail`. Float drift means the accumulation order changed: sum in the baseline's insertion order. Tie order means a sort ran over a different insertion order: sort by `(-score, original_position)` or build lists in baseline item order. Type mismatch means you returned a set where the baseline returns a dict, a list where it returns a tuple, or a new dataclass instead of the baseline's.
- **Too slow.** Compare the parent-side serial time against the pool time. If the merge dominates (Amdahl), make it linear, move per-item work into the workers, and shrink the pickled payloads. Send `(id, text)` pairs, not objects, and do not ship a large index with every task: use `plan.shared_input`. If the pool start-up dominates, add the sequential fast path for small inputs and `num_workers == 1`. If one chunk dominates, rebalance with LPT chunks submitted largest first.
- **Errors.** Pickling a lambda or nested function: move it to module level. Missing globals in workers under spawn/forkserver: use an explicit fork context or an initializer. A `__main__` guard missing in a script entry point under spawn.
- **Memory over limit.** Each worker is holding a full copy of the data: share read-only data via fork/initializer/shared memory, and chunk and discard.

Load `references/parallel-patterns.md`, `references/balancing-strategies.md`, `references/memory-patterns.md` or `references/map-reduce-index.md` as the failure requires.

Answer with `deliverable_path` and the new `verification` object, in the same shape as before.

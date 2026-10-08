Repair the JAX task plan for {meta.name}.

Current plan (one entry per task):
{plan}

Inputs found on disk (array keys, shapes, dtypes):
{inventory}

Survey warnings:
{plan_warnings}

Results of the last compute run, if any (an entry with status "error" carries the message):
{results}

Supported ops and params:
{assets[ops]}

Do this:
1. For each entry whose op, params, axis, array keys, or output path do not match its description and
   the arrays on disk, fix it. Load references/jax-ops.md for the interpretation rules (row/column
   axis wording, logistic label encoding, RNN initial state and orientation, MLP layout).
2. If a task genuinely needs an op compute.py does not support, keep the closest supported op only if
   it is mathematically identical; otherwise set op to "unknown" and explain in that entry's notes.
3. Keep every entry's `id`, `input` and `output` unless the output path itself is wrong.
4. Produce `plan` (the full corrected list, same entry shape) and set `plan_ok` to true.

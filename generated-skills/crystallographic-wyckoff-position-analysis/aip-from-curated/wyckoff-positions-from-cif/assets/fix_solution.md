# Fix the Wyckoff solution so verification passes

Verification of `{solution_path}` (function `{function_name}`, convention
`{output_convention}`) failed:

{verification}

Task request:

{task_request}

Canonical solution for reference (`__FUNCTION_NAME__` is the function name):

```python
{assets[solution_template]}
```

Do this:

1. Read each problem. "differs from canonical analysis" under the standard convention
   means the file drifted from the template: restore the template's logic exactly
   (letters from `dataset.wyckoffs`, counts of atoms, coordinates of the first atom
   in file order, `str(Rational(float(c)).limit_denominator(12))`, sorted keys,
   empty dicts when the dataset is None).
2. Under a custom convention, fix only what breaks the task's stated format; do not
   force the standard convention back in.
3. Edit `{solution_path}` in place. If this is the third failed attempt, overwrite it
   with the canonical solution (placeholder replaced by `{function_name}`) and adapt
   only the minimum the task requires.
4. Return `{{"solution_path": "<absolute path>", "solution_written": true}}`.

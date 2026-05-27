# taxonomy-tree-merge — source notes

This skill encodes the procedure for merging product-category taxonomies from
Amazon, Facebook, and Google Shopping into a single unified 5-level taxonomy.

## Source

- `instruction.md` — the original task instruction (unchanged).
- `procedure.schema.json` — the AIP procedure schema this skill validates
  against (bundled locally for self-containment; `$id` still points at the
  canonical URL).

## Schema choice

`procedure.schema.json` was chosen because the task is a deterministic, multi-
step pipeline (load → normalize → cluster → name → assign → output → validate),
with branching decisions (e.g., how to split an oversized cluster, what to do
with rare leaves) and a validation loop. The procedure schema's `steps`,
`decisions`, and `anti_patterns` fields cover every category of content the
instruction implies.

## Coverage map (instruction → skill body)

| Source content                                          | Where it lives in SKILL.md       |
|---------------------------------------------------------|----------------------------------|
| Goal: unify Amazon/Facebook/Google taxonomies           | `purpose`, `trigger_when`        |
| Input file paths under `/root/data/`                    | `steps[load-inputs]`             |
| `category_path` parsed by `" > "`                       | `steps[normalize-paths]`         |
| Rule 1 — 10–20 top-level, 3–20 children per parent      | `steps[cluster-...]`, `decisions`|
| Rule 2 — naming: source-derived, " \| ", ≤5 words, 70%  | `steps[name-clusters]`, `decisions` |
| Rule 3 — standardize text                               | `steps[normalize-paths]`         |
| Rule 4 — no parent/child name overlap                   | `steps[name-clusters]`, `anti_patterns` |
| Rule 5 — siblings <30% word overlap                     | `steps[name-clusters]`, `decisions` |
| Rule 6 — balance cluster sizes                          | `steps[balance-tree]`            |
| Rule 7 — even source distribution                       | `steps[balance-sources]`         |
| Output paths and column schemas                         | `steps[emit-outputs]`, `references/output-format.md` |
| End-to-end validation                                   | `steps[validate]`, `scripts/validate_output.py` |

Nothing from the instruction was deliberately dropped.

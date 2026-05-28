# Source & authoring notes — `taxonomy-tree-merge`

## Intent

Author an AIP skill that lets a downstream agent autonomously unify product-category
taxonomies from several e-commerce platforms (Amazon, Facebook, Google Shopping) into a
single 5-level category catalog, plus the two CSV deliverables the task requires.

**Sole source material:** `source/instruction.md` (verbatim copy of the SkillsBench task
instruction). The skill was authored from the instruction text alone — no existing
solution skills were inspected.

## Schema choice

Reuses the shared **`procedure`** schema (`source/procedure.schema.json`,
`$id` …/v0.3a2/assets/aip-schemas/procedure.schema.json). The task is a multi-step
execution graph — ingest → design → assign → build → validate → loop — i.e. a runbook /
pipeline. No new schema needed.

## Why clustering stays partly prose

AIP says scriptable logic (numeric thresholds, lookup tables, rules) must live in
`scripts/`. Two kinds of logic exist here:

* **Deterministic / threshold logic → scripted.**
  * `ingest.py` — format-robust CSV reading, delimiter detection, text standardization
    (rule 3), and a profile that seeds top-level groups.
  * `build_outputs.py` — deterministic assembly of the two CSVs + `depth` + the hierarchy
    prefix set.
  * `validate_taxonomy.py` — **every numeric rule** (rule 1 counts, rule 2 word cap,
    rule 4 parent/child overlap, rule 5 sibling overlap, coverage, hierarchy consistency,
    and soft scores for rules 2/6/7). This is the keystone gate.
* **Semantic judgment → prose step.** Deciding *which* native categories are synonyms,
  how to name a cluster so it generalizes its members, and how deep to nest is genuine
  language understanding. Forcing it into a script would over-restrict reasoning (an AIP
  anti-pattern). The agent does this with judgment, **gated by the validator loop**, and
  may optionally use embeddings/an LLM to improve grouping beyond the lexical seed.

## Interpretation decisions (instruction is ambiguous on these)

* **`depth` column.** Defined as the depth of the *source* `category_path` (segment count,
  capped at 5). Rationale: it sits next to `category_path`, and is non-redundant with the
  five `unified_level_*` columns (which already encode the unified depth). `build_outputs.py`
  exposes `--depth-mode unified` to switch to "count of populated unified levels" if grading
  reveals the other reading.
* **`unified_taxonomy_hierarchy.csv` rows.** "All paths from low granularity to high" is
  read as: one row per *distinct node* in the unified tree — every prefix path — ordered
  level-1 nodes first (low granularity) down to full 5-level leaves (high granularity), with
  trailing levels blank. `build_outputs.py` derives this; the validator enforces the set is
  exactly the distinct prefixes of `full.csv`.
* **Rule 2 representativeness (70%).** Inherently semantic. Implemented as a **soft**
  theme-coverage proxy (≥70% of a node's member leaves share a top content token) plus a
  per-node score in the report. It never hard-fails; the agent confirms by judgment. It
  deliberately looks at member-leaf tokens, *not* the parent's own name, so it does not
  conflict with rule 4 (which forbids parent/child name overlap).
* **Rule 4 (parent/child overlap).** Hard: a child name must share **zero** words with its
  parent name.
* **Rule 5 (sibling distinctness).** Hard: pairwise Jaccard word overlap **< 0.30** among
  siblings.
* **Rules 6 (pyramid balance) & 7 (source evenness).** "Reasonable" / "relatively even" and
  data-dependent, so **soft** (warnings + stats in the report) rather than hard fails.

## Instruction → coverage map

| instruction content | where captured |
|---|---|
| 3 source files, different formats, `category_path` column | `ingest.py` (source detection, column + delimiter detection) |
| unify into one 5-level taxonomy | overall procedure; `unified_level_1..5` |
| rule 1 (10–20 top; 3–20 per parent) | `validate_taxonomy.py` rule1_* (hard) |
| rule 2 (name from available names, " \| " sep, ≤5 words, 70% representative) | naming guidance in steps + `references/taxonomy-method.md`; `validate_taxonomy.py` rule2_name_format (hard ≤5 words) + rule2_representativeness (soft) |
| rule 3 (standardize text) | `ingest.py` `standardize_segment` + naming guidance |
| rule 4 (no parent/child name overlap) | `validate_taxonomy.py` rule4 (hard) |
| rule 5 (siblings <30% overlap) | `validate_taxonomy.py` rule5 (hard) |
| rule 6 (balanced pyramid) | `validate_taxonomy.py` rule6 (soft) + design step |
| rule 7 (sources evenly distributed) | `validate_taxonomy.py` rule7 (soft) + assign step |
| output `unified_taxonomy_full.csv` schema | `build_outputs.py`; steps; method reference |
| output `unified_taxonomy_hierarchy.csv` schema | `build_outputs.py`; steps; method reference |
| `/root/data` in, `/root/output` out | script defaults |

## Deliberate drops

None of substance. Example category text from the instruction ("electronics > computers >
Laptops") is illustrative and is generalized into the delimiter-detection logic rather than
hard-coded.

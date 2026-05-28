# Taxonomy-merge method & output contract

Read this during the **design** and **assign** steps, and before **build**. It covers the
clustering approach, naming rules, the `assignments.json` contract, and how to read the
validator report.

## 1. Read the landscape first

`ingest.py` writes `normalized_categories.json`:

* `rows` — one per unique `(source, category_path)`: standardized `segments` + `depth`.
* `suggested_l1_groups` — native top-level terms greedily merged across sources by token
  overlap. **A seed, not the answer** — merge synonyms the lexical pass missed
  (e.g. `apparel` ≈ `clothing`, `cell phones` ≈ `mobile`), and split groups that are too
  broad.
* `level1_terms`, `depth_distribution`, `delimiters`, `sources` — per-source profile.

## 2. Design the unified skeleton (semantic judgment)

Build a tree, **breadth before depth**:

1. **Level 1 (10–20 nodes).** Start from `suggested_l1_groups`. Merge cross-source
   synonyms; keep each L1 a broad department. Aim for the 10–20 band — if you have 4 huge
   groups, split them; if 40 tiny ones, merge.
2. **Levels 2–5 (3–20 children each).** Recursively partition each node's members into
   3–20 distinct subgroups. A node with <3 natural subgroups should stay a **leaf** (stop
   early — not every branch reaches depth 5). Never force a parent to have 1–2 children.
3. **Balance (rule 6).** Keep children-per-parent in a similar range across the level so the
   tree is a pyramid, not a few giant branches beside many stubs.
4. **Source spread (rule 7).** Each L1 should draw from multiple sources where the data
   allows; don't build a branch fed by a single platform if others have matching categories.

You may use embeddings or an LLM to cluster `rows` if available — it beats the lexical seed.
Otherwise group by shared standardized tokens, then refine by meaning.

## 3. Naming rules (rule 2, 3, 4, 5)

* **Source the name** from the actual category text under the node — don't invent jargon.
* **Format:** join words with `" | "`, e.g. `Cell | Phones`, `Home | Kitchen | Dining`.
  Single-word names need no separator (`Electronics`). **≤ 5 words.**
* **Standardize** (rule 3): Title-Case, expand/normalize (`&`→`and`), singular/plural and
  synonym-consistent across sources (pick one of `Men`/`Mens`, `Notebook`/`Laptop`).
* **Rule 4 — parent/child:** a child shares **no word** with its parent. Parent should be a
  *generalization* (`Electronics` → `Computers`, not `Electronics` → `Electronics | Computers`).
* **Rule 5 — siblings:** any two siblings overlap **< 30%** of words (Jaccard). Distinct
  siblings, not near-duplicates.
* **Rule 2 — representativeness:** a node's name must fairly summarize ≥70% of what sits
  under it. If a cluster is too mixed for one honest label, re-split it.

## 4. Assign every source path → unified path

Produce `assignments.json`: a JSON **list**, one object per row in
`normalized_categories.json` (every `(source, category_path)` must appear exactly once —
rule: full coverage):

```json
[
  {
    "source": "amazon",
    "category_path": "Electronics > Computers > Laptops",
    "unified_level_1": "Electronics",
    "unified_level_2": "Computers",
    "unified_level_3": "Laptops",
    "unified_level_4": "",
    "unified_level_5": ""
  }
]
```

* `source` ∈ `amazon` | `facebook` | `google` (map `fb`→`facebook`, the google-shopping
  file → `google`).
* `category_path` = the **original** source string, verbatim from `rows`.
* Fill `unified_level_1..N` with the node path the category lands on; leave deeper levels
  `""`. **No gaps** — never fill level 3 while level 2 is blank.
* A broad source category may map shallow (just L1, or L1→L2); a specific leaf maps deep.
* Source paths deeper than 5 collapse into the best 5-level path; shorter ones map to the
  matching shallower node.

## 5. Build & validate (deterministic, scripted)

```bash
python3 scripts/build_outputs.py --assignments /root/output/assignments.json --out-dir /root/output
python3 scripts/validate_taxonomy.py \
    --full /root/output/unified_taxonomy_full.csv \
    --hierarchy /root/output/unified_taxonomy_hierarchy.csv \
    --normalized /root/output/normalized_categories.json \
    --report /root/output/validation_report.json
```

`build_outputs.py` writes:

* **`unified_taxonomy_full.csv`** — `source, category_path, depth, unified_level_1..5`
  (`depth` = source path depth, capped at 5; use `--depth-mode unified` for unified depth).
* **`unified_taxonomy_hierarchy.csv`** — `unified_level_1..5`, one row per distinct tree
  node, ordered low→high granularity.

## 6. Read the report & loop

`validation_report.json` → `checks.<name>.{status, messages, offenders, scores, data}`.

* **Hard fails (status `fail`)** must reach zero. Common fixes:
  * `rule2_name_format` — a name has >5 words, a raw `>`/`/`/`::` separator, or multiple
    words not joined by `" | "`. Re-name to ≤5 standardized words joined by `" | "`.
  * `rule1_level1_count` — merge/split L1 nodes into the 10–20 band.
  * `rule1_children_per_parent` — a parent with 1–2 children: merge into a sibling or pull
    grandchildren up; >20: introduce an intermediate level.
  * `rule4_parent_child_overlap` — rename the child to drop the shared word.
  * `rule5_sibling_overlap` — rename or merge the near-duplicate siblings.
  * `contiguous` / `coverage` / `hierarchy` — fix the offending `assignments.json` rows and
    rebuild (don't hand-edit the CSVs).
* **Soft warns** (`rule2_representativeness`, `rule6_pyramid_balance`, `rule7_source_even`)
  carry scores/stats. Improve where cheap; they won't block, but a good taxonomy minimizes
  them.

Edit `assignments.json` (or the skeleton), re-run **build → validate**, repeat until hard
errors are zero and soft warnings are addressed.

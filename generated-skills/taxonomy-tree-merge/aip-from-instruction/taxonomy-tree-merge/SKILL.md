---
name: taxonomy-tree-merge
description: Merge product-category taxonomies from multiple e-commerce sources (Amazon, Facebook, Google Shopping) into a single unified 5-level hierarchy and emit both the per-source mapping and the deduplicated hierarchy as CSVs. Use when the user wants to unify, harmonize, reconcile, or cross-walk product categories from two or more platforms into one shared taxonomy for downstream analytics, when input CSVs each have a `category_path` column with `>`-separated hierarchical paths, or when the goal is to produce `unified_taxonomy_full.csv` and `unified_taxonomy_hierarchy.csv` outputs that satisfy shape/naming/balance rules (10–20 top-level buckets, 3–20 children per parent, ≤5-word `|`-separated names, sibling distinctness, even source distribution).
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.2/assets/aip-schemas/procedure.schema.json
compatibility: Requires Python 3.10+; reads from /root/data/ and writes to /root/output/ by default.
---

```yaml
purpose: >
  Merge multiple e-commerce product-category taxonomies (Amazon, Facebook,
  Google Shopping) into a single unified 5-level hierarchy. Produce two
  outputs: a per-source row-level mapping from each original `category_path`
  to its unified 5-level path, and a deduplicated hierarchy listing every
  unified path at every depth. The unified tree must satisfy a fixed set of
  shape, naming, and distribution rules (see `decisions` and
  `references/rules-checklist.md`).

trigger_when:
  - Input directory has CSV files named like `amazon_product_categories.csv`,
    `fb_product_categories.csv`, `google_shopping_product_categories.csv`,
    each with a `category_path` column.
  - The user asks to unify, harmonize, reconcile, or cross-walk product
    categories from two or more e-commerce platforms.
  - The target output is a 5-level taxonomy plus a per-source mapping that
    downstream analytics can group by.
  - The user references `unified_taxonomy_full.csv` and/or
    `unified_taxonomy_hierarchy.csv` as expected outputs.

do_not_use_when:
  - Only one source taxonomy is provided — that's a re-shape task, not a
    merge. Apply the normalization and naming rules directly without
    cross-source clustering.
  - The input data is not hierarchical (flat category lists). The procedure
    assumes `parent > child > grandchild` style paths split on ` > `.
  - The user wants a taxonomy mapped onto an external standard (e.g.,
    GS1 GPC, NAICS). This skill builds a synthesized taxonomy from the input
    label vocabulary, not a mapping to an external one.

scope_and_approval: >
  Read-only on /root/data/. Writes two CSV files under /root/output/
  (creating the directory if missing). No network access required. No
  destructive operations. Safe to run end-to-end without checkpoint approval;
  however, before emitting the final outputs, present the top-level bucket
  list (counts per source) to the user for sanity-check approval — top-level
  choices anchor every downstream level and re-running after fixing them is
  cheap.

steps:
  - name: load-inputs
    description: >
      Run `scripts/inspect_inputs.py` to summarize each source file: column
      names (formats differ across files — the `category_path` column may be
      named slightly differently), row count, unique-path count, depth
      distribution, top-of-path frequency, and a sample path at each depth.
      Use the report to decide which column to read in each file and to
      eyeball the natural top-level buckets before clustering.
  - name: normalize-paths
    description: >
      For every input row, split `category_path` on ` > `, strip whitespace,
      canonicalize casing (Title Case), collapse obvious synonyms ("TVs"
      ↔ "Televisions", "Apparel" ↔ "Clothing & Apparel"), and standardize
      plural/singular usage. Keep the raw `category_path` verbatim for the
      output — normalization only affects the *unified* labels you assign,
      not the source `category_path` cell.
  - name: cluster-level-1
    description: >
      Group all normalized top-of-path segments across the three sources
      into 10–20 unified level-1 buckets. Lead with the top-of-path
      frequency table from `inspect_inputs.py` — that's the natural
      starting seed. Reconcile near-duplicates across sources (e.g., Amazon
      "Electronics" + Facebook "Electronics & Computers" + Google
      "Electronics" all collapse into one bucket). Aim for buckets that
      each receive contributions from all three sources where the data
      supports it.
  - name: cluster-deeper-levels
    description: >
      Within each level-1 bucket, recursively cluster the remaining
      sub-paths into level-2 through level-5. At every internal node aim
      for 3–20 children. If a cluster has only 1–2 children, merge it
      upward; if it has >20, split it on the next discriminating term.
      Truncate paths deeper than 5 — never emit a unified path longer than
      5 levels. Shorter unified paths (depth 1–4) are fine and expected for
      shallow input paths.
    depends_on: [cluster-level-1]
  - name: name-clusters
    description: >
      Name each unified node using vocabulary drawn from the source labels
      it covers. Rules per name cell - ≤5 words, multiple words joined with
      " | " (space-pipe-space), no commas, "representative enough" of the
      cluster (a human reader would expect ~70%+ of descendant leaves to
      fall under the name without surprise). Avoid sharing word stems with
      the parent name — if the parent is "Computers | Tablets" the child
      must not be "Tablets" or "Computer | Cases" (use "Cases" or
      "Carrying Cases" instead). Avoid sharing word stems with siblings —
      pairwise token overlap (Jaccard over min) must be <30%.
    depends_on: [cluster-deeper-levels]
  - name: assign-paths
    description: >
      Map every input row's normalized path to its unified path. Each
      original `category_path` lands at exactly one unified leaf (which may
      be at depth 1–5). Track the source so the per-row CSV can record
      it. Re-do borderline assignments by re-reading sibling cluster
      contents — a row's home should be the cluster whose vocabulary it
      most resembles, not just the first lexical match.
    depends_on: [name-clusters]
  - name: balance-tree
    description: >
      Inspect cluster sizes after assignment. No top-level bucket should
      hold >30% or <2% of total leaf paths; mid-level subtrees within a
      top-level bucket should be within ~3× of each other in leaf count.
      If a bucket is too large, split it; if too small, merge it into a
      thematically neighbouring bucket (or create an "Other | <theme>"
      sibling). Loop back to `cluster-deeper-levels` if rebalancing
      changes the level-1 shape.
    depends_on: [assign-paths]
  - name: balance-sources
    description: >
      For every top-level bucket, check the share contributed by each of
      amazon/facebook/google against that source's overall share. A
      bucket where only one source contributes is a smell — either the
      other two genuinely lack that category (acceptable, note it) or
      their rows are being misrouted (fix the cluster boundary). Use the
      `validate_output.py` `source_imbalance` warnings as a guide.
    depends_on: [assign-paths]
  - name: emit-outputs
    description: >
      Write `unified_taxonomy_full.csv` and `unified_taxonomy_hierarchy.csv`
      under `/root/output/` (create the directory if needed). Column order
      and naming must match `references/output-format.md` exactly. Empty
      cells for unused depths — never write "NaN", "none", or zero. The
      hierarchy file must include every prefix of every unified path that
      appears in the full file (root, root+L2, root+L2+L3, …) with each
      prefix appearing exactly once.
    depends_on: [balance-tree, balance-sources]
  - name: validate
    description: >
      Run `python scripts/validate_output.py --output-dir /root/output`.
      The script enforces mechanical rules (columns, depth/path agreement,
      tree shape, parent/child overlap, prefix coverage, source balance).
      If it exits non-zero, parse the JSONL errors on stderr, fix, re-emit,
      re-run. Then walk `references/rules-checklist.md` by hand for the
      judgement-based rules ("representative enough", "reasonable
      pyramid") the script can't fully enforce.
    depends_on: [emit-outputs]

decisions:
  - signal: A unified cluster has only 1 or 2 children at some level.
    action: Merge it upward into its parent — collapse the singleton and
      promote its grandchildren one level up.
  - signal: A unified cluster has >20 children at some level.
    action: Split on the next discriminating term (e.g., split "Apparel >
      Clothing" by garment type — Tops, Bottoms, Outerwear, Accessories).
  - signal: A proposed child name shares a word stem with its parent.
    action: Drop the shared word; if the remainder is empty or
      uninformative, rename the parent more abstractly or merge the child
      with a sibling.
  - signal: Two siblings have ≥30% token overlap.
    action: Either merge them into one cluster, or rename one with a more
      specific term from its leaf vocabulary.
  - signal: An input row's normalized leaf doesn't match any unified
      cluster's vocabulary.
    action: Add a new sibling cluster only if its parent has room (≤20
      children); otherwise re-bucket the row into the closest existing
      sibling and note the loss in standardization.
  - signal: One source dominates a top-level bucket (>70% share when the
      bucket is >3% of total rows).
    action: Verify the other sources' rows aren't being misrouted to a
      sibling. If they genuinely lack that category, accept the imbalance
      and document it; otherwise fix the cluster boundary.
  - signal: An input `category_path` is deeper than 5 segments.
    action: Use the first 5 (or coarser) segments of vocabulary when
      naming the unified path; the unified path itself is capped at 5
      levels regardless of input depth.
  - signal: "`validate_output.py` reports a `gap_in_levels` violation."
    action: "A row has `unified_level_3` populated but `unified_level_2`
      empty — fill the missing intermediate level or shift the populated
      level upward."

scenarios:
  - need: Amazon row "Electronics > Computers > Laptops" alongside Google
      row "Electronics > Computers & Office > Laptops & Notebooks".
    context: Top-of-path frequency from `inspect_inputs.py` shows both
      sources cluster heavily under "Electronics" / "Electronics & ...".
    action: Unify level-1 → "Electronics"; unify level-2 → "Computers" (or
      "Computers | Office" if Facebook's "Office Electronics" rows also
      land here); unify level-3 → "Laptops". Both source paths map to the
      same `(Electronics, Computers, Laptops, , )` row in the full file.
    outcome: One canonical 3-level unified path; downstream metrics roll
      up cleanly without per-source casing branches.
  - need: A Facebook leaf "Pet Supplies > Aquariums" with no Amazon or
      Google counterpart at that depth.
    context: Aquariums appear in Amazon only at "Pet Supplies > Fish &
      Aquatic Pets > Aquariums & Stands" (deeper) and not at all in
      Google's top-level Pets.
    action: Use the Amazon depth-3 path as the unified target; remap the
      Facebook row to `(Pets, Fish | Aquatic, Aquariums, , )` so all
      three sources roll up consistently under "Pets" at level-1.
    outcome: Pet rows from all three sources land under one level-1
      bucket; the Facebook row's unified path is one level deeper than
      its source path, which is fine.
  - need: A cluster of 28 children appears under `(Home, Kitchen)`.
    context: Children include Cookware, Bakeware, Cutlery, Small
      Appliances, Storage, Cleaning, Linens, Tableware, …
    action: Split into thematic sub-buckets — e.g., `(Home, Kitchen,
      Cookware | Bakeware)`, `(Home, Kitchen, Appliances)`, `(Home,
      Kitchen, Storage | Organization)`, `(Home, Kitchen, Tableware |
      Linens)`. Push the original 28 leaves down one level into the new
      sub-buckets.
    outcome: Every internal node back within the 3–20 child range; tree
      gains depth where the data warrants it.

anti_patterns:
  - Treating the three input files as already-aligned schemas. Column
    names, casing, and even the path separator may differ slightly —
    always run `scripts/inspect_inputs.py` first.
  - Inventing top-level buckets from external knowledge (GS1, NAICS).
    The unified taxonomy must be built from the input vocabulary so every
    source row has a natural home.
  - Naming a child by repeating the parent's words ("Electronics >
    Electronics Accessories"). Drop the shared term.
  - Padding short unified paths with empty placeholder names to reach 5
    levels. Shorter paths are fine; leave the deeper cells empty.
  - Emitting "NaN" or "None" strings instead of empty cells for unused
    depths. The output CSVs must use truly empty cells.
  - Forgetting to include intermediate-prefix rows in
    `unified_taxonomy_hierarchy.csv`. The hierarchy file lists every
    prefix at every depth, not just leaves.
  - Skipping the manual `references/rules-checklist.md` pass after the
    validator script passes. The script enforces structure; the checklist
    enforces semantics ("representative enough", "reasonable pyramid").
  - Renaming or trimming the input `category_path` value in the full
    output file. Preserve it verbatim — only the unified-level cells
    reflect the standardized vocabulary.
```

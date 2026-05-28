---
name: taxonomy-tree-merge
description: "Merge hierarchical product-category taxonomies from multiple e-commerce sources (Amazon, Facebook, Google Shopping) into one unified 5-level catalog. Use when consolidating category_path or breadcrumb data from several platforms/files into a single category system, inducing or aligning a multi-source product taxonomy/ontology, or producing a balanced N-level category tree with per-level size (10-20 top, 3-20 children), pipe-separated names (<=5 words), parent/child and sibling distinctness, representativeness, and even source-distribution constraints. Produces unified_taxonomy_full.csv and unified_taxonomy_hierarchy.csv."
compatibility: "Requires python3 (3.8+, standard library only). Reads CSVs from a data directory (default /root/data) and writes outputs to an output directory (default /root/output)."
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a2/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Unify hierarchical product-category taxonomies from multiple e-commerce sources
  (Amazon, Facebook, Google Shopping) into a single 5-level catalog, and emit the two
  required CSV deliverables. Covers format-robust ingestion of differently-shaped CSVs,
  text standardization, semantic clustering of native categories into a balanced
  10-20 by 3-20 tree, constraint-correct naming, full mapping of every source path, and a
  scripted validation loop that enforces the structural rules. The hard, numeric rules live
  in scripts; the semantic clustering and naming are agent judgment, gated by the validator.

trigger_when:
  - Consolidating category_path / breadcrumb data from several platforms or files into one taxonomy.
  - Inducing or aligning a multi-source product taxonomy or ontology.
  - User provides amazon/facebook/google (or similar) category exports and wants one unified category system.
  - Building a balanced N-level category tree with per-level size, naming, distinctness, and source-distribution constraints.
  - Producing unified_taxonomy_full.csv and unified_taxonomy_hierarchy.csv from category exports.

do_not_use_when:
  - Classifying individual products into an existing fixed taxonomy (this builds the taxonomy, not a classifier).
  - A single clean taxonomy already exists and only needs reformatting.
  - The task is flat deduplication with no hierarchy.

scope_and_approval: >
  Read-only on the input data dir. Writes only under the output dir (default /root/output):
  normalized_categories.json, assignments.json, the two deliverable CSVs, and
  validation_report.json. No network needed (scripts are stdlib-only). Safe to run
  unattended; the validate -> revise loop is the quality gate.

steps:
  - name: ingest
    description: >
      Run scripts/ingest.py to read every CSV in the data dir, detect each file's source,
      its category column, and its path delimiter, standardize segment text, and write
      normalized_categories.json (one row per unique source path plus a profile with
      suggested level-1 seed groups and per-source stats).
    script: scripts/ingest.py
    inputs:
      - name: data-dir
        type: string
        description: Directory of source CSVs (default /root/data).
    outputs:
      - name: normalized
        type: object
        description: normalized_categories.json - rows + profile.
  - name: design-skeleton
    description: >
      Read references/taxonomy-method.md, then design the unified tree from the profile:
      10-20 broad level-1 nodes (merge cross-source synonyms), each deeper level split into
      3-20 distinct children. 5 levels is the MAXIMUM depth, not a quota - stop a branch
      early (it becomes a leaf) when it has no natural subgroups; most branches end shallower.
      Name each node from the actual category text, joined with ' | ', <=5 words,
      standardized; a parent must generalize >=70% of its members and share no word with its
      children (rule 4); siblings must overlap <30% of words (rule 5). Balance
      children-per-parent (rule 6) and spread sources across branches (rule 7). This is
      semantic judgment - use embedding/LLM grouping over the rows if available, else group
      by shared standardized tokens then refine by meaning.
    inputs:
      - name: normalized
        type: object
    outputs:
      - name: taxonomy-skeleton
        type: object
        description: The unified node tree with constraint-correct names.
  - name: assign-paths
    description: >
      Map every (source, category_path) row to its unified level path and write
      assignments.json (format in references/taxonomy-method.md section 4). Every source path
      appears exactly once; levels are contiguous (no gaps); broad categories map shallow,
      specific leaves map deep; paths deeper than 5 collapse to the best 5-level path.
    inputs:
      - name: normalized
        type: object
      - name: taxonomy-skeleton
        type: object
    outputs:
      - name: assignments
        type: object
        description: assignments.json - list of source path -> unified_level_1..5.
  - name: build-outputs
    description: >
      Run scripts/build_outputs.py to assemble unified_taxonomy_full.csv and
      unified_taxonomy_hierarchy.csv from assignments.json. Never hand-write these CSVs - the
      script owns the schema, the depth column, and the distinct-node hierarchy ordering.
    script: scripts/build_outputs.py
    depends_on: [assign-paths]
    inputs:
      - name: assignments
        type: object
    outputs:
      - name: full-csv
        type: string
        description: unified_taxonomy_full.csv path.
      - name: hierarchy-csv
        type: string
        description: unified_taxonomy_hierarchy.csv path.
  - name: validate
    description: >
      Run scripts/validate_taxonomy.py on the two CSVs (pass --normalized for the coverage
      check). It enforces every hard rule (level-1 count, children-per-parent, <=5-word
      names, parent/child overlap, sibling overlap, contiguity, full coverage, hierarchy
      consistency) and scores the soft rules (representativeness, pyramid balance, source
      evenness), writing validation_report.json. Exit 0 means no hard errors.
    script: scripts/validate_taxonomy.py
    depends_on: [build-outputs]
    inputs:
      - name: full-csv
        type: string
      - name: hierarchy-csv
        type: string
      - name: normalized
        type: object
    outputs:
      - name: report
        type: object
        description: validation_report.json - per-check status, offenders, scores.
  - name: iterate
    description: >
      If the report has any hard errors, revise assignments.json (or the skeleton) using the
      fixes in references/taxonomy-method.md section 6, then re-run build-outputs -> validate.
      Repeat until hard errors are zero; then reduce soft warnings (representativeness,
      balance, source evenness) where cheap. Fix the assignment, not the CSV.
    depends_on: [validate]
    inputs:
      - name: report
        type: object
    outputs:
      - name: final-outputs
        type: object
        description: The two validated CSVs in the output dir.

scenarios:
  - need: >
      Three exports - amazon_product_categories.csv (' > '), fb_product_categories.csv ('/'),
      google_shopping_product_categories.csv ('>') - to be unified into one 5-level taxonomy.
    context: >
      ingest.py detects a different delimiter per file and a category column named
      category_path in two files and taxonomy in the third; the profile suggests electronics,
      home, and apparel/clothing seed groups across sources.
    action: >
      Merge apparel+clothing and electronics synonyms into ~12 level-1 nodes, partition each
      3-20 ways, name them ' | '-style, assign all paths, build, validate, and loop.
    outcome: >
      unified_taxonomy_full.csv (every source path mapped) and unified_taxonomy_hierarchy.csv
      (every distinct node) passing all hard checks.
  - need: The validator reports a parent with 2 children and a sibling pair overlapping 0.5.
    context: rule1_children_per_parent and rule5_sibling_overlap failed in the report.
    action: >
      Merge the 2-child parent into a sibling (or lift its grandchildren up a level), and
      rename or merge the near-duplicate siblings; rebuild and revalidate.
    outcome: Both hard checks pass on the next loop.

anti_patterns:
  - Hand-writing the output CSVs instead of producing assignments.json and running build_outputs.py - drifts from the required schema.
  - Reusing native source names verbatim with > or / separators instead of standardizing to ' | ' words.
  - Repeating a parent's word in its child (Electronics -> Electronics | Phones) - violates rule 4.
  - Forcing every branch to depth 5, creating parents with 1-2 children - violates rule 1; stop a branch early instead.
  - Building level 1 from a single source's top categories - skews source distribution (rule 7).
  - Treating soft scores as pass/fail, or ignoring hard errors - loop until hard errors are zero.
  - Editing the CSVs to silence the validator instead of fixing assignments.json and rebuilding.
```

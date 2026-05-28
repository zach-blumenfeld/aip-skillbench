---
name: hierarchical-taxonomy-clustering
description: Build a unified multi-level category taxonomy from hierarchical product category paths across multiple e-commerce sources using embedding-based recursive clustering with intelligent category naming via weighted word-frequency analysis. Use when merging category trees from different platforms, unifying noisy category paths, or producing an N-level (typically 5) cross-source taxonomy for analysis or metric tracking.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a2/assets/aip-schemas/procedure.schema.json
compatibility: Requires Python 3 with pandas, numpy, scipy, sentence-transformers, nltk, and tqdm. First run downloads the all-MiniLM-L6-v2 model and NLTK wordnet/omw-1.4 corpora (network access needed once).
---

```yaml
purpose: >
  Build a single unified multi-level taxonomy from hierarchical category paths
  (e.g. "electronics > computers > laptops") supplied by multiple e-commerce
  sources. The four-step pipeline standardizes and merges sources, encodes each
  path into a hierarchically weighted embedding, recursively clusters the
  embeddings into an N-level tree, names each cluster from weighted word
  frequencies, and exports the result. The output groups semantically similar
  paths across sources under shared category names so products from different
  platforms can be analyzed or tracked on one taxonomy. All numeric logic
  (weight decay, cluster-count bounds, coverage threshold, word selection,
  prefix/depth filtering) lives in the bundled `scripts/`; run them, do not
  re-derive the math inline.

trigger_when:
  - Merging hierarchical product-category trees from two or more e-commerce sources into one taxonomy.
  - Unifying inconsistent or noisy category paths (different delimiters, word forms, special characters) across platforms.
  - Producing an N-level (typically 5) cross-source category hierarchy for analysis or metric tracking.
  - User mentions taxonomy merge, category clustering, unified taxonomy, category-path normalization, or hierarchical clustering of categories.

do_not_use_when:
  - The input is a single already-clean taxonomy that needs no cross-source unification.
  - The categories are flat (no hierarchical paths) — there is no multi-level structure to cluster.
  - The task needs an exact rule-based crosswalk between two known taxonomies rather than embedding-based grouping.

scope_and_approval: >
  Reads the supplied source CSVs and writes exactly two output files into the
  given output directory (`unified_taxonomy_full.csv`,
  `unified_taxonomy_hierarchy.csv`); it creates that directory if missing.
  No other writes, no destructive operations. The first run downloads the
  sentence-transformer model and NLTK corpora over the network. Safe to run
  without prompting once dependencies are installed.

steps:
  - name: install-dependencies
    description: >
      Ensure the runtime has the required packages and NLTK data. Run exactly:
      `pip install pandas numpy scipy sentence-transformers nltk tqdm` then
      `python -c "import nltk; nltk.download('wordnet'); nltk.download('omw-1.4')"`.
      Step 1 lemmatizes at import time, so wordnet must be present before the
      pipeline runs (step 3 also auto-downloads it as a fallback). Kept as prose
      because these are fixed setup commands, not data-dependent logic.
    outputs:
      - name: env-ready
        type: boolean
        description: True once packages and the wordnet/omw-1.4 corpora are available.
  - name: preprocess-and-merge
    description: >
      Run step 1. Per source: dedupe on raw `category_path`, clean text
      (normalize delimiters to ` > `, strip &/,/-/slashes/quotes/possessives,
      lemmatize each word as a noun), compute depth, filter to depth <=
      target_depth (default 5), split into `source_level_1..N`, drop prefix
      (non-leaf) paths, then concatenate all sources. The script holds the
      cleaning rules and filters — pass it the source list, do not reimplement.
    script: scripts/step1_preprocessing_and_merge.py
    depends_on: [install-dependencies]
    inputs:
      - name: source-datasets
        type: list[object]
        description: List of (DataFrame, source_name) tuples; each DataFrame has a `category_path` column. The CLI loads these from `path:name` CSV specs.
      - name: target-depth
        type: integer
        nullable: true
        description: Maximum path depth to keep (default 5).
    outputs:
      - name: merged-df
        type: object
        description: DataFrame with category_path, source, depth, and source_level_1..N (cleaned, lemmatized, leaf-only, deduped per source).
  - name: generate-embeddings
    description: >
      Run step 2. Encode each `source_level_i` with all-MiniLM-L6-v2 (384-dim)
      and combine into one per-path vector using exponentially decaying weights
      (level i weight = 0.6^(i-1): 1.0, 0.6, 0.36, 0.216, 0.1296), using only
      the levels that actually exist and normalizing the weights per path to sum
      to 1. Expect ~2-5 minutes for ~10k records; a progress bar shows status.
    script: scripts/step2_weighted_embedding_generation.py
    depends_on: [preprocess-and-merge]
    inputs:
      - name: merged-df
        type: object
      - name: weights
        type: object
        nullable: true
        description: "Optional {level: weight} map; defaults to 0.6^(n-1) decay."
    outputs:
      - name: embeddings
        type: object
        description: Numpy matrix of shape (n_records, 384).
  - name: recursive-cluster-and-name
    description: >
      Run step 3. Recursively agglomerative-cluster (average linkage, cosine
      distance) the embeddings level by level (10-20 clusters at L1, 3-20 at
      L2-L5), naming each cluster by greedy weighted word frequency: select
      words covering >=70% of records or up to 5 words, applying bundle-word
      logic, excluding all ancestor words and global duplicate names (a branch
      terminates with None when no valid words remain). A cluster with <=
      min_clusters_other records (default 3) becomes a leaf instead of
      recursing deeper, so small branches stop early. Expect ~1-3 minutes for
      ~10k records. The script owns every threshold and the naming algorithm.
    script: scripts/step3_recursive_clustering_naming.py
    depends_on: [generate-embeddings]
    inputs:
      - name: merged-df
        type: object
      - name: embeddings
        type: object
      - name: cluster-bounds
        type: object
        nullable: true
        description: Optional min_clusters_l1 (10), max_clusters (20), min_clusters_other (3).
    outputs:
      - name: assignments
        type: object
        description: Dict mapping record index -> {unified_level_1 ... unified_level_N}.
  - name: apply-and-export
    description: >
      Run step 4. Map `assignments` back onto the DataFrame as
      `unified_level_1..N`, then write two CSVs to the output directory:
      `unified_taxonomy_full.csv` (every record with source, category_path,
      depth, unified levels) and `unified_taxonomy_hierarchy.csv` (unique,
      sorted unified paths). Also prints coverage and category-distribution
      quality metrics. Category names use the ` | ` separator.
    script: scripts/step4_result_assignments.py
    depends_on: [recursive-cluster-and-name]
    inputs:
      - name: merged-df
        type: object
      - name: assignments
        type: object
      - name: output-dir
        type: string
    outputs:
      - name: full-csv
        type: string
        description: Path to unified_taxonomy_full.csv (all records mapped to unified categories).
      - name: hierarchy-csv
        type: string
        description: Path to unified_taxonomy_hierarchy.csv (deduplicated taxonomy structure).

modes:
  - name: full-pipeline
    body: >
      Recommended default. Run all four steps end to end with
      `scripts/pipeline.py`, either via its CLI
      (`python scripts/pipeline.py --sources data1.csv:amazon data2.csv:google
      --output ./out --depth 5 --min-l1 10 --max-clusters 20 --min-others 3`)
      or by importing `run_pipeline(source_dfs, output_dir, ...)`. Each `--sources`
      entry is `csv_path:source_name`, and every CSV must contain a
      `category_path` column. The CLI splits on the first-and-only `:`, so the
      path and source name must not themselves contain a colon (e.g. Windows
      drive paths); use the `run_pipeline()` / step-by-step API for those.
  - name: step-by-step
    body: >
      Advanced control. Import and call the step functions directly
      (`standardize_and_filter_sources` -> `generate_embeddings` ->
      `recursive_taxonomy_clustering` -> `apply_assignments` /
      `export_results`), passing the output of each as the input to the next.
      Use when you need to inspect or tune an intermediate artifact (e.g. the
      merged DataFrame or the embedding matrix) between steps.

scenarios:
  - need: Merge Amazon and Google category exports into one 5-level taxonomy.
    context: Two CSVs, each with a `category_path` column using mixed delimiters and word forms.
    action: >
      Run the full pipeline:
      `python scripts/pipeline.py --sources amazon.csv:amazon google.csv:google --output ./out`.
    outcome: out/unified_taxonomy_full.csv maps every original path to unified_level_1..5; out/unified_taxonomy_hierarchy.csv lists the unique unified tree.
  - need: A cluster's child level comes back empty / a branch stops before level 5.
    context: All candidate words for the child were already used by an ancestor, or duplicate a sibling name.
    action: Treat the None as a natural path termination — that branch is intentionally shallower; do not force a name.
    outcome: Deeper unified_level_* columns are null for those records, which is expected behavior.
  - need: Same path appears many times within one source.
    action: Rely on step 1's per-source dedupe on raw `category_path` (before cleaning) rather than deduping yourself.
    outcome: Cluster weights are not inflated by duplicates and original formatting is preserved for validation.

anti_patterns:
  - Reimplementing the cleaning, weighting, clustering, or naming math inline instead of running the bundled scripts — the thresholds (0.6^(n-1) weights, 10-20/3-20 cluster bounds, 70% coverage, max 5 words) live in the scripts and must stay consistent.
  - Including prefix (intermediate) paths alongside their deeper children — step 1 keeps only leaf nodes to avoid redundant, overlapping clusters and double-counted parent concepts.
  - Skipping the per-source dedupe or doing it after text cleaning — dedupe on the raw `category_path` first, or cluster weights inflate and validation against originals breaks.
  - Keeping paths deeper than target_depth — they are too sparse and fine-grained to unify meaningfully and are filtered out by design.
  - Assuming the run hung during embedding or clustering — these take minutes for ~10k records; let the progress bar finish before intervening.
  - Forgetting the NLTK wordnet/omw-1.4 download — step 1 lemmatizes at import and will fail without it.
```

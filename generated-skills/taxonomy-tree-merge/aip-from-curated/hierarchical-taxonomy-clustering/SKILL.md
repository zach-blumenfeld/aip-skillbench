---
name: hierarchical-taxonomy-clustering
description: Build a unified multi-level category taxonomy from hierarchical product category paths collected from multiple e-commerce sources using embedding-based recursive clustering with intelligent category naming via weighted word frequency analysis. Use when the user needs to unify category trees across platforms, cluster hierarchical paths like "electronics -> computers -> laptops", or generate a clean N-level (default 5) taxonomy with automatically named categories for cross-source product analysis.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.2/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Build a unified multi-level category taxonomy (typically 5 levels) from
  hierarchical product category paths gathered from multiple e-commerce
  sources. Convert paths to weighted embeddings, recursively cluster at
  each level with cosine distance, and generate meaningful category
  names via weighted word frequency, lemmatization, and bundle-word
  logic so products from different platforms can be analyzed under a
  single shared taxonomy.

trigger_when:
  - User needs to unify category taxonomies across multiple e-commerce data sources.
  - Input is a collection of hierarchical category paths (e.g., "electronics -> computers -> laptops") that must be grouped, normalized, and renamed.
  - User wants a clean N-level (default 5) hierarchical taxonomy with automatically generated category names.
  - User needs cross-source product analysis or metric tracking under a shared taxonomy.

do_not_use_when:
  - Only flat (non-hierarchical) category clustering is required.
  - Categories must be manually curated or governed — automatic naming is unacceptable.
  - Single-source taxonomy cleanup that does not require cross-source unification.

steps:
  - name: install-dependencies
    description: >
      Install required Python packages and NLTK data before running the
      pipeline. Run `pip install pandas numpy scipy sentence-transformers
      nltk tqdm`, then download NLTK data via
      `python -c "import nltk; nltk.download('wordnet'); nltk.download('omw-1.4')"`.
  - name: step1-preprocessing-and-merge
    description: >
      Run `scripts/step1_preprocessing_and_merge.py`. Input: list of
      (DataFrame, source_name) tuples where each DataFrame has a
      `category_path` column. Per-source deduplication, text cleaning
      (remove &/,/'/-/quotes, drop "and"/"&"/",", lemmatize words as
      nouns), normalize the delimiter to ` > `, depth filtering, prefix
      removal, then merge all sources. The `source_level_*` columns
      reflect the processed version of each source's level name.
      Output: merged DataFrame with `category_path`, `source`, `depth`,
      and `source_level_1` through `source_level_N`.
  - name: step2-weighted-embedding-generation
    description: >
      Run `scripts/step2_weighted_embedding_generation.py`. Input:
      DataFrame from step 1. Convert paths to sentence-transformer
      embeddings with exponentially decaying weights per level —
      L1=1.0, L2=0.6, L3=0.36, L4=0.216, L5=0.1296 (0.6^(n-1)) — so
      top-level granularity dominates while deeper levels still
      contribute. Output: numpy embedding matrix shaped
      (n_records × 384). Expect 2-5 minutes for ~10,000 records; the
      progress bar shows encoding status.
  - name: step3-recursive-clustering-naming
    description: >
      Run `scripts/step3_recursive_clustering_naming.py`. Input:
      DataFrame plus embeddings from step 2. Hierarchically cluster at
      each level using average linkage with cosine distance — 10-20
      clusters at L1, 3-20 at L2-L5. Generate category names via
      weighted word frequency, lemmatization, and bundle-word logic,
      excluding all ancestor words (parent, grandparent, etc.) to
      avoid path duplicates, with coverage of ≥70% of records in each
      cluster. Output: assignments dict
      `{index → {level_1: …, level_5: …}}`. Expect 1-3 minutes for
      ~10,000 records as the system walks recursive levels.
  - name: step4-result-assignments
    description: >
      Run `scripts/step4_result_assignments.py`. Input: DataFrame plus
      assignments from step 3. Add `unified_level_1` through
      `unified_level_N` columns to each record. Names use the ` | `
      separator, max 5 words, covering ≥70% of records in each cluster
      (e.g., "electronic | device", "computer | laptop"). Output two
      CSVs: `unified_taxonomy_full.csv` (all records with unified
      categories) and `unified_taxonomy_hierarchy.csv` (unique
      taxonomy structure).

modes:
  - name: complete-pipeline
    body: >
      Default mode. Run `scripts/pipeline.py` to execute all four
      steps end-to-end. The script wires step1 → step2 → step3 →
      step4 and exports the final CSVs to the requested output
      directory. Use this whenever the caller does not need to inspect
      intermediate artifacts.
  - name: individual-steps
    body: >
      Advanced control. Invoke each `step*.py` script directly when
      the caller needs to inspect intermediate artifacts — cleaned
      merged DataFrame, embedding matrix, or assignments dict — or to
      tune parameters between stages.

decisions:
  - signal: ~10,000 records and encoding appears stalled in step 2.
    action: Wait — step 2 takes 2-5 minutes at this size. Watch the progress bar before assuming a hang.
  - signal: ~10,000 records and clustering appears stalled in step 3.
    action: Wait — step 3 takes 1-3 minutes as it walks recursive levels.
  - signal: User wants more or fewer top-level categories.
    action: Adjust `min_clusters_l1` (default 10) and `max_clusters` (default 20) when calling the pipeline.
  - signal: User wants finer or coarser sub-level granularity.
    action: Adjust `min_clusters_other` (default 3) for L2-L5 cluster floors.
  - signal: Target taxonomy depth differs from 5.
    action: Pass `target_depth` to the pipeline; depth filtering in step 1 will respect the new value.

scenarios:
  - need: Unify category trees from two e-commerce platforms with overlapping but inconsistently named paths.
    context: Each source DataFrame has a `category_path` column with paths like "Electronics & Computers > Laptops" on one side and "electronics -> computers -> laptops" on the other.
    action: Run the complete pipeline (`scripts/pipeline.py`) with both DataFrames passed as `[(df_a, "source_a"), (df_b, "source_b")]`. Step 1 normalizes delimiters and lemmatizes; step 3 names the unified clusters.
    outcome: Each record gains `unified_level_1` … `unified_level_5` columns under a single taxonomy (e.g., "electronic | device" → "computer | laptop"), enabling cross-platform metric tracking.

anti_patterns:
  - Skipping step 1 cleaning (lemmatization, delimiter normalization, prefix removal) — downstream clustering quality degrades because semantically identical paths look distinct.
  - Treating every level with equal weight instead of the 0.6^(n-1) decay — top-level granularity stops dominating and lower-level noise distorts clusters.
  - Allowing ancestor words to appear in child cluster names — produces path duplicates like "electronics | electronics-computer".
  - Calling the individual step scripts out of order — each step depends on the artifacts of the previous one.
  - Lowering the 70% cluster coverage threshold to force shorter names — the resulting names stop reflecting the cluster contents.
```

# hierarchical-taxonomy-clustering — AIP authoring notes

## What this is

AIP conversion of the curated Agent Skill `hierarchical-taxonomy-clustering`
(the `aip-from-curated` track for the `taxonomy-tree-merge` task). The
canonical original is preserved verbatim at `source/ORIGINAL_SKILL.md`; all
five pipeline scripts are copied verbatim into `scripts/`.

## Source materials

- `source/ORIGINAL_SKILL.md` — verbatim copy of the curated `SKILL.md`.
- `scripts/pipeline.py` — verbatim. Orchestrates the 4 steps end to end; has a
  CLI (`--sources path:name ... --output DIR --depth --min-l1 --max-clusters
  --min-others`) and a `run_pipeline()` function.
- `scripts/step1_preprocessing_and_merge.py` — verbatim. Per-source dedupe,
  text cleaning + lemmatization, delimiter normalization, depth filter, level
  split, prefix-path removal, merge.
- `scripts/step2_weighted_embedding_generation.py` — verbatim. all-MiniLM-L6-v2
  (384-dim) encoding with per-path normalized 0.6^(n-1) level weights.
- `scripts/step3_recursive_clustering_naming.py` — verbatim. Average-linkage
  cosine agglomerative clustering, recursive dendrogram cutting, weighted
  word-frequency naming with bundle-word logic and ancestor/duplicate exclusion.
- `scripts/step4_result_assignments.py` — verbatim. Applies assignments and
  exports the two CSVs plus quality metrics.
- `source/procedure.schema.json` — the AIP `procedure` schema (v0.3a2) the body
  validates against. Bundled locally so the skill is self-contained.

## Schema choice

`procedure` schema (reused, not drafted). The curated skill is explicitly a
"4-step pipeline" — a linear execution graph of script-backed nodes connected
by inputs/outputs (merged DataFrame → embeddings → assignments → CSVs). That is
exactly what the procedure schema models. No skill-specific schema was needed.

## How the original maps to the AIP structure

- The four documented pipeline steps become four `script`-backed graph nodes
  (`preprocess-and-merge`, `generate-embeddings`, `recursive-cluster-and-name`,
  `apply-and-export`) wired with `depends_on` and matching input/output names.
- A leading `install-dependencies` step captures the Installation section. It
  is prose (no `script`) because it is a fixed pip/nltk setup command, not
  data-dependent logic.
- The "Usage" section (run `pipeline.py` for the whole flow vs. call individual
  steps for advanced control) maps to two `modes`: `full-pipeline` and
  `step-by-step`.

## Why every computational step is script-backed

AIP best practice requires that numeric thresholds, lookup tables, and
conditional logic live in `scripts/`, not prose. All of it already does in the
curated scripts: the 0.6^(n-1) weight decay, the 10-20 (L1) / 3-20 (L2-L5)
cluster bounds, the 70% coverage threshold, the max-5-words and bundle-word
selection, depth filtering, and prefix removal. Step descriptions are therefore
one-line summaries that name the key knobs and point at the script; the script
is the source of truth.

## Source-content classification (completeness check)

- Title + Problem statement → **Mapped** to `purpose` and `trigger_when`.
- Methodology bullets (hierarchical weighting, recursive clustering, intelligent
  naming, quality control) → **Mapped** across the relevant step descriptions
  (`generate-embeddings`, `recursive-cluster-and-name`) and `anti_patterns`;
  the algorithms themselves live in steps 2-3 scripts.
- Output section (unified_level_1..N columns, ` | ` separator, max 5 words, 70%+
  coverage) → **Mapped** to the `apply-and-export` and `recursive-cluster-and-name`
  descriptions and the `full-csv` / `hierarchy-csv` outputs.
- Installation commands → **Mapped** to the `install-dependencies` step and
  `compatibility` frontmatter.
- Step 1-4 descriptions (inputs/process/outputs, including the weights table and
  the depth/dedupe/prefix rules) → **Mapped** to the four script-backed steps
  with explicit `inputs`/`outputs`.
- Performance notes (2-5 min embeddings, 1-3 min clustering for ~10k records;
  "be patient") → **Mapped** to step descriptions and a "don't assume it hung"
  `anti_pattern`.
- Usage section (pipeline.py end-to-end vs. individual steps) → **Mapped** to
  the two `modes`.
- Natural path termination (naming returns None when words are exhausted /
  duplicate) → **Mapped** to a `scenario` and the `recursive-cluster-and-name`
  description.
- No content was dropped. The CLI `path:name` source-spec format, which lives
  only in `pipeline.py`'s argparse, is surfaced in the `full-pipeline` mode so
  the agent can invoke it without reading the script.

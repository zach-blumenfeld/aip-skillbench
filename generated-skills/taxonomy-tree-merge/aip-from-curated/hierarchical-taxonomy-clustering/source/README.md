# Source materials — hierarchical-taxonomy-clustering (AIP from curated)

This directory holds the inputs used to compile the AIP version of the
`hierarchical-taxonomy-clustering` skill.

## Inputs

- `original-SKILL.md` — the curated freeform-markdown SKILL.md from
  `vendor/skillsbench/tasks/taxonomy-tree-merge/environment/skills/hierarchical-taxonomy-clustering/`,
  copied verbatim. The compiled `SKILL.md` at the skill root must
  preserve the same `name:` and the same operational intent.
- `procedure.schema.json` — the AIP schema this skill validates
  against. The `procedure` schema fits because the source is a
  four-step linear pipeline with optional individual-step execution,
  clear triggers, and concrete anti-patterns.

## Compilation logic

1. **Schema choice.** `procedure.schema.json` covers the source 1:1:
   `purpose`, `trigger_when`, ordered `steps`, optional `modes`
   (complete pipeline vs individual steps), `decisions` (performance
   timing reassurance, tuning parameters), `scenarios`, and
   `anti_patterns`.
2. **Name.** The frontmatter `name:` is held at
   `hierarchical-taxonomy-clustering` to match the task's mounted
   skill folder name. Do not rename.
3. **Steps.** The four pipeline scripts (`step1`–`step4`) plus the
   `install-dependencies` prerequisite become five typed steps in
   list order. `parallel` and `depends_on` are unused — the pipeline
   is strictly linear.
4. **Modes.** Two modes captured: `complete-pipeline` (default, runs
   `pipeline.py`) and `individual-steps` (advanced control, invoke
   each `step*.py` directly).
5. **Decisions.** Performance-timing hints from the source (step 2
   takes 2-5 min, step 3 takes 1-3 min for ~10k records) and the
   cluster-count tuning levers are encoded as signal→action rows.
6. **Anti-patterns.** Drawn from the methodology's quality-control
   rules (exclude ancestor words, weight levels exponentially,
   preserve step ordering).

## Source-coverage classification

Every distinct piece of `original-SKILL.md` content is accounted for:

| Source content | Disposition |
|---|---|
| Problem statement | Mapped → `purpose` |
| Methodology bullets (weighting, recursive clustering, naming, quality control) | Mapped → embedded across step descriptions and `anti_patterns` |
| Output description | Mapped → step4 description |
| Installation block | Mapped → `install-dependencies` step |
| 4-step pipeline detail | Mapped → `steps` |
| Performance notes ("expect 2-5 minutes…") | Mapped → step descriptions and `decisions` |
| Usage section (pipeline.py vs individual steps) | Mapped → `modes` |
| Category-name format rules (` | ` separator, max 5 words, 70% coverage) | Mapped → step4 description |

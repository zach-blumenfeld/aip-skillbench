# memory-optimization — AIP conversion notes

## Source

- `source/SKILL.md` — original curated freeform-markdown skill bundled with the `parallel-tfidf-search` SkillsBench task.
- `source/advanced_techniques.md` — original `references/advanced_techniques.md` from the curated skill.
- `source/procedure.schema.json` — the AIP schema this skill validates against (procedure family).

## Schema choice

This is a **procedure**: a multi-step workflow (profile → analyze → select → transform → verify) the agent walks end-to-end. The existing `procedure.schema.json` already covers steps with inputs/outputs, modes (decision branches), scenarios, and anti-patterns — no new schema needed.

## Script vs prose decisions

The curated skill is dominated by **pattern templates** (Class→`__slots__`, list→generator, sparse, flyweight, etc.) and **decision-tree judgment** ("what's consuming memory? → which optimization fits?"). Those are interpretation-heavy and stay as prose steps.

The one truly mechanical sub-procedure is **pandas DataFrame dtype downcasting** — a fixed rule chain (int64→smallest int → float64→smallest float → low-cardinality object → category → integral-float → Int64) with a single tunable (`category_threshold`). Promoted to `scripts/optimize_dtypes.py` because:

- pure deterministic rules over structured input (DataFrame dtypes)
- numeric threshold (`category_threshold = 0.5`)
- a lookup-style chain (each dtype → its downcast rule)
- prone to silent breakage if the agent re-implements it inline (column-order accidents, missing the integral-float→Int64 demotion)

Other patterns stayed as prose: they're code templates the agent has to adapt to the user's specific class / file / DataFrame — not deterministic transformations over a fixed input shape.

## Completeness mapping (source → AIP body)

| Source section                              | Disposition         | Where |
|---------------------------------------------|---------------------|-------|
| Workflow (5 steps)                          | **Mapped**          | `steps` |
| Memory Optimization Decision Tree           | **Mapped**          | `steps.select-strategy.description` + `modes` |
| Pattern 1: Class to `__slots__`             | **Mapped**          | `steps.transform.description` (inline) |
| Pattern 2: List to Generator                | **Mapped**          | `steps.transform.description` (inline) |
| Pattern 3: Downcast Numeric Types           | **Mapped (scripted)** | `scripts/optimize_dtypes.py` + step `transform` |
| Pattern 4: String Deduplication             | **Mapped**          | `steps.transform.description` (inline) |
| Pattern 5: Memory-Mapped File Processing    | **Mapped**          | `steps.transform.description` (inline) |
| Pattern 6: Chunked DataFrame Processing     | **Mapped**          | `steps.transform.description` (inline) |
| Data Structure Memory Comparison table      | **Mapped**          | `steps.select-strategy.description` (inline table) |
| Memory Leak Detection table                 | **Mapped**          | `steps.analyze.description` (inline table) |
| Profiling Commands                          | **Mapped**          | `steps.profile.description` |
| Verification Checklist                      | **Mapped**          | `steps.verify.description` |
| Advanced patterns (`references/advanced_techniques.md`) | **Mapped (deferred)** | Body references `references/advanced_techniques.md`; full content copied verbatim into the new skill's `references/` |

No deliberate drops. Every section from the curated skill is reachable from the AIP body, either inline or via the on-demand reference.

## Task fit (parallel-tfidf-search)

This skill is one of three in the task's environment (`memory-optimization`, `python-parallelization`, `workload-balancing`). It's the one the agent reaches for when parallel workers blow up RSS — sharing the inverted index across workers, deciding between sparse-vs-dense TF-IDF matrices, and chunking the document stream so multiprocessing fanout doesn't multiply per-worker memory by N. The AIP body keeps the original's general-purpose framing — no task-specific narrowing — so it composes cleanly with the sibling skills.

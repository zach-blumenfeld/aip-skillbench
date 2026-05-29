# workload-balancing — source notes

## Origin

Compiled from the curated Agent Skill at:

    vendor/skillsbench/tasks/parallel-tfidf-search/environment/skills/workload-balancing/

Source materials carried into `source/`:

- `original-SKILL.md` — verbatim copy of the curated skill body.
- `procedure.schema.json` — bundled copy of the AIP procedure schema this
  skill validates against (canonical $id points to the upstream URL).

Carried into the skill root, unchanged:

- `references/advanced_techniques.md` — distributed-system patterns
  (consistent hashing, rate-limited queue, priority balancing,
  circuit breaker, adaptive batching, locality-aware scheduling,
  MapReduce shuffling, exponential backoff with jitter).

## Schema choice

Reused `procedure.schema.json` (no new schema drafted). The curated
skill describes a five-phase execution graph (characterize → identify →
select → implement → monitor) plus five canonical strategies and
straggler-handling logic. That maps cleanly onto the procedure shape:
typed steps with inputs/outputs, `one_of` for strategy selection, plus
optional `anti_patterns` and `scenarios`. No procedure-shape gaps were
found.

## Script vs. prose decisions

| Step | Choice | Rationale |
|------|--------|-----------|
| characterize-workload | prose | Requires judgment of task-time variance, predictability, resource constraints. Not a fixed lookup. |
| identify-bottlenecks | prose | Bottleneck interpretation hinges on reading runtime signals; agent reasons. |
| select-strategy | prose with `one_of` | Decision tree from source body; alternatives are mutually exclusive. Branch selection is interpretive — the inputs (workload-profile) are loosely-specified. |
| implement-balancing | prose | Code template selection and adaptation belongs to agent reasoning over the reference implementations carried in the body. |
| measure-balance | **script** (`balance_metrics.py`) | Pure formula: `max(load)/mean(load)`, `max(t)/median(t)`, `mean(t)/wall`, `stdev(queue)`. Numeric thresholds (1.2, 2.0, 0.9) from the source "Monitoring Metrics" table baked into verdicts. |
| weighted-partition (sub-step of implement) | **script** (`weighted_partition.py`) | LPT (longest-processing-time-first) bin packing is a fixed deterministic algorithm with a known approximation guarantee. Same code as source Strategy 4, hardened into a CLI. |
| handle-stragglers | prose | Selection between timeout/speculative/rebalance depends on workload character. Implementations stay as reference snippets in the body. |
| verify | prose | Checklist walk; agent applies the metric script's verdict alongside correctness checks. |

## Completeness audit (source → body classification)

| Source content | Status |
|----------------|--------|
| Workflow (5 phases) | **Mapped** → `steps` |
| Load-balancing decision tree | **Mapped** → embedded in `select-strategy` description with `one_of` |
| Strategy 1 — Static Chunking | **Mapped** → reference snippet in `implement-balancing` |
| Strategy 2 — Dynamic Task Queue | **Mapped** → reference snippet |
| Strategy 3 — Work Stealing | **Mapped** → reference snippet |
| Strategy 4 — Weighted Distribution | **Mapped** → reference snippet + `weighted_partition.py` |
| Strategy 5 — Async Semaphore | **Mapped** → reference snippet |
| Partitioning Strategies table | **Mapped** → `select-strategy` description |
| Handling Stragglers (3 techniques) | **Mapped** → `handle-stragglers` step |
| Monitoring Metrics table | **Mapped** → `balance_metrics.py` (formulas + thresholds) |
| Anti-Patterns table | **Mapped** → `anti_patterns` |
| Verification Checklist | **Mapped** → `verify` step |
| advanced_techniques.md | **Mapped** → preserved verbatim under `references/`, loaded on demand |

No deliberate drops.

## Task context

Mounted into the `parallel-tfidf-search` SkillsBench task. Performance
targets the task expects:

- 1.5× speedup on parallel index building over sequential
- 2.0× speedup on parallel batch search over sequential
- Identical results to the sequential reference

This skill provides the balancing layer; pair it with
`python-parallelization` (process/thread/async choice) and
`memory-optimization` (per-worker memory) which are also mounted on
the task.

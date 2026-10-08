# parallelize-python — source and compilation notes

## Provenance

The originals are copied verbatim into this folder:

| Source | Path here |
|---|---|
| `python-parallelization/SKILL.md` + `references/advanced_techniques.md` | `source/python-parallelization/` |
| `workload-balancing/SKILL.md` + `references/advanced_techniques.md` | `source/workload-balancing/` |
| `memory-optimization/SKILL.md` + `references/advanced_techniques.md` | `source/memory-optimization/` |

Domain context also came from the task environment: a `python:3.12-slim` container with no third-party packages, and a workspace containing `sequential.py` (TF-IDF index build, cosine search, batch search) and `document_generator.py` (synthetic corpus with log-normal document lengths). Neither file is copied into the pack, because the pack must work on whatever sequential code it is given. A stdlib-only parallel prototype of that workload was built and measured in a scratch directory during authoring. Its measurements and gotchas are written up in `references/map-reduce-index.md`; that reference is authored and is not in the source skills.

## Intent

The three source skills describe one workflow: profile → classify → select a strategy → transform → verify. They differ only in the concern each covers: parallel strategy, distributing the work, and memory. The compiled procedure runs that workflow once, with each concern as a dimension of the same plan:

```
inspect (script) → characterize (client) → classify (decision) → plan (script) → by-route
   ├─ parallelize          → implement-parallel (client) ─┐
   └─ optimize_sequential  → implement-sequential (client)┤
                                                          → evaluate (script) → by-verdict
                                                              ├─ pass   → end
                                                              ├─ revise → revise (client) → evaluate
                                                              └─ stop   → end   (after max_attempts = 3)
```

## Step-kind choices

| Step | Kind | Why |
|---|---|---|
| inspect | execution | Finding nested loops over independent collections, lambdas passed to pools, I/O calls in loops, classes without `__slots__`, CPU count/cgroup quota/affinity, start methods, memory limit and importable packages is all deterministic. The agent would otherwise guess these, for example assuming numpy exists in `python:3.12-slim`. |
| characterize | client_task | Reading the task's exact API and thresholds, and writing a timing script for the specific target function, takes judgment and code generation. A generic script cannot know which function or which input size matters. |
| classify | decision | Goal, workload type, dependency structure, cost variance, shared-input size and exactness are judgments with a fixed answer space. These are the branch points of the three source decision trees. |
| plan | execution | The decision trees are lookup tables over those answers (`assets/strategy_rules.json`). The script also runs a partitioning simulation (contiguous, round-robin, LPT, dynamic chunking) on the measured item weights, plus the Amdahl bound, the over-parallelization threshold, the CPU-quota check and the memory-copy check. All of this is numeric logic. |
| by-route | router | Parallelize, or optimize sequentially when the goal is memory, the iterations are loop-carried, or the workload is too small. The task can force the parallel route through `must_parallelize`. |
| implement-parallel / implement-sequential | client_task | Writing code. Each template carries the ordered workflow, the plan, and the verification harness (`assets/harness_template.py`). |
| evaluate | execution | Grades the measured verification against fixed targets from the monitoring-metrics table and the verification checklists: imbalance < 1.2, straggler ratio < 2.0, utilization > 90%, speedup > 1 or the task's minimum, memory limit, memory reduced when memory is the goal. Deterministic. |
| by-verdict | router | Validation loop with an attempt cap, so the procedure always terminates. |
| revise | client_task | Fixing code, guided by a cause → fix list. |

## Where the source content lives

- **python-parallelization**
  - Workflow → the step sequence.
  - Decision tree → `strategy_rules.json` `executor` (workload type × dependency) and `no_numeric_libs_fallback`.
  - Patterns 1–4, candidates table, safety requirements, pitfalls → `references/parallel-patterns.md`. The pitfalls are also in `strategy_rules.pitfalls`; safety requirements are in `exactness` and `verification_checklist`; the candidate indicators are detected by `inspect_target.py`.
  - Verification checklist → `strategy_rules.verification_checklist`, graded by `evaluate.py`.
  - Advanced techniques → `references/parallel-patterns.md`.
- **workload-balancing**
  - Workflow → characterize/plan/evaluate.
  - Decision tree → `strategy_rules.balancing` and `resource_constraints`, plus the measured-weight cross-check in `plan_strategy.py`.
  - Strategies 1–5, partitioning table, straggler handling, monitoring metrics, anti-patterns → `references/balancing-strategies.md`. Metric targets are in `strategy_rules.targets` and `evaluate.py`; the anti-patterns are in `anti_patterns`; the partitioning strategies are simulated in `plan_strategy.py`.
  - Verification checklist → `verification_checklist`.
  - Distributed patterns → the same reference.
- **memory-optimization**
  - Workflow → implement-sequential.
  - Decision tree → `strategy_rules.memory_tactics` and `references/memory-patterns.md`.
  - Patterns 1–6, size table, leak table, profiling commands → `references/memory-patterns.md`. Profiling is also in the characterize and implement-sequential templates; classes without slots are detected by `inspect_target.py`.
  - Verification checklist → `verification_checklist`, plus the memory checks in `evaluate.py`.
  - Advanced patterns → the same reference.

## Edits to source code while copying into references

- `workload-balancing` Strategy 2 used `wait`/`FIRST_COMPLETED` without importing them, imported unused `as_completed`/`Queue`, and used `list.pop(0)`. Fixed in `references/balancing-strategies.md`: the imports now match, and pending items are a `deque`.
- Section headings were demoted one level so that the three files read as single documents.

## Deliberate drops

| Item | Rationale |
|---|---|
| The per-skill one-line intros ("Transform sequential Python code to leverage…", "Distribute work efficiently…", "Transform Python code to minimize memory usage…") | Redundant with `purpose` and `description`. |
| Separate per-skill "Workflow" lists as literal text | Each workflow became the step graph itself: profile/analyze/characterize → inspect + characterize; classify/identify → classify; select → plan; transform/implement → implement-*; verify/monitor → evaluate. |
| Queue-depth-variance metric target ("Low") from the monitoring table | No numeric threshold, and pool-based designs have no per-worker queues to measure. The metric is kept in `references/balancing-strategies.md`. |
| Frontmatter `description` fields of the three sources | Merged into the compiled `description` and `trigger_when`. |

## Changes from functional testing

Tests covered the author's own runs of every branch (parallelize → pass; optimize_sequential → revise → revise → stop), plus two fresh-agent sessions: TF-IDF build and search, and a long-tailed log-file analytics job. Both sessions passed on their first attempt with outputs identical to the baselines. Their findings were fixed as follows:

- **Chunk count.** "~4 chunks per worker" created a straggler when one item outweighed an average chunk. `plan_strategy.py` now caps the LPT chunk count at total weight / largest weight, emits `best_balance[W]` with a concrete chunk count, warns when no item-level partition gets under 1.2, and breaks near-ties toward LPT chunks handed out dynamically, since weights are only a proxy.
- **Input-generation hotspots.** Nested loops in input-generator functions (`make_*`, `generate_*`) are tagged `likely_input_generation` and listed under `hotspots_in_input_generation_ignore`, not under the fixes to make.
- **Interpreter probe.** The probe and profile used the aip CLI's interpreter. An optional start key, `python_executable`, now probes and profiles with the task's interpreter.
- **Amdahl bound.** The bound is relabeled `amdahl_max_speedup_parallelism_alone`. The fixes are flagged mandatory when only they can reach the target.
- **Harness.** It now times each public function separately (`FUNCTIONS`/`PRIMARY` → `per_function`, also graded by `evaluate.py`), measures balance in-process via `measure_chunk_costs`, and keeps `__pycache__` out of the deliverable folder with `PYTHONDONTWRITEBYTECODE=1`.
- **Characterize.** It now reports `weight_stats` (cv, max_over_median, max_share), and the `task_variance` criteria use the same numeric cut-offs as the plan script, with long_tail taking precedence.
- **Smaller fixes:** `num_workers=None` is capped at the item count, a `chunk_size` API parameter is treated as an upper bound on items per chunk, `evaluate` declares `deliverable_path`, and missing balance metrics produce a warning.

Not fixed, because they are runtime behaviour outside the pack: state renders into templates as Python reprs, pauses exit with code 3, and the decision pause does not display thresholds.

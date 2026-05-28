# Research plan & learnings — human-curated vs AIP-from-curated

Living document for the study comparing **human-curated skills (mode 2)** against **AIP-from-curated skills (mode 5)** — the same human knowledge, repackaged into AIP form. Companion to `skill_correlations.ipynb` (corpus structure analysis) and the `reports/` eval write-ups.

## The question

Both arms carry the *same* domain knowledge — AIP only repackages it. So the question is not "does AIP add knowledge" but:

> **Does AIP-formatting a human-curated skill make an agent more successful, faster, and more consistent — and when does it help most?**

Dependent variables (success is only one, and the one that ceilings):
- **success** — pass rate / mean reward (mean reward preferred: survives ceilings, handles graded verifiers)
- **efficiency** — wall clock, tool calls (does *not* ceiling)
- **consistency** — within-task variance across trials (does *not* ceiling)
- **cost** — tokens/$ — *not yet measurable* (see Limitations)

## What we've learned so far

Evidence from `eval-1-haiku` (6 tasks × 5 modes × 5 trials, Haiku, AIP v0.2), `eval-2-haiku` (10 tasks, Haiku, v0.2), and `eval-3med-sonnet-v0_3a2` (3 medium tasks × {human, aip-inst, aip-cur} × 5 trials, Sonnet, AIP v0.3a2).

1. **The corpus is noisy at the extremes.** Most tasks ceiling (solver aces unaided) or floor (solver fails regardless of skill); only "on-the-bubble" tasks differentiate modes. Haiku floored nearly all hard tasks → eval-1's all-hard cut was the wrong corpus for that solver.

2. **AIP-cur preserves the human signal, then beats it.** Aggregate pass rate aip-cur ≈ human on Haiku (mode 5's design promise). On Sonnet + v0.3a2 (eval-3med): **aip-cur 15/15 (mean r 1.00), human 11/15 (0.85), aip-inst 0/15 (0.18)** — aip-cur was strictly dominant *and* faster.

3. **Two distinct mechanisms by which AIP-cur > human** (from deep dives):
   - **Add executability** (`drone-planning-control`): human skill was prose-only (0 scripts); AIP added ~1,377 LoC of runnable scripts → agent *runs* vetted code instead of authoring a control stack from prose. 5/5 @ 734 s vs human 2/5 @ 1279 s (one 21-min stall).
   - **Compress + structure** (`crystallographic-wyckoff`): human had scripts but ~1,200 lines of verbose prose; AIP trimmed prose into a short body + numbered steps → less deliberation. Near-deterministic 81.7–84.0 s (±1.5 s) vs human's 138–255 s spread, 5/5 vs 4/5.

4. **Structure alone doesn't predict benefit — implementation burden is a second axis.** `earthquake-plate` and `drone` are *both prose-only* at similar `prose_loc`, yet AIP gave **zero** benefit on earthquake-plate (human already 5/5; AIP added only 180 LoC) and the **whole win** on drone. Working model:
   > **AIP-cur benefit ≈ (room to add executability) × (implementation burden of the task).**
   `earthquake-plate` is a short deterministic pipeline (easy from prose); `drone` requires building+tuning a control system (error-prone from prose).

5. **(De-emphasized) aip-from-instruction is high-variance** and out of scope for this paper: it won earthquake-phase on Haiku (Opus inferred a better algorithm) but floored 0/15 on eval-3med (inferred wrong methods — distorting projection, brittle parser, unstable controller — frozen into the committed skill). We focus on human vs aip-cur.

## Measurement axes (from corpus analysis)

- **`structure_class`** (the AIP-upside axis): `prose-only` (50 tasks) / `mixed` (32) / `script-heavy` (13). prose-only = most room for AIP to add executability.
- **Structure ⊥ difficulty** — Spearman ~0.09–0.18, so they're independent axes; sample them separately, span difficulty as a covariate.
- **`prose_loc` ≈ `skill_md_loc`** (log r=0.85) — near-redundant; one prose-volume axis. Use `prose_loc` (includes reference docs).
- **Implementation burden has no single proxy.** `agent_timeout_sec` and `test_loc` are *uncorrelated* (r=0.04, p=0.71) — they measure different facets (time budget vs output scope). `task_type` heavy/light (`impl_class`: 29 heavy / 66 light) is an **unvalidated heuristic (n=2)**. Therefore: measure impl-burden **empirically** from the `noskill` baseline (authoring effort — `Write`/`Edit` counts, wall, iteration), and let the regression adjudicate among that + `agent_timeout_sec` + `test_loc` + `task_type`.

## Experimental design

- **Arms:** `human-curated` vs `aip-from-curated`. (`noskill` as anchor where feasible — measured separately to also serve as the impl-burden meter.)
- **Within-task paired:** both arms run the same task, same trials → the `aip_cur − human` delta is computed within task/cohort, robust to cross-cohort drift.
- **Stratify on `structure_class`** for coverage (not on a guessed driver); span difficulty + category as covariates.
- **n = 10 trials** (n=5 binomial CI is ±~22 pp — too loose; consistency is a DV and needs n for variance).
- **Analysis:**
  - main effect: per-task Δ, Wilcoxon signed-rank across tasks → "AIP ≥ human?"
  - gradient: regress Δ (reward, wall, variance) on `prose_loc` × impl-burden + difficulty + category → *which* feature predicts benefit (don't assume).
  - consistency: compare within-task variance between arms.
- **Cohorts: balanced, not by-cell.** Cohorts run at different times/machines; if cohort = cell, run-timing drift confounds the structure×impl axis. Each cohort is a mini-stratified sample (all 6 `structure × impl` cells, 3 hard each) so cohorts are interchangeable.

## Current status & plan

**Sample:** 24 fresh tasks (excludes the 3 eval-3med tasks), stratified across `structure_class × impl_class × difficulty`. Split into 3 balanced cohorts of 8 — `configs/eval-cohort-{a,b,c}-sonnet.yaml`. Difficulty 5 easy / 10 medium / 9 hard; 7 categories.

**Pipeline:**
1. **Convert** — `batch-convert --from curated` all 24 against AIP v0.3a2 (in progress).
2. **Run** — each cohort `human-curated` + `aip-from-curated`, n=10, Sonnet (`claude-sonnet-4-6`).
3. **Analyze** — combine cohorts A/B/C + the eval-3med 3 tasks; run a `noskill` pass to measure impl-burden; compute per-task Δ; Wilcoxon (main effect) + gradient regression + variance comparison.

**Solver:** `claude-sonnet-4-6`. **AIP spec:** v0.3a2.

## Open questions

- Does aip-cur > human **generalize** across the structure × impl grid, or only in specific cells?
- Is benefit driven by **structure**, **implementation burden**, or their **interaction**?
- Does AIP **reduce execution variance** generally (the crystallographic result, at scale)?
- *(Future)* Solver-dependence — does the benefit shrink as the model strengthens (Haiku vs Sonnet)?
- *(Future)* Token/$ cost — is aip-cur cheaper, not just faster?

## Known limitations

- **No token capture** — benchflow/`claude-agent-acp` record only tool calls, prompts, timing. Per-cell cost needs an `ANTHROPIC_BASE_URL` logging proxy or a benchflow patch (see repo README).
- **`impl_class` is an unvalidated heuristic** — used only as a coverage lever for sampling, never as the measured driver.
- **Reward verifiers are heterogeneous** (binary vs graded) — report mean reward and pass rate separately.

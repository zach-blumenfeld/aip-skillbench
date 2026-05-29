# Source notes — pareto-optimization (AIP)

## Origin

Converted from the curated Agent Skill at:

    vendor/skillsbench/tasks/mars-clouds-clustering/environment/skills/pareto-optimization/SKILL.md

The original is bundled here as `SKILL.original.md` for reference.

## Schema choice

Reused `procedure.schema.json` (AIP v0.3a3) rather than drafting a new
schema. Pareto extraction is a small linear procedure — frame the
objectives, filter, compute, format — so the procedure schema's
`purpose` / `trigger_when` / `steps` / `scenarios` / `anti_patterns`
shape carries it cleanly without adding new fields.

## Script vs. prose decisions

Per the AIP best-practices guidance ("script the deterministic /
mechanical parts; leave data-dependent conditional / branching logic as
prose"):

- **Scripted** — `scripts/compute_pareto.py` is the deterministic core:
  paretoset (preferred) or a vectorized numpy fallback over an array of
  numeric objective columns. It also absorbs the *mechanical* parts of
  the surrounding steps that are easy to get wrong by hand: pre-filter
  by simple comparisons (`--filter "F1 > 0.5"`), per-column rounding
  (`--round COL:DECIMALS`), output column ordering (`--columns`), and
  sort. All of these are fixed lookup-table / numeric work — exactly
  what the AIP guide says to script.
- **Prose** — `frame-objectives`, the *interpretation* in
  `prefilter-results`, and `format-output` stay prose. Choosing which
  columns are objectives (vs hyperparameters vs quality gates), which
  thresholds apply, and what header / precision the task expects all
  hinge on reading the task spec — they are judgment calls the agent
  must reason through, not mechanical transforms. Scripting them would
  over-restrict (e.g., bake one specific filter into a generic skill).
- **Visualization** — `scripts/visualize_pareto.py` is a small,
  optional companion. Plotting is mechanical but not required for
  correctness; it is offered as a sanity-check / reporting utility,
  not a step in the main graph.

## Source-content classification

Walking the original `SKILL.md` line-by-line:

| Source content                                          | Disposition  | Where in AIP body                                                |
|---------------------------------------------------------|--------------|------------------------------------------------------------------|
| Intro framing (multi-objective optimization)            | Mapped       | `purpose`                                                        |
| "Pareto Dominance" definition                           | Mapped       | `purpose` (definitional), reinforced via `anti_patterns`         |
| "Pareto Frontier" definition + trade-off framing        | Mapped       | `purpose`, `properties` section absorbed into `anti_patterns`    |
| `paretoset` library usage                               | Mapped       | `scripts/compute_pareto.py` (primary path)                       |
| Manual implementation (`is_dominated`, `compute_pareto_frontier`) | Mapped       | `scripts/compute_pareto.py` (vectorized numpy fallback)          |
| "Model Selection" worked example                        | Mapped       | `scenarios[1]`                                                   |
| Visualization snippet                                   | Mapped       | `scripts/visualize_pareto.py` + `scenarios[2]`                   |
| "Properties of Pareto Frontiers" (trade-off, no single best, decision-making) | Mapped       | `purpose` + `anti_patterns` ("treating best-F1 as the answer")   |
| Prefilter pattern (`results[results['accuracy'] >= 0.85]`) | Mapped       | `steps.prefilter-results` + script `--filter`                    |
| (none dropped)                                          | —            | —                                                                |

## What the original did not cover (additions)

The curated source teaches the algorithm but not the *integration* with
the consuming task. The AIP version adds three operational steps that
the mars-clouds-clustering task exposes:

- **Quality gates as a distinct concept** (`prefilter-results`). The
  original showed a one-line filter inside the model-selection example
  but did not flag it as a step you must consciously do *before* the
  frontier. Forgetting it pulls failing configurations onto the
  frontier.
- **Output formatting as a step** (`format-output`). The task spec
  specifies column order, per-column decimal precision, and (often) a
  sort order. The script's `--columns` / `--round` / `--sort-by` flags
  exist for this; the step makes it impossible to skip.
- **Numpy fallback in the script.** The original's manual O(N²)
  implementation runs as Python loops. The bundled script keeps the
  same semantics but vectorizes the dominance check, which matters when
  the sweep is on the order of 10³–10⁴ candidates (the mars-clouds
  sweep is 7 × 11 × 11 ≈ 850 candidates pre-filter, well within
  paretoset's comfort zone but still worth not hand-looping).

## Name preservation

`name: pareto-optimization` is preserved verbatim — the task at
`mars-clouds-clustering` mounts skills by directory name, and the
benchmark harness expects this exact slug.

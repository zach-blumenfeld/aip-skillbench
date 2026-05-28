# Pareto optimization — concepts

Read when the agent needs to reason about *why* a point is on or off the
frontier, or to explain trade-offs to the user. The runtime computation
itself does not require this file.

## Pareto dominance

Point **A dominates B** if both hold:
- A is **at least as good as** B in *every* objective (weak preference).
- A is **strictly better than** B in *at least one* objective.

Equivalence: A and B with identical objective vectors do not dominate
each other; both stay on the frontier.

## Pareto frontier (Pareto front)

The set of all non-dominated points. Every member represents an optimal
trade-off — improving one objective requires sacrificing another.

## Properties

1. **Trade-off curve.** Moving along the frontier improves one
   objective while worsening another.
2. **No single best.** All Pareto-optimal solutions are equally "good"
   in a multi-objective sense.
3. **Decision making.** Final selection depends on the user's
   preference between objectives — surface the frontier, do not collapse
   it to a single recommendation unless asked.

## Sense (max vs. min)

`paretoset` accepts a `sense` vector. Each entry is `"max"` or `"min"`
matching the objective columns. The script in
`scripts/compute_pareto.py` requires this explicitly — there is no
default, because forgetting which direction is "better" is the most
common Pareto bug.

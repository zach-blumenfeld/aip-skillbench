# Rules checklist

Run through this list manually after the validator passes — the validator
catches mechanical violations, but several rules ("representative enough",
"reasonable pyramid") require judgement.

## Rule 1 — Shape

- [ ] `unified_level_1` has between 10 and 20 distinct values.
- [ ] Every internal node has between 3 and 20 immediate children (a node with
      only one child is a smell — collapse the child up or merge with a sibling).
- [ ] The tree is broadly pyramidal: each level has at least as many nodes as
      the one above it, until you hit the leaf level.

## Rule 2 — Naming

- [ ] All names are ≤5 words.
- [ ] Multi-word names use ` | ` (space-pipe-space).
- [ ] Each non-leaf name is "representative enough" of its descendants
      — i.e., a human reader would expect at least ~70% of the descendant leaf
      names to fall under that label without surprise.

## Rule 3 — Standardization

- [ ] Casing is consistent within the unified taxonomy (don't mix
      `electronics` and `Electronics`).
- [ ] Synonyms are collapsed (`TVs` and `Televisions` → one canonical form).
- [ ] Plural/singular usage is consistent at each level.

## Rule 4 — Parent/child distinctness

- [ ] No child name shares a word stem with its parent name. If the parent is
      `Computers | Tablets`, the child must not be `Tablets` or
      `Computer | Cases` — pick `Cases` or `Carrying Cases` instead.

## Rule 5 — Sibling distinctness

- [ ] For any set of siblings, pairwise word-token overlap is <30%. Tokenize
      on whitespace/`|`, lowercase, drop stopwords, then `|intersection| /
      min(|a|, |b|)`.

## Rule 6 — Cluster balance

- [ ] No top-level bucket holds more than ~30% of total leaf paths.
- [ ] No top-level bucket holds fewer than ~2% of total leaf paths (merge tiny
      buckets into a related neighbour or `Other | <theme>`).
- [ ] Mid-level subtrees within a top-level bucket are within ~3× of each
      other in leaf count.

## Rule 7 — Even source distribution

- [ ] For each top-level bucket, the share contributed by each of
      `amazon`/`facebook`/`google` is within roughly 0.5×–2× of the bucket's
      total share. (A bucket that only Google contributes to is a smell —
      either Google has a category the others don't, in which case fine, or
      Amazon and Facebook rows are being misrouted.)

## Final check

- [ ] Hierarchy file contains every prefix of every leaf path.
- [ ] Row counts in `unified_taxonomy_full.csv` equal the sum of input rows
      across the three source files. No input row is dropped or duplicated.

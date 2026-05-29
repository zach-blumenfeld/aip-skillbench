# source/ — search-restaurants AIP

## Intent

Lift the curated `search-restaurants` skill (a one-shot pandas helper that
filters a bundled CSV by city) into an AIP-validated procedure so an
agent can invoke it with the same guarantees the original Python class
provided.

## Source materials

- `ORIGINAL_SKILL.md` — verbatim copy of the upstream curated skill's
  SKILL.md (minimal: install + quick start).
- `ORIGINAL_search_restaurants.py` — verbatim copy of the upstream
  helper. The runtime copy lives at `../scripts/search_restaurants.py`
  and is identical.
- `procedure.schema.json` — bundled copy of the AIP procedure schema
  this skill validates against.

## Schema choice

Reuse `procedure.schema.json` (no new schema). The skill is a tiny
execution graph: normalize the user's city → call the lookup script →
hand results back. One script-backed step plus a thin prose framing
fits the procedure shape exactly; rulebook / doc-template schemas would
be over-fit.

## Script vs prose

Lookup, normalization (trim + case-insensitive match), and the
parenthetical-stripping variant are **deterministic** over structured
input — they belong in `scripts/search_restaurants.py` and remain
there verbatim. The agent-side prose only covers (a) deciding whether
to use the annotation-variant entry point and (b) interpreting the
two well-known "no data" / "no match" string returns, both of which
hinge on judgment, not lookup.

## Deliberate drops

The upstream SKILL.md's `pip install pandas` line is dropped from the
AIP body — pandas is a hard runtime dependency of the script, surfaced
via `compatibility` in frontmatter instead of a prose install step.
The "Quick Start" Python snippet is dropped from prose because the
AIP body points at the script directly; the equivalent invocation is
captured in `scenarios`.

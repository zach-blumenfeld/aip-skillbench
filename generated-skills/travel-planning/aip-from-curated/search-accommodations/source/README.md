# source/ — provenance for `search-accommodations` (AIP)

## What this skill is

A single-purpose lookup over the travel-planning accommodations dataset
(`accommodations/clean_accommodations_2022.csv`). Given a city name, the
backing script returns a `pandas.DataFrame` of matching rows projected to
eight columns — `NAME`, `price`, `room type`, `house_rules`,
`minimum nights`, `maximum occupancy`, `review rate number`, `city` —
with rows that have nulls in any selected column dropped. Two sentinel
strings cover the no-data and no-match cases.

Sibling skill to `search-cities`, `search-flights`,
`search-driving-distance`, `search-restaurants`, `search-attractions` in
the travel-planning bundle.

## Source materials

- `SKILL.md.original` — the curated `SKILL.md` shipped with the
  travel-planning task (vendored at
  `vendor/skillsbench/tasks/travel-planning/environment/skills/search-accommodations/SKILL.md`).
  The original body is intentionally thin: one paragraph, an `Installation`
  snippet (`pip install pandas`), and a Quick Start Python example. A
  truncated sentence ("Notice all the") in the original is a known stub —
  not a hidden directive — and was dropped in the AIP rewrite.
- `procedure.schema.json` — bundled local copy of the AIP procedure
  schema (`aip-schemas/procedure.schema.json`, spec `v0.3a2`). Same schema
  the sibling AIP search skills validate against; reused rather than
  hand-rolled.
- `../scripts/search_accommodations.py` — verbatim copy of the curated
  script. The AIP skill drives this through its CLI/Python interface; the
  script is the source of truth for the lookup logic (path resolution,
  column projection, null-drop, case-insensitive city match).

## Schema choice

`procedure.schema.json` (procedure-style AIP). The skill is a small
execution graph: resolve city → run script → branch on return type. Two
nodes, one script, a couple of sentinel branches. No need for a new
schema — the same schema covers the sibling lookup skills and keeps the
travel-planning corpus consistent.

## Authoring decisions

- **Two steps, not one.** The script does the lookup; the agent still
  has to interpret the union return (`DataFrame | str`) before passing
  results downstream. Splitting `lookup-accommodations-for-city` from
  `interpret-result` makes the type-branch explicit instead of burying
  it inside the script's caller.
- **`city_normalizer` documented as a constructor knob, not a step.**
  The curated script accepts an optional `Callable[[str], str]` for
  pre-match city normalisation. That's a hook for callers that want
  e.g. parenthetical-stripping; it doesn't change the procedure shape,
  so it lives in the step description and a `scenarios` entry rather
  than as its own node.
- **`do_not_use_when` added.** The original SKILL.md has no negative
  guidance. The procedure schema supports it and the sibling
  `search-restaurants` AIP skill uses it — added matching guidance
  (no city chosen yet, no pandas in runtime, batch cross-city queries).
- **Anti-patterns derived from the script, not the original SKILL.md.**
  The original is too thin to enumerate failure modes. The list in the
  AIP body is drawn from reading the script: sentinel-vs-DataFrame
  confusion, per-call reconstruction (the constructor reloads the CSV
  and prints `Accommodations loaded.`), assuming row order is ranked,
  passing annotated city strings without a normalizer, hard-coding the
  container data path.

## Completeness check vs source SKILL.md

| Source content                                       | Disposition |
|------------------------------------------------------|-------------|
| `name: search-accommodations`                        | Mapped (frontmatter, unchanged per task constraint). |
| `description` line                                   | Mapped and expanded (keyword-richer, sibling cross-refs added). |
| `# Search Accommodations` heading                    | Implicit in `purpose`. |
| "Find the accommodations for a specific city."       | Mapped (`purpose`, `steps[0]`). |
| Truncated sentence "Notice all the"                  | **Deliberate drop** — incomplete stub in the source. |
| `## Installation` / `pip install pandas`             | Mapped (`scope_and_approval`, `do_not_use_when`). |
| `## Quick Start` Python example                      | Mapped (`steps[0].description`, `scenarios[0]`). |

No schema gaps. No body drops.

## Re-validation

After any edit to `SKILL.md` or the bundled schema, run from the repo
root:

```
uv run .claude/skills/aip/scripts/validate.py \
  generated-skills/travel-planning/aip-from-curated/search-accommodations
```

The skill is committed only after a clean validator run.

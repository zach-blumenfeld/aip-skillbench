# Source — search-cities (AIP conversion)

## What this skill is

Looks up the list of cities present in the bundled travel-planning dataset
(`background/citySet_with_states.txt`) for a given first-level region (the
file calls these "states", but the vocabulary is broader than U.S. states —
see "Dataset shape" below). The dataset is the canonical universe of valid
origin/destination cities for every other travel-planning sibling skill
(flights, restaurants, attractions, driving distance, accommodations), so
this skill is the gate that decides which cities a downstream lookup may
legitimately be invoked on.

## Provenance

Adapted from
`vendor/skillsbench/tasks/travel-planning/environment/skills/search-cities/SKILL.md`
(captured verbatim as `ORIGINAL_SKILL.md` in this directory) and the
companion implementation at
`vendor/skillsbench/tasks/travel-planning/environment/skills/search-cities/scripts/search_cities.py`.
The original SKILL.md is a near-empty stub — three sentences plus a usage
snippet — so most of the AIP body is recovered from the script's actual
behaviour rather than the prose.

## Schema choice

- `procedure.schema.json` (procedure category) — the skill is a small,
  script-backed workflow (load mapping → look up state → interpret the
  union-typed return). No new schema required.

## Source → AIP mapping

| Original SKILL.md content                                         | AIP location                                                                |
| ----------------------------------------------------------------- | --------------------------------------------------------------------------- |
| Skill name + one-line description                                 | `name`, `description` frontmatter                                           |
| "Map states to their cities from the background text file."       | `purpose`                                                                   |
| Installation: "No external dependencies."                         | Implicit — no install step in `steps`. Captured in `scope_and_approval`.    |
| Quick Start usage snippet (`Cities().run("California")`)          | `scenarios[0]` + `lookup-cities-for-state` step description                 |
| Implementation behaviour (case-insensitive match, sentinel return) | `scripts/search_cities.py` (verbatim) + `interpret-result` step             |
| Default data path resolution (`/app/data` → relative fallback)    | `scripts/search_cities.py` + `lookup-cities-for-state` step description     |

## Notable additions vs. the original

The original SKILL.md does not document:

- **The dataset is not U.S.-only.** The "state" column carries
  non-U.S.-state entries — `England`, `Scotland`, `Ontario`, `Tuscany`,
  `Wallonia`, `Alexandria Governorate`, plus Caribbean/Pacific territories
  like `St. Thomas`, `Saipan`, `San Juan`, `Ponce`, `Aguadilla`. Calling
  the field "state" is a dataset convention, not a U.S. constraint. The
  AIP body says so explicitly so the agent does not reject foreign
  destinations on a wrong assumption.
- **The return type is a union.** `Cities.run` returns either
  `list[str]` (match) or one of two sentinel strings (`"Invalid state."`
  for no match, `"No city data is available."` for an empty dataset). The
  AIP body spells this out and the `interpret-result` step gates the
  three branches; the original Quick Start glosses over it.
- **State matching is case- and whitespace-insensitive on the input** but
  preserves the dataset's casing on output (`run` lowercases the input
  before comparing, but returns the cities verbatim).
- **Cities are returned in dataset order**, not sorted — the script
  appends to a `setdefault(...)` list in the order it encounters rows.
- **`Cities()` is expensive to construct** — it reads and parses the
  entire file on `__init__` and prints `"Cities loaded."`. The body warns
  the agent to reuse one instance across a session rather than calling
  it inside a hot path.
- **The data path resolves to `/app/data/...` first** (the Docker
  container layout), with a fallback to a path relative to the script.
  In the AIP install location the relative fallback will not exist; the
  skill is intended to run inside the task's container where `/app/data`
  is present, or with `--path` supplied.

## Deliberate drops

None. The original is short enough that every line is captured — the
"Installation" section ("No external dependencies.") becomes implicit
(there is no install step), and the Quick Start snippet survives as a
scenario.

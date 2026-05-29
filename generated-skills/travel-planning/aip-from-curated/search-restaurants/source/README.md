# Source — search-restaurants (AIP conversion)

## What this skill is

Retrieves restaurants for a given city from the bundled travel-planning
dataset (`restaurants/clean_restaurant_2022.csv`). The dataset rows carry
`Name`, `Average Cost`, `Cuisines`, `Aggregate Rating`, and `City`. The
skill is intended to be called once a destination city has already been
chosen (typically via `search-cities`) — it does not validate the city
against the canonical city/state mapping or surface alternatives when a
city has no entries.

## Provenance

Adapted from
`vendor/skillsbench/tasks/travel-planning/environment/skills/search-restaurants/SKILL.md`
(captured verbatim as `ORIGINAL_SKILL.md` in this directory) and the
companion implementation at
`vendor/skillsbench/tasks/travel-planning/environment/skills/search-restaurants/scripts/search_restaurants.py`.
The original SKILL.md is a stub — one descriptive line, a `pip install`
hint, and a Quick Start snippet — so the AIP body recovers most of the
specialised knowledge from the script's actual behaviour and the dataset
shape.

## Schema choice

- `procedure.schema.json` (procedure category) — the skill is a small,
  script-backed workflow (load CSV → look up city → interpret the
  union-typed return). No new schema required. This mirrors the sibling
  `search-cities` AIP skill.

## Source → AIP mapping

| Original SKILL.md content                                                | AIP location                                                                       |
| ------------------------------------------------------------------------ | ---------------------------------------------------------------------------------- |
| Skill name + one-line description                                        | `name`, `description` frontmatter                                                  |
| "Query restaurants for a given city."                                    | `purpose`                                                                          |
| `pip install pandas` installation hint                                   | `scope_and_approval` (records the pandas dependency; no install step)              |
| Quick Start usage snippet (`Restaurants().run("San Francisco")`)         | `scenarios[0]` + `lookup-restaurants-for-city` step description                    |
| Implementation behaviour (case-insensitive city match, sentinel returns) | `scripts/search_restaurants.py` (verbatim) + `interpret-result` step               |
| Default data path resolution (`/app/data` → relative fallback)           | `scripts/search_restaurants.py` + `lookup-restaurants-for-city` step description   |
| `Restaurants` class shape and column projection                          | `lookup-restaurants-for-city` step description + output schema                     |
| `run_for_annotation` and `get_city_set` helpers                          | `modes` (annotation variant) + `interpret-result` step (canonical-city-set probe)  |

## Notable additions vs. the original

The original SKILL.md does not document:

- **The return type is a union.** `Restaurants.run` returns either a
  `pandas.DataFrame` (match) or one of two sentinel strings
  (`"There is no restaurant in this city."` for an unknown city,
  `"No restaurant data is available."` for an empty dataset). The AIP
  body spells this out and the `interpret-result` step gates the three
  branches; the Quick Start snippet glosses over it entirely.
- **City matching is case- and surrounding-whitespace-insensitive on
  the input** but preserves the dataset's casing on output (the script
  lowercases for comparison only; the returned `City` column keeps
  whatever casing the CSV row has).
- **Returned columns are a fixed projection.** Only `Name`,
  `Average Cost`, `Cuisines`, `Aggregate Rating`, and `City` are
  retained, in that order. Rows with any null in those columns are
  dropped at load time (`dropna()` over the projection), so the
  returned frame is dense — no `NaN` to guard against downstream.
- **The reset index.** Results come back with a fresh `RangeIndex`
  (`reset_index(drop=True)`), so positional indexing on the returned
  frame is safe.
- **Restaurants are returned in dataset order**, not sorted by rating
  or cost. Sort downstream if a ranked display matters.
- **`Restaurants()` is expensive to construct** — it reads and parses
  the entire CSV on `__init__` and prints `"Restaurants loaded."`. The
  body warns the agent to reuse one instance across a session rather
  than rebuilding inside a per-city loop.
- **An annotation variant exists.** `run_for_annotation` strips a
  trailing parenthetical (e.g., `"San Francisco (CA)"` →
  `"San Francisco"`) before delegating to `run`. Useful when the
  upstream caller passes city strings that may carry a parenthetical
  region tag.
- **A canonical city-set probe.** `get_city_set()` returns the set of
  cities present in the dataset — handy for membership checks against
  the supported universe without paying the per-call DataFrame
  filter cost. The original SKILL.md mentions neither helper.
- **The data path resolves to `/app/data/...` first** (the Docker
  container layout), with a fallback to a path relative to the script.
  In the AIP install location the relative fallback will not exist;
  the skill is intended to run inside the task's container where
  `/app/data` is present, or with `--path` supplied.
- **pandas is required.** The original notes this in the install
  block; the AIP body records it under `scope_and_approval` so the
  agent knows to expect an `ImportError` outside an environment that
  has pandas installed.

## Deliberate drops

None. The original is short enough that every line is captured — the
Quick Start snippet survives as a scenario, and the `pip install pandas`
hint is recorded under `scope_and_approval` rather than as an install
step (the skill assumes the runtime already has its dependency).

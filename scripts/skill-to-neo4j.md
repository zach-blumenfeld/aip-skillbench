# Skill → Neo4j execution-graph connector

`scripts/skill_to_neo4j.py` maps AIP skill directories to a navigable execution
graph in Neo4j. Each `SKILL.md` carries a procedure-style graph in a fenced
`yaml` block (`steps` wired by named `inputs`/`outputs`, plus `depends_on`); the
connector turns that — plus the on-disk `references/` and `scripts/` and the
skill-level schema properties — into nodes and edges.

## Run it

```bash
# Whole corpus, fresh load (nukes all nodes + constraints + indexes first).
uv run python scripts/skill_to_neo4j.py generated-skills/ --clear

# One task pack, or one skill dir (idempotent MERGE — re-run updates in place).
uv run python scripts/skill_to_neo4j.py generated-skills/bike-rebalance
uv run python scripts/skill_to_neo4j.py generated-skills/travel-planning/aip-from-curated/search-flights

# Parse + report row counts without touching the DB.
uv run python scripts/skill_to_neo4j.py generated-skills/ --dry-run
```

Credentials are read from `reports/neo4j.txt` (`NEO4J_URI` / `NEO4J_USERNAME` /
`NEO4J_PASSWORD` / `NEO4J_DATABASE`), overridable by the same-named env vars or
`--uri/--user/--password/--database`.

Writes are **batched** (`UNWIND $rows`, one tx per row-type per ~1000-row chunk,
single session) — the whole 66-skill corpus loads in a few seconds. `--clear`
does a `ki nuke`-style reset: server-side batched `DETACH DELETE` then drops every
constraint and non-LOOKUP index.

## Graph model

```
(:Skill)-[:HAS_STEP {order}]->(:Step)
(:Step)-[:INPUT_TO {item,type,description,nullable}]->(:Step)   # data flow — item ON the edge
(:Skill)-[:PROVIDES {item,...}]->(:Step)                       # external input (no producer in-skill)
(:Step)-[:YIELDS {item,...}]->(:Skill)                         # terminal output (no consumer)
(:Step)-[:DEPENDS_ON]->(:Step)                                 # explicit ordering
(:Step)-[:RUNS]->(:Script)         (:Step)-[:REFERENCES]->(:Reference)
(:Skill)-[:HAS_SCRIPT]->(:Script)  (:Skill)-[:HAS_REFERENCE]->(:Reference)
(:Skill)-[:TRIGGERS_ON]->(:Trigger)        (:Skill)-[:AVOID_WHEN]->(:DoNotUse)
(:Skill)-[:WARNS]->(:AntiPattern)          (:Skill)-[:HAS_SCENARIO]->(:Scenario)
(:Skill)-[:INTEGRATES_WITH]->(:Integration)(:Skill)-[:HAS_MODE]->(:Mode)
(:Skill)-[:HAS_SHORTCUT]->(:SearchShortcut)
(:Skill)-[:PARTNERS_WITH]->(:Skill)        # integration partner resolved within the same task
```

Keys (for idempotent re-runs): `Skill.skill_id` and `Step.step_id` are repo-relative
paths (`Step.step_id = <skill_id>::<step name>`); `Script.path` / `Reference.path`
are repo-relative file paths; attribute nodes use a deterministic `uid`.

## View it (paste into Neo4j Browser)

```cypher
// One skill's whole execution graph — steps, data-flow, scripts, references.
MATCH (sk:Skill {name: 'search-flights'})
MATCH p = (sk)-[:HAS_STEP|INPUT_TO|PROVIDES|YIELDS|DEPENDS_ON|RUNS|REFERENCES|HAS_SCRIPT|HAS_REFERENCE*1..2]->()
RETURN p;

// The skill node wired to all its schema properties.
MATCH (sk:Skill {name: 'routing-subtour-elimination'})
MATCH p = (sk)-[:TRIGGERS_ON|AVOID_WHEN|WARNS|HAS_SCENARIO|INTEGRATES_WITH|HAS_MODE|HAS_SHORTCUT]->()
RETURN p;

// Linear data-flow chain with the I/O item printed on each hop.
MATCH (a:Step)-[f:INPUT_TO]->(b:Step)
WHERE a.skill_id ENDS WITH 'search-flights'
RETURN a.name AS from, f.item AS item, f.type AS type, b.name AS to;

// Cross-skill collaboration within a task pack.
MATCH p = (:Skill {task: 'civ6-adjacency-optimizer'})-[:PARTNERS_WITH]->(:Skill)
RETURN p;

// Steps that fan out (parallel) or branch (one_of).
MATCH (sk:Skill)-[:HAS_STEP]->(st:Step)
WHERE st.parallel OR size(st.one_of) > 0
RETURN sk.name, st.name, st.parallel, st.one_of;

// Which references / scripts are most reused across the corpus.
MATCH (st:Step)-[:REFERENCES]->(r:Reference) RETURN r.path, count(*) AS uses ORDER BY uses DESC LIMIT 20;
```

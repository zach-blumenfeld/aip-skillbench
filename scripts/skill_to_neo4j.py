#!/usr/bin/env python3
"""Map AIP skill directories to an execution graph in Neo4j.

An AIP skill (`SKILL.md`) carries a procedure-style execution graph in a fenced
``yaml`` block: ``steps`` connected by named ``inputs``/``outputs`` (the data-flow
edges) and explicit ``depends_on`` (the ordering edges), plus skill-level metadata
(``trigger_when``, ``scenarios``, ``anti_patterns``, ``integrations``, ...). On disk
each skill also ships ``references/*.md`` and ``scripts/*`` that steps point at.

This connector walks a directory, parses every ``SKILL.md`` it finds, and writes a
human-navigable graph to Neo4j:

  (:Skill)-[:HAS_STEP {order}]->(:Step)
  (:Step)-[:INPUT_TO {item,type,description,nullable}]->(:Step)   # data flow, item on the edge
  (:Skill)-[:PROVIDES {item,...}]->(:Step)                        # external input (no producer)
  (:Step)-[:YIELDS {item,...}]->(:Skill)                          # terminal output (no consumer)
  (:Step)-[:DEPENDS_ON]->(:Step)
  (:Step)-[:RUNS]->(:Script)        (:Step)-[:REFERENCES]->(:Reference)
  (:Skill)-[:HAS_SCRIPT]->(:Script) (:Skill)-[:HAS_REFERENCE]->(:Reference)
  (:Skill)-[:TRIGGERS_ON]->(:Trigger)     (:Skill)-[:AVOID_WHEN]->(:DoNotUse)
  (:Skill)-[:WARNS]->(:AntiPattern)       (:Skill)-[:HAS_SCENARIO]->(:Scenario)
  (:Skill)-[:INTEGRATES_WITH]->(:Integration)  (:Skill)-[:HAS_MODE]->(:Mode)
  (:Skill)-[:HAS_SHORTCUT]->(:SearchShortcut)
  (:Skill)-[:PARTNERS_WITH]->(:Skill)     # integration partner resolved to a known skill

Writes are batched: rows are accumulated across *all* skills and shipped to Cypher
via `UNWIND $rows AS row` in chunks (one transaction per row-type per chunk, in a
single session) rather than a transaction per skill. Re-runs are idempotent
(everything is MERGE-keyed on stable ids). Pass --clear to wipe the database first.

Usage:
    uv run python scripts/skill_to_neo4j.py generated-skills/ --clear
    uv run python scripts/skill_to_neo4j.py generated-skills/bike-rebalance

Credentials are read from reports/neo4j.txt (NEO4J_URI / NEO4J_USERNAME /
NEO4J_PASSWORD / NEO4J_DATABASE), overridable by the same-named env vars or
--uri/--user/--password/--database flags.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from neo4j import GraphDatabase

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CREDS_FILE = REPO_ROOT / "reports" / "neo4j.txt"
DEFAULT_BATCH_SIZE = 1000

# Match `references/foo/bar.md` and `scripts/foo.py` mentions inside prose fields.
REF_RE = re.compile(r"references/[\w\-./]+\.(?:md|txt|json|yaml|yml)")
SCRIPT_RE = re.compile(r"scripts/[\w\-./]+\.(?:py|sh|js|ts)")


# --------------------------------------------------------------------------- #
# Parsing
# --------------------------------------------------------------------------- #
@dataclass
class ParsedSkill:
    skill_id: str  # repo-relative path to the skill dir — stable, globally unique
    path: Path
    name: str
    description: str
    task: str
    mode: str
    spec: str | None
    schema_id: str | None
    proc: dict  # the parsed procedure yaml body
    references: list[str] = field(default_factory=list)  # repo-relative paths on disk
    scripts: list[str] = field(default_factory=list)


def _split_frontmatter(text: str) -> tuple[dict, str]:
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    if not m:
        return {}, text
    fm = yaml.safe_load(m.group(1)) or {}
    return fm, m.group(2)


def _extract_yaml_block(body: str) -> dict:
    m = re.search(r"```ya?ml\s*\n(.*?)```", body, re.S)
    if not m:
        return {}
    return yaml.safe_load(m.group(1)) or {}


def _rel(p: Path) -> str:
    try:
        return str(p.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(p.resolve())


def parse_skill(skill_md: Path) -> ParsedSkill | None:
    text = skill_md.read_text(encoding="utf-8")
    fm, body = _split_frontmatter(text)
    proc = _extract_yaml_block(body)
    if not proc:
        print(f"  ! no yaml procedure block in {skill_md} — skipping", file=sys.stderr)
        return None

    skill_dir = skill_md.parent
    aip = (fm.get("metadata") or {}).get("aip") or {}

    # Derive task / mode from the repo layout: generated-skills/<task>/<mode>/<skill>/
    parts = skill_dir.resolve().parts
    task = mode = ""
    if "generated-skills" in parts:
        i = parts.index("generated-skills")
        tail = parts[i + 1 :]
        if len(tail) >= 1:
            task = tail[0]
        if len(tail) >= 2:
            mode = tail[1]

    refs = sorted(_rel(p) for p in (skill_dir / "references").rglob("*") if p.is_file())
    scripts = sorted(_rel(p) for p in (skill_dir / "scripts").rglob("*") if p.is_file())

    return ParsedSkill(
        skill_id=_rel(skill_dir),
        path=skill_dir,
        name=fm.get("name") or skill_dir.name,
        description=fm.get("description", ""),
        task=task,
        mode=mode,
        spec=aip.get("spec"),
        schema_id=aip.get("schemaId"),
        proc=proc,
        references=refs,
        scripts=scripts,
    )


# --------------------------------------------------------------------------- #
# Row accumulation — one flat list per node/edge type across the whole corpus.
# Each list is written with a single batched UNWIND query (see WRITE below).
# --------------------------------------------------------------------------- #
@dataclass
class Rows:
    skills: list[dict] = field(default_factory=list)
    steps: list[dict] = field(default_factory=list)
    has_step: list[dict] = field(default_factory=list)
    references: list[dict] = field(default_factory=list)  # node + HAS_REFERENCE
    scripts: list[dict] = field(default_factory=list)  # node + HAS_SCRIPT
    flow: list[dict] = field(default_factory=list)  # Step -INPUT_TO-> Step
    provides: list[dict] = field(default_factory=list)  # Skill -PROVIDES-> Step
    yields: list[dict] = field(default_factory=list)  # Step -YIELDS-> Skill
    depends: list[dict] = field(default_factory=list)  # Step -DEPENDS_ON-> Step
    runs: list[dict] = field(default_factory=list)  # Step -RUNS-> Script
    step_refs: list[dict] = field(default_factory=list)  # Step -REFERENCES-> Reference
    triggers: list[dict] = field(default_factory=list)
    dnu: list[dict] = field(default_factory=list)
    anti: list[dict] = field(default_factory=list)
    scenarios: list[dict] = field(default_factory=list)
    integrations: list[dict] = field(default_factory=list)
    modes: list[dict] = field(default_factory=list)
    shortcuts: list[dict] = field(default_factory=list)


def _ios(items) -> list[dict]:
    """Normalize an inputs/outputs list of io_items into plain dicts."""
    out = []
    for it in items or []:
        if not isinstance(it, dict):
            continue
        out.append(
            {
                "name": it.get("name", ""),
                "type": it.get("type"),
                "description": it.get("description"),
                "nullable": bool(it.get("nullable", False)),
            }
        )
    return out


def accumulate(skill: ParsedSkill, rows: Rows) -> None:
    """Flatten one skill into the global row lists."""
    sid = skill.skill_id
    proc = skill.proc
    steps = proc.get("steps") or []

    rows.skills.append(
        {
            "skill_id": sid,
            "props": {
                "name": skill.name,
                "description": skill.description,
                "task": skill.task,
                "mode": skill.mode,
                "spec": skill.spec,
                "schema_id": skill.schema_id,
                "path": sid,
                "purpose": proc.get("purpose", ""),
                "scope_and_approval": proc.get("scope_and_approval", ""),
            },
        }
    )

    # references / scripts on disk, owned by the skill
    for rp in skill.references:
        rows.references.append({"skill_id": sid, "path": rp, "name": rp.rsplit("/", 1)[-1]})
    for sp in skill.scripts:
        rows.scripts.append({"skill_id": sid, "path": sp, "name": sp.rsplit("/", 1)[-1]})

    valid_refs = set(skill.references)
    valid_scripts = set(skill.scripts)

    def resolve_disk_path(mention: str, valid: set[str]) -> str | None:
        cand = _rel(skill.path / mention)
        if cand in valid:
            return cand
        base = mention.rsplit("/", 1)[-1]
        for v in valid:
            if v.rsplit("/", 1)[-1] == base:
                return v
        return None

    # output-name -> step names that produce it (for data-flow edges)
    producers: dict[str, list[str]] = {}
    for st in steps:
        for o in _ios(st.get("outputs")):
            producers.setdefault(o["name"], []).append(st.get("name", ""))

    consumed: set[str] = set()

    for order, st in enumerate(steps):
        name = st.get("name", f"step-{order}")
        step_id = f"{sid}::{name}"
        prose = " ".join(str(x) for x in [st.get("description", ""), *(st.get("one_of") or [])])

        rows.steps.append(
            {
                "step_id": step_id,
                "props": {
                    "name": name,
                    "description": st.get("description", ""),
                    "parallel": bool(st.get("parallel", False)),
                    "one_of": [str(x) for x in (st.get("one_of") or [])],
                    "script": st.get("script"),
                    "order": order,
                    "skill_id": sid,
                },
            }
        )
        rows.has_step.append({"skill_id": sid, "step_id": step_id, "order": order})

        for dep in st.get("depends_on") or []:
            rows.depends.append({"from": step_id, "to": f"{sid}::{dep}"})

        for inp in _ios(st.get("inputs")):
            iname = inp["name"]
            prods = [p for p in producers.get(iname, []) if p != name]
            if prods:
                consumed.add(iname)
                for p in prods:
                    rows.flow.append(
                        {
                            "from": f"{sid}::{p}",
                            "to": step_id,
                            "item": iname,
                            "type": inp.get("type"),
                            "description": inp.get("description"),
                            "nullable": inp.get("nullable", False),
                        }
                    )
            else:
                rows.provides.append(
                    {
                        "skill_id": sid,
                        "to": step_id,
                        "item": iname,
                        "type": inp.get("type"),
                        "description": inp.get("description"),
                        "nullable": inp.get("nullable", False),
                    }
                )

        # script edges (explicit `script:` field + mentions in prose)
        for sm in set(filter(None, [st.get("script")])) | set(SCRIPT_RE.findall(prose)):
            rp = resolve_disk_path(sm, valid_scripts)
            if rp:
                rows.runs.append({"from": step_id, "to": rp, "name": rp.rsplit("/", 1)[-1]})

        # reference edges (mentions in description / one_of)
        for rm in set(REF_RE.findall(prose)):
            rp = resolve_disk_path(rm, valid_refs)
            if rp:
                rows.step_refs.append({"from": step_id, "to": rp, "name": rp.rsplit("/", 1)[-1]})

    # terminal outputs: produced but never consumed
    for st in steps:
        sname = st.get("name", "")
        for o in _ios(st.get("outputs")):
            if o["name"] not in consumed:
                rows.yields.append(
                    {
                        "skill_id": sid,
                        "from": f"{sid}::{sname}",
                        "item": o["name"],
                        "type": o.get("type"),
                        "description": o.get("description"),
                        "nullable": o.get("nullable", False),
                    }
                )

    # skill-level attribute nodes
    def attr(lst, kind, text):
        lst.append({"skill_id": sid, "uid": f"{sid}::{kind}::{len(lst)}", "text": text})

    for t in proc.get("trigger_when") or []:
        attr(rows.triggers, "trigger", str(t))
    for d in proc.get("do_not_use_when") or []:
        attr(rows.dnu, "dnu", str(d))
    for a in proc.get("anti_patterns") or []:
        attr(rows.anti, "anti", str(a))

    for s in proc.get("scenarios") or []:
        if isinstance(s, dict):
            rows.scenarios.append(
                {
                    "skill_id": sid,
                    "uid": f"{sid}::scenario::{len(rows.scenarios)}",
                    "props": {
                        "need": str(s.get("need", "")),
                        "context": s.get("context"),
                        "action": str(s.get("action", "")),
                        "outcome": s.get("outcome"),
                    },
                }
            )
    for ig in proc.get("integrations") or []:
        if isinstance(ig, dict):
            rows.integrations.append(
                {
                    "skill_id": sid,
                    "uid": f"{sid}::integration::{len(rows.integrations)}",
                    "props": {"partner": str(ig.get("partner", "")), "body": str(ig.get("body", ""))},
                }
            )
    for m in proc.get("modes") or []:
        if isinstance(m, dict):
            rows.modes.append(
                {
                    "skill_id": sid,
                    "uid": f"{sid}::mode::{len(rows.modes)}",
                    "props": {"name": str(m.get("name", "")), "body": str(m.get("body", ""))},
                }
            )
    for sc in proc.get("search_shortcuts") or []:
        if isinstance(sc, dict):
            rows.shortcuts.append(
                {
                    "skill_id": sid,
                    "uid": f"{sid}::shortcut::{len(rows.shortcuts)}",
                    "props": {"category": str(sc.get("category", "")), "body": str(sc.get("body", ""))},
                }
            )


# --------------------------------------------------------------------------- #
# Neo4j schema + batched UNWIND writes
# --------------------------------------------------------------------------- #
CONSTRAINTS = [
    "CREATE CONSTRAINT skill_id IF NOT EXISTS FOR (n:Skill) REQUIRE n.skill_id IS UNIQUE",
    "CREATE CONSTRAINT step_id IF NOT EXISTS FOR (n:Step) REQUIRE n.step_id IS UNIQUE",
    "CREATE CONSTRAINT script_path IF NOT EXISTS FOR (n:Script) REQUIRE n.path IS UNIQUE",
    "CREATE CONSTRAINT reference_path IF NOT EXISTS FOR (n:Reference) REQUIRE n.path IS UNIQUE",
    "CREATE CONSTRAINT trigger_id IF NOT EXISTS FOR (n:Trigger) REQUIRE n.uid IS UNIQUE",
    "CREATE CONSTRAINT donotuse_id IF NOT EXISTS FOR (n:DoNotUse) REQUIRE n.uid IS UNIQUE",
    "CREATE CONSTRAINT antipattern_id IF NOT EXISTS FOR (n:AntiPattern) REQUIRE n.uid IS UNIQUE",
    "CREATE CONSTRAINT scenario_id IF NOT EXISTS FOR (n:Scenario) REQUIRE n.uid IS UNIQUE",
    "CREATE CONSTRAINT integration_id IF NOT EXISTS FOR (n:Integration) REQUIRE n.uid IS UNIQUE",
    "CREATE CONSTRAINT mode_id IF NOT EXISTS FOR (n:Mode) REQUIRE n.uid IS UNIQUE",
    "CREATE CONSTRAINT shortcut_id IF NOT EXISTS FOR (n:SearchShortcut) REQUIRE n.uid IS UNIQUE",
]

Q_SKILLS = """
UNWIND $rows AS row
MERGE (sk:Skill {skill_id: row.skill_id})
SET sk += row.props
"""

Q_STEPS = """
UNWIND $rows AS row
MERGE (st:Step {step_id: row.step_id})
SET st += row.props
"""

Q_HAS_STEP = """
UNWIND $rows AS row
MATCH (sk:Skill {skill_id: row.skill_id}), (st:Step {step_id: row.step_id})
MERGE (sk)-[r:HAS_STEP]->(st)
SET r.order = row.order
"""

Q_REFERENCES = """
UNWIND $rows AS row
MERGE (r:Reference {path: row.path})
SET r.name = row.name
WITH r, row
MATCH (sk:Skill {skill_id: row.skill_id})
MERGE (sk)-[:HAS_REFERENCE]->(r)
"""

Q_SCRIPTS = """
UNWIND $rows AS row
MERGE (sc:Script {path: row.path})
SET sc.name = row.name
WITH sc, row
MATCH (sk:Skill {skill_id: row.skill_id})
MERGE (sk)-[:HAS_SCRIPT]->(sc)
"""

Q_FLOW = """
UNWIND $rows AS row
MATCH (a:Step {step_id: row.from}), (b:Step {step_id: row.to})
MERGE (a)-[f:INPUT_TO {item: row.item}]->(b)
SET f.type = row.type, f.description = row.description, f.nullable = row.nullable
"""

Q_PROVIDES = """
UNWIND $rows AS row
MATCH (sk:Skill {skill_id: row.skill_id}), (b:Step {step_id: row.to})
MERGE (sk)-[f:PROVIDES {item: row.item, step_id: row.to}]->(b)
SET f.type = row.type, f.description = row.description, f.nullable = row.nullable
"""

Q_YIELDS = """
UNWIND $rows AS row
MATCH (a:Step {step_id: row.from}), (sk:Skill {skill_id: row.skill_id})
MERGE (a)-[f:YIELDS {item: row.item}]->(sk)
SET f.type = row.type, f.description = row.description, f.nullable = row.nullable
"""

Q_DEPENDS = """
UNWIND $rows AS row
MATCH (a:Step {step_id: row.from}), (b:Step {step_id: row.to})
MERGE (a)-[:DEPENDS_ON]->(b)
"""

Q_RUNS = """
UNWIND $rows AS row
MATCH (a:Step {step_id: row.from})
MERGE (sc:Script {path: row.to})
SET sc.name = row.name
MERGE (a)-[:RUNS]->(sc)
"""

Q_STEP_REFS = """
UNWIND $rows AS row
MATCH (a:Step {step_id: row.from})
MERGE (r:Reference {path: row.to})
SET r.name = row.name
MERGE (a)-[:REFERENCES]->(r)
"""

# Skill -[REL]-> (Label {uid, text}) — list-of-string attribute nodes.
def _q_text_attr(label: str, rel: str) -> str:
    return f"""
UNWIND $rows AS row
MATCH (sk:Skill {{skill_id: row.skill_id}})
MERGE (n:{label} {{uid: row.uid}})
SET n.text = row.text
MERGE (sk)-[:{rel}]->(n)
"""


# Skill -[REL]-> (Label {uid, ...props}) — structured attribute nodes.
def _q_props_attr(label: str, rel: str) -> str:
    return f"""
UNWIND $rows AS row
MATCH (sk:Skill {{skill_id: row.skill_id}})
MERGE (n:{label} {{uid: row.uid}})
SET n += row.props
MERGE (sk)-[:{rel}]->(n)
"""


# Resolve integration partners to real Skill nodes by name, scoped to the same
# task pack (skill names repeat across tasks). Run after all skills are loaded.
PARTNER_QUERY = """
MATCH (sk:Skill)-[:INTEGRATES_WITH]->(ig:Integration)
MATCH (partner:Skill {name: ig.partner})
WHERE partner <> sk AND partner.task = sk.task
MERGE (sk)-[r:PARTNERS_WITH]->(partner)
SET r.via = ig.partner
"""


def nuke(session) -> None:
    """Reset the entire database — `ki nuke` style.

    1. Batched server-side `DETACH DELETE` of every node (CALL ... IN
       TRANSACTIONS so a large graph doesn't OOM the server in one tx).
    2. Drop every constraint and every non-LOOKUP index, regardless of which
       schema created them, so nothing lingers. All `IF EXISTS`-guarded and
       idempotent — safe to run against an already-empty database.

    The chunk-size literal is substituted client-side because `IN TRANSACTIONS
    OF n ROWS` rejects a Cypher parameter for `n`.
    """
    session.run(
        "MATCH (n) CALL (n) { DETACH DELETE n } IN TRANSACTIONS OF 10000 ROWS"
    ).consume()
    for name in [r["name"] for r in session.run("SHOW CONSTRAINTS YIELD name")]:
        session.run(f"DROP CONSTRAINT `{name}` IF EXISTS").consume()
    for r in session.run("SHOW INDEXES YIELD name, type"):
        if r["type"] == "LOOKUP":  # built-in token-lookup indexes can't be dropped
            continue
        session.run(f"DROP INDEX `{r['name']}` IF EXISTS").consume()


def run_batched(session, query: str, rows: list[dict], batch_size: int = DEFAULT_BATCH_SIZE) -> int:
    """Ship rows to an `UNWIND $rows` query in chunks, one tx per chunk."""
    if not rows:
        return 0
    for i in range(0, len(rows), batch_size):
        session.run(query, rows=rows[i : i + batch_size]).consume()
    return len(rows)


def write_all(session, rows: Rows, batch_size: int) -> None:
    # Nodes first (so edge MATCHes resolve), then edges, then attribute nodes.
    plan = [
        ("Skill", Q_SKILLS, rows.skills),
        ("Step", Q_STEPS, rows.steps),
        ("HAS_STEP", Q_HAS_STEP, rows.has_step),
        ("Reference", Q_REFERENCES, rows.references),
        ("Script", Q_SCRIPTS, rows.scripts),
        ("INPUT_TO", Q_FLOW, rows.flow),
        ("PROVIDES", Q_PROVIDES, rows.provides),
        ("YIELDS", Q_YIELDS, rows.yields),
        ("DEPENDS_ON", Q_DEPENDS, rows.depends),
        ("RUNS", Q_RUNS, rows.runs),
        ("REFERENCES", Q_STEP_REFS, rows.step_refs),
        ("Trigger", _q_text_attr("Trigger", "TRIGGERS_ON"), rows.triggers),
        ("DoNotUse", _q_text_attr("DoNotUse", "AVOID_WHEN"), rows.dnu),
        ("AntiPattern", _q_text_attr("AntiPattern", "WARNS"), rows.anti),
        ("Scenario", _q_props_attr("Scenario", "HAS_SCENARIO"), rows.scenarios),
        ("Integration", _q_props_attr("Integration", "INTEGRATES_WITH"), rows.integrations),
        ("Mode", _q_props_attr("Mode", "HAS_MODE"), rows.modes),
        ("SearchShortcut", _q_props_attr("SearchShortcut", "HAS_SHORTCUT"), rows.shortcuts),
    ]
    for label, query, data in plan:
        n = run_batched(session, query, data, batch_size)
        if n:
            print(f"  wrote {n:5d} {label}")


# --------------------------------------------------------------------------- #
# Credentials
# --------------------------------------------------------------------------- #
def load_creds(creds_file: Path) -> dict:
    creds = {}
    if creds_file.exists():
        for line in creds_file.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            creds[k.strip()] = v.strip()
    for k in ("NEO4J_URI", "NEO4J_USERNAME", "NEO4J_PASSWORD", "NEO4J_DATABASE"):
        if os.environ.get(k):
            creds[k] = os.environ[k]
    return creds


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("path", type=Path, help="Skill dir, task dir, or corpus root to ingest (recursive).")
    ap.add_argument("--clear", action="store_true", help="Wipe the database before loading.")
    ap.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    ap.add_argument("--creds-file", type=Path, default=DEFAULT_CREDS_FILE)
    ap.add_argument("--uri")
    ap.add_argument("--user")
    ap.add_argument("--password")
    ap.add_argument("--database")
    ap.add_argument("--dry-run", action="store_true", help="Parse and report; do not write to Neo4j.")
    args = ap.parse_args()

    root = args.path.resolve()
    if not root.exists():
        print(f"path not found: {root}", file=sys.stderr)
        return 2

    skill_mds = sorted(root.rglob("SKILL.md")) if root.is_dir() else [root]
    # Skip vendored `source/SKILL.md` originals nested under an AIP skill dir.
    skill_mds = [p for p in skill_mds if p.parent.name != "source"]
    if not skill_mds:
        print(f"no SKILL.md found under {root}", file=sys.stderr)
        return 2

    parsed = [s for p in skill_mds if (s := parse_skill(p))]
    rows = Rows()
    for s in parsed:
        accumulate(s, rows)

    print(f"Parsed {len(parsed)} skill(s) from {root}")
    print(
        f"  {len(rows.steps)} steps | flow {len(rows.flow)} | ext-in {len(rows.provides)} | "
        f"term-out {len(rows.yields)} | depends {len(rows.depends)} | runs {len(rows.runs)} | "
        f"step-refs {len(rows.step_refs)} | refs {len(rows.references)} | scripts {len(rows.scripts)}"
    )

    if args.dry_run:
        return 0

    creds = load_creds(args.creds_file)
    uri = args.uri or creds.get("NEO4J_URI")
    user = args.user or creds.get("NEO4J_USERNAME")
    password = args.password or creds.get("NEO4J_PASSWORD")
    database = args.database or creds.get("NEO4J_DATABASE") or "neo4j"
    if not (uri and user and password):
        print("missing NEO4J_URI / NEO4J_USERNAME / NEO4J_PASSWORD", file=sys.stderr)
        return 2

    driver = GraphDatabase.driver(uri, auth=(user, password))
    try:
        driver.verify_connectivity()
        with driver.session(database=database) as session:
            if args.clear:
                print("Clearing database (nuke: all nodes + constraints + indexes)...")
                nuke(session)
            for q in CONSTRAINTS:
                session.run(q).consume()
            print("Writing graph...")
            write_all(session, rows, args.batch_size)
            res = session.run(PARTNER_QUERY).consume()
            print(f"  linked {res.counters.relationships_created} cross-skill PARTNERS_WITH edges")

            counts = session.run(
                "MATCH (n) UNWIND labels(n) AS l RETURN l AS label, count(*) AS n ORDER BY n DESC"
            ).data()
        print("\nNode counts:")
        for c in counts:
            print(f"  {c['label']:16} {c['n']}")
    finally:
        driver.close()

    print(f"\nDone. Open Neo4j Browser/Bloom on {uri} to explore.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""The authoring prompt for `aip-skillbench convert`: one shared body plus a note per
variant kind (aip_skillbench._variants). The body states the compile conditions that are
identical across variants (docs/aip-version-ablation-benchmark.md, "Compilation"); the
note says how to use that variant's authoring skill without a human in the loop.

Every prompt names only workspace-relative paths (./inputs, ./out, ./scratch); the
workspace layout is in _authoring.py.
"""

from __future__ import annotations

from aip_skillbench._variants import Variant

_BODY = """\
Use the `{skill_name}` skill in ./.claude/skills/{skill_name}/ to compile the curated
Agent Skills under:

    ./inputs/skills/

({curated}) into ONE skill at:

    ./out/<skill-name>/

What you have, all under ./inputs/:

- ./inputs/skills/: the curated skills. They describe one workflow; compile them into a
  single skill.
- ./inputs/instruction.md: the task statement a downstream agent will receive with the
  compiled skill mounted. Read it first: it says what the skill must achieve and where
  the inputs and outputs live in the task's container (those are container paths, not
  paths on this machine).
- ./inputs/environment/: the task's input files, with MANIFEST.md listing their real
  names and sizes, and the Dockerfile of the container the skill will run in.
  {data_note}

{note}

Requirements:

1. Read every SKILL.md and every other file under ./inputs/skills/ (scripts/,
   references/, assets/, etc.). Copy all the originals verbatim into
   ./out/<skill-name>/source/ and write ./out/<skill-name>/source/README.md with the
   provenance, the component-kind choices, and the deliberate-drop log. Mirror, copy, or
   adapt supporting files into scripts/, references/, or assets/ as the skill needs.
2. Pick a concise <skill-name>; the directory name under ./out/ must equal the skill's
   `name:` frontmatter.
3. The skill must carry all the specialized knowledge and procedures an agent needs to
   solve this task type autonomously. Do not derive or hardcode an expected answer; the
   skill must compute its result from whatever files it is given.
4. Scripts run inside the task's container, so they must work with the packages that
   container provides (see ./inputs/environment/Dockerfile) or bootstrap their own
   environment; do not assume extra packages.
5. Nobody is watching this session: do not ask questions or wait for confirmation; name
   the skill yourself; skip any install step and write straight to ./out/<skill-name>/.
   Do not spawn other agents or `claude -p` sessions: only this session's own tool calls
   are audited, so the functional test is done by you, here.
6. Everything you may read is under ./inputs/ and everything you write goes under ./out/
   or ./scratch/; do not look anywhere else on this machine. Test inputs never go inside
   the skill folder.

Write nothing outside ./out/ and ./scratch/."""

_DATA_NOTES = {
    "full": (
        "These are the real files, complete: functional-test the skill against them "
        "(copy what you need into ./scratch/). Every loader, default, and assumption in "
        "the skill must hold for these files exactly as they are, and the skill must still "
        "work on another instance of the same task with different contents."
    ),
    "sample": (
        "These copies are TRUNCATED to their first 2 KB: enough to see the real format "
        "(header lines, delimiters, column order, cadence, units, encoding), not the "
        "content. Every loader, default, and assumption in the skill must hold for those "
        "files exactly as they are; build the functional test's inputs in the same format "
        "(synthesize a full-length file in ./scratch/ that mimics them)."
    ),
    "none": (
        "Only the Dockerfile is staged; the instruction says what the input files are. "
        "Build the functional test's inputs in ./scratch/ from that description."
    ),
}

_NOTES = {
    # aip-spec 0.6a1 authoring skill plus the aip 0.6a1 client on PATH.
    "aip": """\
Follow the aip skill's "Authoring an Agent Skill" checklist end to end: source/
materials, SKILL.md with the verbatim runtime block and one fenced YAML procedure,
`aip-spec validate ./out/<skill-name>` after every edit (the `aip-spec` and `aip` CLIs
are on PATH), the line-by-line completeness check against the sources, and the
functional test: write realistic start inputs to ./scratch/start.json and run
`aip run ./out/<skill-name> --input ./scratch/start.json`, answering each pause with
`aip resume <run-id> --input <answer.json>` (every pause prints its `run_id`), through
to the end step, reaching every router branch at least once.

The 0.6a1 contract the validator enforces: the pack's `requires` block names the
interpreter with a minimum version the container's `python3` meets, every package the
scripts import, and any other tool they call (the client checks it before the first
script and stops naming what is missing); every execution and client_task step declares
its `outputs`; every key has one producer, and a consumed key's type must agree with its
producer's. How `aip run` executes a script: it runs `<python> <script>` (or the step's
`command`) with cwd set to the script's folder and one JSON object on stdin
({"state": <the step's declared inputs only>, "assets", "expects"}); stdout must be one
JSON object holding exactly the step's declared `outputs`. In the container that python
has the container's system packages; in a local `aip run` here it is the aip CLI's own
Python 3.14, which lacks the task's packages, so the `requires` check fails until they
are visible. If the functional test needs them: `uv venv --python 3.14 ./scratch/venv &&
uv pip install --python ./scratch/venv/bin/python <packages>`, then prefix the run with
`PYTHONPATH="$(./scratch/venv/bin/python -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')" aip run ...`
(the `requires` check and the scripts inherit it; do the same for `aip resume`). That is
all you need to know about the aip installation; do not read its source.""",

    # The aip repo at v0.3a3: the skill itself, with its own validator script.
    "aip-legacy": """\
Follow the aip skill's "Authoring an Agent Skill" checklist end to end: reuse the
procedure schema under ./.claude/skills/aip/assets/aip-schemas/ (bundle a copy in
./out/<skill-name>/source/ as the checklist says), source/ materials, SKILL.md with the
`metadata.aip.spec` and `metadata.aip.schemaId` frontmatter and exactly one fenced YAML
body, `uv run ./.claude/skills/aip/scripts/validate.py ./out/<skill-name>` after every
edit (exit 0 means valid; errors are JSON lines on stderr), the line-by-line
completeness check against the sources, and the functional test. Do the functional
test yourself in this session, as the downstream agent would: execute the procedure
step by step on realistic inputs under ./scratch/, run every script with the exact
command the body gives, reach every branch at least once, and check each script's
result against the real inputs, not just that it exits 0. The skill's `compatibility`
frontmatter names the interpreter and packages the scripts need.""",

    # The distillation meta-skill: a plain Agent Skill of components and scripts.
    "dist": """\
Follow the skill-distillation skill's "Distillation Procedure" end to end: source/
materials, SKILL.md with the Trigger When and Purpose sections and each component as a
script, a decision, or a client task per "Choose Component Kinds", the review checklist
after every edit, the line-by-line completeness check against the sources, and the
functional test. Do the functional test yourself in this session, as the downstream
agent would: walk the skill on realistic inputs under ./scratch/, run every script with
the launch command the body gives, answer every decision and perform every client task,
reach every branch at least once, and check each script's result against the real
inputs, not just that it exits 0. The output is a plain Agent Skill: the harness checks
the frontmatter, that `name` equals the folder, that `source/` exists, and that every
relative path the body mentions exists in the skill folder.""",
}


def prompt_for(v: Variant, curated_names: list[str], stage_data: str) -> str:
    try:
        note = _NOTES[v.kind]
    except KeyError:
        raise ValueError(f"no authoring note for variant kind {v.kind!r}") from None
    return _BODY.format(
        skill_name=v.skill_name,
        curated=", ".join(curated_names),
        data_note=_DATA_NOTES[stage_data],
        note=note,
    )

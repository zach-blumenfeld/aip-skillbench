Use the `aip` skill in ./.claude/skills/aip/ to compile the curated Agent
Skills under:

    ./inputs/skills/

(pdf, xlsx) into ONE AIP skill at:

    ./out/<skill-name>/

Follow the aip skill's "Authoring an Agent Skill" checklist end to end: source/
materials, SKILL.md with the verbatim runtime block and one fenced YAML procedure,
`aip-spec validate ./out/<skill-name>` after every edit (the `aip-spec` and `aip`
CLIs are on PATH), the line-by-line completeness check against the sources, and the
functional test: write realistic start inputs to ./scratch/start.json (test inputs
never go inside the pack) and run `aip run ./out/<skill-name> --input
./scratch/start.json`, answering each pause with `aip resume <run-file> --input
<answer.json>`, through to the end step. Nobody is watching this session: do not ask
questions, and skip the checklist's install step (write straight to the destination
below). Everything you may read is under ./inputs/ and everything you write goes
under ./out/ or ./scratch/; do not look anywhere else on this machine. Scripts run
inside the task's container, so they must work with the packages that container
provides (see ./inputs/environment/Dockerfile when present) or bootstrap their own
environment; do not assume extra packages.

Requirements:
1. Read every SKILL.md and every other file under ./inputs/skills/ (scripts/,
   references/, assets/, etc.). The curated skills describe one workflow; compile
   them into a single procedure graph. Copy all the originals verbatim into
   ./out/<skill-name>/source/ and write ./out/<skill-name>/source/README.md with
   the provenance, the step-kind choices, and the deliberate-drop log. Mirror, copy,
   or adapt supporting files into scripts/, references/, or assets/ as the
   procedure needs.
2. Pick a concise `<skill-name>`; the directory name under ./out/ must equal the
   skill's `name:` frontmatter.
3. The skill must carry all the specialized knowledge and procedures an agent needs
   to solve this task type autonomously.

Write nothing outside ./out/ and ./scratch/.
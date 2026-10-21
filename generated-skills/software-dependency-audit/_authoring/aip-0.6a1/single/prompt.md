Use the `aip` skill in ./.claude/skills/aip/ to compile the curated
Agent Skills under:

    ./inputs/skills/

(cvss-score-extraction, trivy-offline-vulnerability-scanning, vulnerability-csv-reporting) into ONE skill at:

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
  These are the real files, complete: functional-test the skill against them (copy what you need into ./scratch/). Every loader, default, and assumption in the skill must hold for these files exactly as they are, and the skill must still work on another instance of the same task with different contents.

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
all you need to know about the aip installation; do not read its source.

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

Write nothing outside ./out/ and ./scratch/.
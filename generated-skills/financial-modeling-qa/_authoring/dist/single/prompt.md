Use the `skill-distillation` skill in ./.claude/skills/skill-distillation/ to compile the curated
Agent Skills under:

    ./inputs/skills/

(pdf, xlsx) into ONE skill at:

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
relative path the body mentions exists in the skill folder.

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
# maven-build-lifecycle — AIP authoring notes

## Source
Converted from a curated Agent Skill bundled with the SkillsBench task
`fix-build-google-auto`. The original is preserved verbatim at
`./original-SKILL.md`.

## Schema choice
- **Schema:** `procedure.schema.json` (AIP v0.3a3).
- **Why:** Although the original SKILL.md is structured as a reference
  document (lifecycle phases, XML snippets, command tables), the agent's
  actual use of it is procedural — classify the Maven need, locate the
  right reference, identify the failing phase, pick a debug strategy,
  propose a fix, verify. The procedure schema captures that workflow as
  steps with inputs/outputs, and parks the long-form reference content
  under `references/` for on-demand loading.
- Bias to reuse: this is a stock AIP schema, not a new one. No new
  schema was authored.

## Body vs references split
The body keeps only what the agent needs every invocation:
- Workflow steps for diagnosing/working with Maven builds.
- A compact `search_shortcuts` table of the most-used phases, flags,
  reactor options, and debug commands.
- Anti-patterns lifted from the original "Common Pitfalls" + best
  practices.
- Three worked scenarios spanning the most common task shapes
  (multi-module reactor scope, Surefire/Failsafe split, profile setup).

Detail lives under `references/` and is loaded only when a step says to:
- `references/lifecycle-phases-and-goals.md` — full phase list for the
  default / clean / site lifecycles, goals vs phases, phase-to-goal
  bindings.
- `references/profiles.md` — profile definition, activation triggers
  (JDK, OS, property, file).
- `references/build-customization.md` — source/target, custom source
  dirs, final name, resource filtering, property substitution.
- `references/test-configuration.md` — Surefire and Failsafe.
- `references/multi-module-builds.md` — reactor options, module order.
- `references/debugging-and-optimization.md` — debug flags, effective
  POM, dependency analysis, parallel builds, incremental, build cache.
- `references/ci-cd-integration.md` — GitHub Actions and Jenkins
  examples.

## Why no `scripts/`
Maven build diagnosis is interpretive: read the build output, judge
which phase actually failed and why, decide whether the problem is in
source, pom configuration, profile activation, or invocation flags.
Hard-coding any of that as a lookup or if/else would be brittle —
plugin output formats vary, custom plugins reuse standard phase names,
and the same symptom (e.g. "missing symbol") can resolve through a
reactor flag, a dependency add, or a source edit. Each step is left as
prose so the agent reasons.

The agent does not need any deterministic calculation, lookup table, or
fixed-rules validation that would call for code. A future revision
could script a small parser for `BUILD FAILURE` blocks if the task
became repetitive, but that's out of scope for this conversion.

## Content classification (every distinct piece of source mapped)
- **Mapped → body:** purpose statement, when-to-use list, common
  command set (search_shortcuts), common pitfalls (anti_patterns), best
  practices (folded into anti_patterns / step descriptions where
  relevant), `mvn dependency:tree` / `mvn help:effective-pom` debug
  flow (pick-debug-strategy step).
- **Mapped → references/lifecycle-phases-and-goals.md:** complete phase
  list for default/clean/site lifecycles, goals vs phases, phase-to-goal
  bindings XML.
- **Mapped → references/profiles.md:** profile definition XML,
  activation flags, activation trigger types (JDK, OS, property, file).
- **Mapped → references/build-customization.md:** source/target props,
  custom source dirs, final name / output dirs, resource filtering XML
  and property substitution.
- **Mapped → references/test-configuration.md:** Surefire and Failsafe
  plugin XML.
- **Mapped → references/multi-module-builds.md:** reactor options,
  `<modules>` ordering.
- **Mapped → references/debugging-and-optimization.md:** -X / -e / -q
  flags, effective-pom / effective-settings / active-profiles,
  versions:display-* checks, parallel builds, incremental, mvnd, build
  cache flag.
- **Mapped → references/ci-cd-integration.md:** GitHub Actions and
  Jenkins pipeline snippets.
- **Deliberate drops:** none — every distinct section of the original
  is either in the body or in a reference file.

# Conversion notes: maven-plugin-configuration → AIP

## Source
- `source/original-SKILL.md` — the curated Anthropic Agent Skill being converted.

## Schema choice
- Bundled `source/procedure.schema.json` (AIP `procedure` schema).
- The original is reference-heavy, but the task this skill supports is
  procedural: an agent diagnoses a build/configuration need, locates the
  relevant plugin, edits `pom.xml`, and validates. `procedure` cleanly models
  that as a step graph with reference material loaded on demand. No
  category-specific schema exists for "Maven plugin reference," and inventing
  one would be premature.

## Body shape
- The original `SKILL.md` mixed (a) a procedural intuition about how to
  configure plugins and (b) a thick catalog of XML examples for ~20 plugins.
- The AIP body keeps the procedure lean and pushes every plugin example into
  `references/*.md`, loaded on demand. Progressive disclosure keeps invocation
  cost low; plugin examples only pay for tokens when the agent opens them.
- `search_shortcuts` indexes the plugins by category and points to the right
  reference file, so the agent can pick a reference without scanning all of
  them.
- `anti_patterns` carries the original "Common Pitfalls" plus the strongest
  items from "Best Practices" rephrased as concrete corrections.

## Script decisions
- **No scripts.** The original ships none. The procedure's decisions
  (which plugin is implicated, what configuration to apply, whether the
  build is fixed) are interpretation-heavy — agent reasoning, not
  mechanical rules. Adding a script would over-constrain a flexible
  configuration task. Validation already exists as a CLI (`mvn`).

## Reference file layout
- `references/plugin-basics.md` — plugin structure, `<pluginManagement>`.
- `references/build-and-test-plugins.md` — compiler, resources, jar, source,
  javadoc, surefire, failsafe, jacoco.
- `references/quality-and-packaging-plugins.md` — enforcer, checkstyle,
  spotbugs, pmd, assembly, shade, war.
- `references/ecosystem-plugins.md` — spring-boot, versions, release,
  build-helper, exec.
- `references/best-practices.md` — original "Best Practices" section
  verbatim (the anti-patterns side already lives in the body).

## Items deliberately dropped from body
- None. Every original section is either present in the body, present in
  `references/`, or rephrased as `anti_patterns`. The "When to Use This
  Skill" closing section is folded into `trigger_when`.

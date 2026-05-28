# Source notes — `maven-plugin-configuration` (AIP form)

## Origin

Compiled from the curated `maven-plugin-configuration/SKILL.md` shipped with
the SkillsBench `fix-build-google-auto` task (lineage:
`TheBushidoCollective/han/jutsu/jutsu-maven/skills`). The original was a
freeform Markdown cookbook of Maven plugin XML examples plus prose "best
practices" and "common pitfalls" sections.

## Schema choice

`procedure.schema.json` from `aip v0.3a2`. The source content lacked any
explicit procedure, but the downstream task (`fix-build-google-auto`)
consumes the skill while triaging and patching a broken Maven build — the
agent's work is procedural even when the source isn't. AIP procedures cleanly
model that: `steps` carry the diagnose → look up → patch → verify flow,
`scripts/` back the deterministic pieces (log parsing, POM block
extraction), and the XML cookbook moves into `references/` for progressive
disclosure.

No new schema was drafted; reuse of the standard procedure schema is
sufficient.

## Compilation map (source → AIP)

| Source section                               | AIP location                                       |
|----------------------------------------------|----------------------------------------------------|
| Overview / Plugin Basics / Plugin Management | `references/plugin-basics.md` + body step `consult-plugin-reference` |
| Core Build Plugins (Compiler/Resources/JAR/Source/Javadoc) | `references/core-build-plugins.md` |
| Testing Plugins (Surefire/Failsafe/JaCoCo)   | `references/testing-plugins.md`                    |
| Quality Plugins (Enforcer/Checkstyle/SpotBugs/PMD) | `references/quality-plugins.md`              |
| Packaging Plugins (Assembly/Shade/WAR/Spring Boot) | `references/packaging-plugins.md`            |
| Version Management & Code Generation         | `references/version-and-codegen-plugins.md`        |
| Best Practices                               | `references/plugin-basics.md` § Best Practices     |
| Common Pitfalls                              | `references/plugin-basics.md` § Common Pitfalls + body `anti_patterns` |
| When to Use This Skill                       | body `trigger_when`                                |

Pieces added beyond the source to make this procedure agent-actionable for
the `fix-build-google-auto` task family:

- `references/diagnosis-playbook.md` — error-message → plugin/fix map,
  plus repo-specific notes for `google/auto`. Synthesized from common
  Maven failure modes plus the BugSwarm task context.
- `scripts/diagnose_plugin.sh` — parses Maven logs into a structured
  `{ plugin, goal, hints, error_lines }` JSON record.
- `scripts/extract_plugin_block.py` — finds a `<plugin>` block in a POM
  preserving offsets so the agent can build a precise patch.

## Source items deliberately not surfaced

- "Master Maven plugin configuration including core plugins, build
  plugins, reporting plugins, and custom plugin development." — opening
  marketing line; absorbed into the body `purpose`.
- The standalone `mvn versions:*` bash recipe is preserved verbatim
  inside `references/version-and-codegen-plugins.md` rather than promoted
  into a step (it is reference, not procedure).

Nothing else from the source was dropped.

## Why scripts only cover diagnosis + block extraction

The bulk of source content is *declarative reference XML* — a script
cannot produce "the right plugin configuration" without an unbounded
domain model. Per AIP best practices, those steps stay as prose nodes
that point the agent at the correct reference file. The genuinely
scriptable pieces — log parsing and POM surgery — are backed by scripts.

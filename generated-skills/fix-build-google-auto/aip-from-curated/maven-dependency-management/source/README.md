# Source materials for `maven-dependency-management` (AIP port)

## Origin

Compiled from the curated Agent Skill at:

    vendor/skillsbench/tasks/fix-build-google-auto/environment/skills/maven-dependency-management/SKILL.md

The original `SKILL.md` is preserved verbatim as `ORIGINAL_SKILL.md` in this folder.

## Schema choice

`procedure.schema.json` (bundled here) — the AIP procedure schema. Picked because
the underlying skill is a step-graph an agent walks through when triaging a Maven
build:

  inspect → diagnose conflict → choose resolution strategy → apply patch → verify

The original document reads as a reference manual, but the *task type* it
supports (fix a broken Maven build, resolve dependency conflicts, optimize a
tree) is procedural. The procedure schema expresses that graph; the XML
templates, scope tables, and command cheatsheets move into `references/` for
progressive disclosure.

## Mapping rationale

| Source section                  | Destination                              |
|---------------------------------|------------------------------------------|
| Overview                        | `purpose`                                |
| When to Use This Skill          | `trigger_when`                           |
| Dependency Declaration          | `references/xml-patterns.md`             |
| Dependency Scopes (incl. table) | `references/scopes.md` + scoring script  |
| Version Management              | `references/xml-patterns.md`             |
| Dependency Management / BOM     | `references/boms.md`                     |
| Exclusions                      | `references/xml-patterns.md`             |
| Dependency Analysis (commands)  | `scripts/run_mvn_diagnostic.sh`          |
| Conflict Resolution             | step `diagnose-conflict` + decision script |
| Multi-Module Projects           | `references/multi-module.md`             |
| Repository Configuration        | `references/repositories.md`             |
| Best Practices                  | folded into step descriptions + `anti_patterns` |
| Common Pitfalls                 | `anti_patterns`                          |
| Troubleshooting                 | `scripts/run_mvn_diagnostic.sh` flags    |

## Deliberate drops

- The `LATEST` / `RELEASE` version-range examples are kept in
  `references/xml-patterns.md` only as anti-examples — the AIP body lists them
  under `anti_patterns` rather than as something to copy.
- The `system` scope is documented in `references/scopes.md` but not given a
  worked example in the body. Maven 3.x+ deprecates it and the original skill
  flags it as a pitfall.
- The "Repository in Settings.xml" snippet is kept in `references/repositories.md`
  but no step references it — credentials live outside the project pom and the
  procedure is not the right surface for them.
- "Use `versions-maven-plugin` for updates" from the original Best Practices
  list is not retained — it is an upgrade-cadence tip, not a build-repair
  procedure, and is out of scope for the host task.
- "Document Exclusions — Comment why exclusions are needed" is folded into the
  XML comments emitted by `scripts/generate_patch_snippet.py` rather than as
  a standalone instruction in the body.

## Completeness audit (source → destination)

Every distinct section of `ORIGINAL_SKILL.md` is accounted for. Each entry is
either **Mapped** (captured faithfully somewhere in the AIP skill) or
**Deliberate drop** (above). No `Schema gap` items — the procedure schema's
`purpose` / `trigger_when` / `steps` / `modes` / `search_shortcuts` /
`integrations` / `scenarios` / `anti_patterns` slots covered every section
the source provides without contortion.

## Name preservation

The `name:` frontmatter is **`maven-dependency-management`**, unchanged from
the source. The benchmark task mounts the skill by directory name; renaming
would break activation.

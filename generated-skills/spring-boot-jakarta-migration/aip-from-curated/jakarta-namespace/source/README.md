# jakarta-namespace — source notes

## Origin

This AIP skill was compiled from the curated SkillsBench skill at
`vendor/skillsbench/tasks/spring-boot-jakarta-migration/environment/skills/jakarta-namespace/SKILL.md`
(also bundled here as `original-SKILL.md`). The original is a freeform-markdown
runbook for the `javax.* → jakarta.*` namespace migration required when
upgrading to Spring Boot 3.x.

## Schema

`procedure.schema.json` (v0.3a2) — bundled locally so the skill is
self-contained. The skill is a multi-step migration runbook with deterministic
shell commands; the procedure schema fits cleanly with `steps` backed by
scripts and a fallback `modes` entry for the OpenRewrite alternative.

## Compilation decisions

- **Lookup table → reference.** The package-mapping table and the
  affected-annotations lists are static reference data, not branching logic.
  They live in `references/package-mappings.md` and are loaded on demand,
  keeping `SKILL.md` body lean.
- **Bash sequences → scripts.** The discovery/migration/verification command
  blocks are exactly the kind of consistency-critical, repeatable logic that
  belongs in scripts (per AIP best practices). Each script takes an optional
  target directory and works on both GNU and BSD/macOS `sed`.
  - `scripts/find_javax_imports.sh` — discovery
  - `scripts/migrate_imports.sh` — batch rewrite (idempotent)
  - `scripts/verify_migration.sh` — completeness check
- **OpenRewrite path → mode + reference.** The original presents OpenRewrite
  as an alternative automated path. Encoded as a `modes` entry pointing at
  `references/openrewrite.md`.
- **Worked examples → scenarios + reference.** The Entity / Validation /
  Servlet before/after examples live in `references/package-mappings.md` so
  they're available when needed without bloating the body. A short
  `scenarios` list in the body summarizes the common triggering situations.
- **Common pitfalls → anti_patterns.** Direct mapping; each pitfall becomes a
  one-line anti-pattern.
- **Sources URLs → dropped.** The original's `## Sources` section
  (Spring Boot migration guide, Baeldung, OpenRewrite docs) is reference
  material for the human reader of the runbook, not actionable instruction
  for the agent. Documented here as a deliberate drop.

## Deliberate drops

- The "Sources" section (three external URLs at the end of the original
  SKILL.md). Rationale above.
- Repetition of the `javax.sql` / `javax.crypto` exclusion in multiple
  places — consolidated into the package-mappings reference and the
  `scripts/find_javax_imports.sh` filter logic.

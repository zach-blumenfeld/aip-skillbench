# hibernate-upgrade — source notes

## Origin

This AIP skill was compiled from the curated SkillsBench skill at
`vendor/skillsbench/tasks/spring-boot-jakarta-migration/environment/skills/hibernate-upgrade/SKILL.md`
(also bundled here as `original-SKILL.md`). The original is a freeform-markdown
runbook for migrating Hibernate 5 to Hibernate 6 in the context of a Spring
Boot 3 upgrade.

## Schema

`procedure.schema.json` (v0.3a2) — bundled locally so the skill is
self-contained. The skill is a multi-step migration runbook with a mix of
deterministic shell commands (discovery, mechanical rewrite, verification)
and structural-rewrite guidance (Criteria API, custom types). The procedure
schema fits cleanly: scriptable steps are backed by `scripts/`, judgment-
heavy steps stay as prose, and the static lookup material lives in
`references/` so the body stays lean.

## Compilation decisions

- **Lookup tables and worked examples → references.** The before/after
  examples for each breaking change, the legacy-Criteria → JPA-Criteria
  mapping cheatsheet, the type-annotation rewrites, and the configuration
  property table are all static reference data, not branching logic. They
  live in `references/breaking-changes.md`, `references/type-mappings.md`,
  and `references/configuration.md` and load on demand.
- **Bash sequences → scripts.** The discovery, mechanical-fix, and
  verification grep/sed blocks in the original are exactly the kind of
  consistency-critical, repeatable logic that belongs in scripts (per AIP
  best practices). Each script takes an optional target directory and works
  on both GNU and BSD/macOS `sed`.
  - `scripts/find_hibernate5_patterns.sh` — discovery (Criteria API,
    `@Type(type=...)`, `@TypeDef`, `update from`, redundant `distinct`,
    dialect references, legacy ID generators)
  - `scripts/fix_update_from.sh` — mechanical rewrite (`update from <E>` →
    `update <E>`); the only fully-safe bulk transformation in the upgrade
  - `scripts/verify_upgrade.sh` — completeness check on the patterns that
    must be zero after migration
- **Structural rewrites stay as prose steps.** Legacy Criteria → JPA
  Criteria, `@Type(type="...")` / `@TypeDef` → `@JdbcTypeCode`, and N+1
  triage all require call-site-specific judgment. They are encoded as
  prose steps that fan out to the reference docs, not as scripts that would
  attempt a brittle bulk rewrite.
- **Monitoring → step + reference.** Enabling statistics and SQL logging is
  configuration-edit work; it's a real migration step, but the actual
  property keys live in `references/configuration.md`.
- **Anti-patterns → anti_patterns.** The "Common Errors" / "Testing
  Considerations" warnings become a short anti_patterns list. Detail lives
  in the references.
- **Sources URLs → dropped.** The original's `## Sources` section (three
  external URLs at the end) is reference material for the human reader of
  the runbook, not actionable instruction for the agent. Documented here as
  a deliberate drop.

## Relationship to the sibling `jakarta-namespace` skill

The original SKILL.md opens with a "Package Namespace" section pointing out
that Hibernate 6 uses `jakarta.persistence`. That namespace migration is
the entire scope of the sibling `jakarta-namespace` skill in this task. The
hibernate-upgrade skill does not re-encode that work — it assumes the
namespace migration is handled separately (or has already happened) and
focuses on Hibernate-specific changes. The body's `trigger_when` and the
breaking-changes reference both stay scoped to Hibernate concerns.

## Deliberate drops

- The "Sources" section (three external URLs at the end of the original
  SKILL.md). Rationale above.
- The "Package Namespace" subsection that overlaps with the
  `jakarta-namespace` skill. Rationale above; not re-encoded to avoid
  duplicate-step churn during a multi-skill migration.

# Source materials — spring-boot-migration (AIP conversion)

## Origin

This AIP skill was compiled from the curated Agent Skill at:

```
vendor/skillsbench/tasks/spring-boot-jakarta-migration/environment/skills/spring-boot-migration/SKILL.md
```

A verbatim copy lives at `original-SKILL.md` for traceability.

## Schema

Validates against `procedure.schema.json` (bundled in this folder), pinned to
AIP `v0.3a2`. The original skill is a Spring Boot 2 → 3 migration runbook — a
linear-with-optional-fan-out execution graph of pom edits, dependency removals,
and verification commands. That is exactly what the `procedure` schema models,
so no new schema was drafted.

## Mapping summary

| Source section                               | Destination                                                                                  |
| -------------------------------------------- | -------------------------------------------------------------------------------------------- |
| Overview                                     | `purpose`                                                                                    |
| Key Migration Steps §§ 1–4                   | `steps[update-spring-boot-parent, update-java-version, remove-legacy-deps, update-jwt]`      |
| Common Issues §§ 1–3                         | `references/common-issues.md` + integrations / anti_patterns                                 |
| Migration Commands (sed)                     | `scripts/update_pom_versions.sh`                                                             |
| OpenRewrite section                          | `modes[automated]` + `scripts/openrewrite_run.sh` + `references/pom-snippets.md` § 5         |
| Verification Steps (grep + mvn)              | `scripts/verify_migration.sh` + `steps[verify-pom, compile-and-test]`                        |
| Migration Checklist                          | `references/common-issues.md` (Migration checklist)                                          |
| Recommended Migration Order                  | `references/common-issues.md` (Recommended migration order); reflected in step order         |
| Sources                                      | `references/common-issues.md` (Sources)                                                      |
| Issue 1 cross-ref (javax → jakarta)          | `integrations[Jakarta Namespace skill]`; also rewritten automatically by OpenRewrite recipe  |
| Issue 3 cross-ref (Spring Security)          | `integrations[Spring Security 6 skill]`                                                      |
| Checklist cross-ref (RestTemplate)           | `integrations[RestClient Migration skill]`                                                   |

## Deliberate drops

- The duplicate H2 dialect property snippet ("Before / After" with identical
  class names) is reduced to a single mention in `references/common-issues.md`
  with the actual change — Hibernate 6 typically auto-detects it. The original
  formatting suggested a change where the class name was unchanged; no agent
  guidance is lost.
- The free-standing `sed` examples for Java 1.8 / 8 / 11 → 21 are folded into
  `scripts/update_pom_versions.sh`, which performs all three substitutions in
  one invocation parameterized by the desired target version.

## Files

- `procedure.schema.json` — bundled AIP schema (procedure category).
- `original-SKILL.md` — unmodified copy of the source skill for diffs.
- `README.md` — this file.

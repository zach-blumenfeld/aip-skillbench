# hibernate-upgrade — AIP compilation notes

Source: `source/CURATED-SKILL.md` (the original freeform Agent Skill from
`vendor/skillsbench/tasks/spring-boot-jakarta-migration/environment/skills/hibernate-upgrade/SKILL.md`).

Schema: `source/procedure.schema.json` (AIP v0.3a3 procedure schema, bundled
for self-containment).

## Script vs prose decisions

Mechanical and deterministic logic was moved into `scripts/`; everything that
requires the agent to read code and decide stayed in prose.

| Source content                                      | Compiled as            | Rationale |
|-----------------------------------------------------|------------------------|-----------|
| Migration-command grep audit (Criteria, @Type, etc.) | `scripts/scan_hibernate_patterns.py` | Fixed regex catalog, no judgment. Reused by every downstream step. |
| `sed s/update from /update /g` rewrite              | `scripts/apply_mechanical_fixes.py`  | Deterministic textual substitution. Generalised to also handle `javax.persistence` → `jakarta.persistence` imports (the namespace-rename overlap with the parent migration). |
| Observability properties block                       | `scripts/patch_observability_config.py` | Fixed property list, idempotent insertion. |
| Criteria API → JPA Criteria rewrite                 | Prose step `migrate-legacy-criteria` + reference cheat-sheet | Call shape changes per use site; needs reading surrounding code. |
| Custom type migration (`@TypeDef`, `@Type`)         | Prose step `migrate-custom-types`     | Per-type decision: built-in `@JdbcTypeCode` vs class-ref `@Type`. |
| JPQL / native query audit                           | Prose step `review-queries`            | Semantic review (distinct on join-fetch only, implicit joins, etc.). |
| Dialect cleanup                                      | Prose step `review-dialect-config`     | Depends on whether non-default behaviour is needed. |
| Build / test loop                                    | Prose step `build-and-verify`          | Project-specific tooling. |
| N+1 monitoring                                       | Prose step `monitor-performance`       | Requires interpretation of Hibernate stat output. |

## Source coverage classification

Walked the curated SKILL.md section-by-section.

- **Mapped** — every section listed below appears in the compiled body or
  references file:
  - § Overview → `purpose`
  - § 1 Package namespace → `apply_mechanical_fixes` (import rewrite)
  - § 2 ID generation → references/hibernate-6-migrations.md § ID generation +
    prose step output advice
  - § 3 Dialect config → prose step `review-dialect-config` + references § Dialect
  - § 4 Query changes (JPQL + native) → prose step `review-queries` + references § JPQL/HQL audit
  - § 5 Type mappings (enum / java.time) → references § Type-mapping defaults
  - § 6 Fetch strategies → captured under the LAZY-default guidance in references § ID/Type defaults / N+1 monitoring
  - § Deprecation removals (`@Type`, `@TypeDef`, legacy generators) → prose step `migrate-custom-types` + references § Custom type mappings
  - § Configuration properties → `patch_observability_config.py` + prose `review-dialect-config`
  - § Testing considerations → prose step `build-and-verify` (rolled into the validation loop)
  - § Troubleshooting common errors → references § Troubleshooting table
  - § Critical breaking changes (1 update-from, 2 distinct, 3 Criteria, 4 N+1) → scripts + prose steps + references
  - § Migration commands (greps) → `scan_hibernate_patterns.py`
  - § Migration commands (sed `update from`) → `apply_mechanical_fixes.py`
  - § Performance monitoring → `patch_observability_config.py` + prose `monitor-performance`
  - § Sources → references § Sources

- **Deliberate drops** — none. Every line of the curated SKILL.md has a home.

- **Schema gaps** — none. The `procedure` schema fits cleanly: scripts for
  deterministic steps, prose for judgement steps, references for on-demand
  detail, anti-patterns for the well-known traps.

## Decisions worth flagging

- The `apply_mechanical_fixes` script handles both the in-scope rewrite from
  the source (`update from`) **and** the parent migration's namespace rename
  (`javax.persistence` → `jakarta.persistence`). The curated source treated
  the namespace rename as Hibernate-adjacent context; folding it into the
  script keeps the hibernate-upgrade skill useful even when the broader
  jakarta-namespace skill is not loaded.
- `distinct ... join fetch` removal was *not* scripted. The pattern is
  detected by `scan_hibernate_patterns.py` but applying the rewrite blindly
  risks deleting an intentional `distinct` on a non-join-fetch query that
  shares the same line. The prose step asks the agent to confirm per match.
- The references file is loaded only when the prose steps trigger it
  (Criteria rewrite, custom-type rewrite, troubleshooting). Progressive
  disclosure keeps `SKILL.md` under the 5000-token budget.

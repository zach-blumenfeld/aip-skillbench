---
name: hibernate-upgrade
description: Migrate Hibernate 5 to Hibernate 6 within a Spring Boot 3 / Jakarta upgrade. Use when fixing HQL/JPQL parser errors, removing the legacy org.hibernate.Criteria API, replacing @TypeDef / @Type custom-type annotations, updating ID generation strategies, cleaning up dialect configuration, or diagnosing N+1 query regressions after the upgrade. Covers breaking changes, mechanical rewrites, type mappings, and observability.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a3
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a3/assets/aip-schemas/procedure.schema.json
compatibility: Java/Spring Boot 3 project on the local filesystem. Requires python3 to run the bundled scripts and the project's own build tool (Maven/Gradle) to verify.
---

```yaml
purpose: >
  Carry a Spring Boot 3 codebase across the Hibernate 5 -> 6 boundary. Detect
  every H5 pattern in the project, apply the deterministic rewrites in one
  pass, then walk the agent through the judgement-required migrations
  (legacy Criteria API, custom type mappings, JPQL audit, dialect cleanup)
  and verify with the project build plus observability props for N+1
  regression hunting.

trigger_when:
  - User asks to upgrade Hibernate 5 to Hibernate 6 (often as part of a Spring Boot 2 -> 3 / Jakarta migration).
  - Build fails with org.hibernate.query.SyntaxException or "Could not determine recommended JdbcType".
  - References to org.hibernate.Criteria, Restrictions.*, @TypeDef, or @Type(type = "...") appear in the codebase.
  - "@Query strings contain `update from` or `select distinct ... join fetch`."
  - Post-upgrade smoke testing surfaces N+1 query regressions or slow page loads.
  - User mentions Hibernate 6, JdbcTypeCode, or jakarta.persistence migrations.

do_not_use_when:
  - The project is still on Spring Boot 2 / Hibernate 5 and not yet migrating.
  - The migration target is Hibernate 7 (not yet covered).
  - The work is unrelated ORM tuning (query optimisation on a stable H6 baseline) — use general database/ORM skills instead.

scope_and_approval: >
  Write actions: `apply_mechanical_fixes` modifies Java source files in place;
  `patch_observability_config` appends properties to application.properties.
  Both are idempotent. Run `apply_mechanical_fixes --dry-run` first if the
  user wants to preview, and confirm before writing when the working tree
  has uncommitted changes outside the migration scope. All judgement steps
  (Criteria rewrite, custom type mappings, query audit) edit code one site
  at a time — surface each change to the user before moving on.

steps:
  - name: scan-hibernate-patterns
    description: Catalog every Hibernate 5 pattern in the project as a structured JSON report that drives the rest of the procedure.
    script: scripts/scan_hibernate_patterns.py
    inputs:
      - name: project_root
        type: string
        description: Absolute path to the Spring Boot project root.
    outputs:
      - name: findings
        type: object
        description: "{java: {legacy_criteria_api, type_annotation, typedef_annotation, update_from_hql, javax_persistence_import, javax_persistence_reference, distinct_join_fetch}, config: {explicit_dialect, hibernate_dialect_alt, generate_statistics, timezone_storage}, summary}."

  - name: triage-findings
    description: >
      Read the summary counts from `findings`. If every count is zero, stop
      and report no migration work. Otherwise group sites by remediation
      type and decide the step order (scripts first, then judgement steps in
      the order that minimises rework — Criteria before queries because
      Criteria rewrites change query text).
    inputs:
      - name: findings
        type: object
    outputs:
      - name: work_plan
        type: object
        description: Per-category lists of files and the step that will handle each.

  - name: apply-mechanical-fixes
    description: Run the deterministic rewrites — `javax.persistence` -> `jakarta.persistence` imports and `update from <E>` -> `update <E>` in @Query strings. Idempotent; safe to re-run.
    script: scripts/apply_mechanical_fixes.py
    depends_on: [triage-findings]
    inputs:
      - name: project_root
        type: string
      - name: work_plan
        type: object
    outputs:
      - name: mechanical_changes
        type: object
        description: "{files_changed, javax_to_jakarta_imports, update_from_rewrites, files: [...]}"

  - name: migrate-legacy-criteria
    description: >
      For each `legacy_criteria_api` site, rewrite the call into JPA
      CriteriaBuilder. Read `references/hibernate-6-migrations.md` § Legacy
      Criteria API for the call-shape change and the Restrictions translation
      cheat-sheet. Edit one file at a time; if the surrounding code reaches
      Session via `entityManager.unwrap(Session.class)`, prefer holding the
      EntityManager directly going forward.
    depends_on: [apply-mechanical-fixes]
    inputs:
      - name: findings
        type: object
    outputs:
      - name: criteria_migrations
        type: list[object]
        description: One entry per rewritten site with file, line range, and a short note on the transformation applied.

  - name: migrate-custom-types
    description: >
      For each `type_annotation` and `typedef_annotation` site, decide
      between `@JdbcTypeCode(SqlTypes.X)` (preferred when a built-in JDBC
      type covers the column — JSON, XML, UUID, etc.) and
      `@Type(MyCustomType.class)` (when a custom UserType is still needed).
      Drop the matching `@TypeDef` registration in the same file or
      package-info.java. Reference `references/hibernate-6-migrations.md`
      § Custom type mappings.
    depends_on: [apply-mechanical-fixes]
    inputs:
      - name: findings
        type: object
    outputs:
      - name: type_migrations
        type: list[object]

  - name: review-queries
    description: >
      Walk every `distinct_join_fetch` finding and every @Query referenced
      under `update_from_hql` after the script pass. For
      `distinct ... join fetch`, drop the `distinct` keyword — Hibernate 6
      de-duplicates root entities from join-fetched collections
      automatically. For any remaining `update from`, confirm the script
      missed it because the @Query is built at runtime, then fix the string
      builder. Also audit each @Query for implicit joins and missing entity
      aliases (H6 parser rejects them). Reference
      `references/hibernate-6-migrations.md` § JPQL/HQL audit.
    depends_on: [migrate-legacy-criteria]
    inputs:
      - name: findings
        type: object
    outputs:
      - name: query_changes
        type: list[object]

  - name: review-dialect-config
    description: >
      Inspect every `explicit_dialect` / `hibernate_dialect_alt` site.
      Hibernate 6 auto-detects dialect from the JDBC URL — remove the
      property unless the project needs a non-default behaviour (forced
      function quoting, vendor-specific extension). If the property stays,
      verify the dialect class still exists in H6 (several version-suffixed
      classes were dropped in favour of unversioned auto-detecting ones).
    depends_on: [triage-findings]
    inputs:
      - name: findings
        type: object
    outputs:
      - name: config_changes
        type: list[object]

  - name: enable-observability
    description: >
      Add Hibernate 6 observability properties (statistics, SQL logging,
      timezone normalisation, slow-query threshold) to application.properties
      so the build-and-verify step can detect N+1 regressions. Idempotent.
      Pass `--target <relative_path>` if the project has multiple
      properties files and you want to override the default selection.
    script: scripts/patch_observability_config.py
    depends_on: [triage-findings]
    inputs:
      - name: project_root
        type: string
    outputs:
      - name: properties_added
        type: list[string]

  - name: build-and-verify
    description: >
      Run the project's build (`./mvnw verify` or `./gradlew test` — use
      whatever the project actually uses). Classify failures using the
      troubleshooting table in `references/hibernate-6-migrations.md`
      § Troubleshooting common errors and route each back to the relevant
      step (`Unknown entity` -> check for leftover javax.persistence /
      `@EntityScan`; `Could not determine recommended JdbcType` ->
      migrate-custom-types missed a site; `SyntaxException` -> review-queries
      missed a site). Iterate until the build is green.
    depends_on: [migrate-custom-types, review-queries, review-dialect-config, enable-observability]
    outputs:
      - name: build_status
        type: object
        description: "{green: bool, residual_errors: list[object]}"

  - name: monitor-performance
    description: >
      Exercise the hot paths against the observability-enabled build. In
      the `org.hibernate.stat` output, watch for EntityFetchCount exceeding
      EntityLoadCount on the same entity — that is the N+1 signature.
      Mitigate (in order of preference) with a targeted `@EntityGraph`, a
      `JOIN FETCH` repository query, or `@BatchSize` on the collection.
      Skip this step only if the user explicitly opts out.
    depends_on: [build-and-verify]
    outputs:
      - name: n_plus_1_observations
        type: list[object]

scenarios:
  - need: "Build fails with `org.hibernate.query.SyntaxException: at line 1, column 8` on a bulk delete repository method."
    context: scan-hibernate-patterns reports two `update_from_hql` sites in `UserRepository.java`.
    action: apply-mechanical-fixes rewrites `update from User u set u.active = false ...` to `update User u set u.active = false ...`. Build advances past the parser.
    outcome: Bulk update repositories compile against H6 without further intervention.
  - need: Build fails with `Could not determine recommended JdbcType for type 'com.fasterxml.jackson.databind.JsonNode'` on an entity field.
    context: scan-hibernate-patterns finds a `@Type(type = "json")` annotation paired with a `@TypeDef` registration in `package-info.java`.
    action: migrate-custom-types replaces the field annotation with `@JdbcTypeCode(SqlTypes.JSON)` and deletes the `@TypeDef`. Build succeeds.
    outcome: JSON columns round-trip without the third-party type registry.
  - need: Post-upgrade, the /orders page renders 5x slower than before.
    context: enable-observability appended hibernate.generate_statistics=true and org.hibernate.stat=debug; logs show 51 SELECTs per page load against `orders`.
    action: monitor-performance identifies the N+1 on `Order.lineItems`. Add `@EntityGraph(attributePaths = "lineItems")` to the repository finder.
    outcome: /orders page issues one SELECT plus one JOIN per request; latency back to baseline.

anti_patterns:
  - Running `apply_mechanical_fixes` over a dirty working tree without inspecting the diff afterwards — the script is conservative but the user should still review.
  - Blindly stripping `distinct` from every JPQL query — H6 only auto-deduplicates root entities under `join fetch`; non-fetch queries may still need `distinct`.
  - Replacing every `@Type(type = "...")` with `@JdbcTypeCode` without checking that a built-in JDBC type covers the column. For genuinely custom `UserType` implementations, the correct H6 form is `@Type(MyCustomType.class)`.
  - Leaving an explicit `spring.jpa.database-platform` for a removed versioned dialect class — application startup fails. Either remove the property (H6 auto-detects) or switch to the unversioned class.
  - Skipping `enable-observability` and declaring the migration done before exercising hot paths — N+1 regressions are the most common silent breakage from H5 -> H6.
  - Using `GenerationType.AUTO` on a cross-database project — H6 resolves it differently per dialect. Pick IDENTITY or SEQUENCE explicitly.
```

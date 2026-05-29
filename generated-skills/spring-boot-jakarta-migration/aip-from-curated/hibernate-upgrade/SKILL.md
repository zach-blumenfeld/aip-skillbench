---
name: hibernate-upgrade
description: Migrate Hibernate 5 to Hibernate 6 with Spring Boot 3. Use when fixing HQL/JPQL query parsing issues, removing deprecated Criteria API, updating ID generation strategies, or diagnosing N+1 query behavior changes. Covers breaking changes, type mappings, and performance monitoring.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a2/assets/aip-schemas/procedure.schema.json
compatibility: Requires bash, grep, find, and sed (GNU or BSD). Targets a Spring Boot 3.x / Hibernate 6 codebase migrated from Spring Boot 2.x / Hibernate 5.
---

```yaml
purpose: >
  Migrate a Spring Boot codebase from Hibernate 5 to Hibernate 6 — the ORM
  version bundled with Spring Boot 3. Cover the breaking changes the agent
  must address before the project compiles and runs: stricter HQL/JPQL
  parsing, removal of the legacy `org.hibernate.Criteria` API, deprecated
  `@Type(type="...")` / `@TypeDef` annotations, ID-generation and dialect
  changes, and N+1 / performance behavior shifts that may need
  monitoring. The Jakarta `javax.* → jakarta.*` namespace migration is a
  separate concern handled by the sibling `jakarta-namespace` skill and is
  not duplicated here.

trigger_when:
  - Upgrading a project from Spring Boot 2.x to Spring Boot 3.x (which pulls
    in Hibernate 6).
  - Build or runtime errors after the upgrade naming `org.hibernate.Criteria`,
    `session.createCriteria`, `Restrictions`, `@Type(type=...)`, or
    `@TypeDef`.
  - HQL/JPQL queries failing to parse under Hibernate 6 (especially queries
    containing `update from`, redundant `distinct` on `join fetch`, or
    implicit-path joins).
  - Removed/renamed Hibernate dialect class causing
    `ClassNotFoundException` / `NoClassDefFoundError` at startup.
  - Unexpected N+1 query patterns or performance regressions surfacing after
    a Hibernate 6 upgrade.
  - User asks to migrate, upgrade, or audit a project for Hibernate 5 → 6.

do_not_use_when:
  - The project targets Spring Boot 2.x / Hibernate 5 and is not migrating —
    the changes here are breaking and Hibernate-6-specific.
  - The only outstanding work is the `javax.* → jakarta.*` import rewrite —
    use the sibling `jakarta-namespace` skill for that.
  - The codebase already runs cleanly on Hibernate 6 and the user is asking
    a general JPA modeling question, not an upgrade question.

scope_and_approval: >
  Discovery and verification scripts are read-only. The single mechanical
  rewrite script (`scripts/fix_update_from.sh`) edits .java files in place;
  recommend (or ensure) a clean git working tree before running it so the
  diff is reviewable and revertable. All structural rewrites — Criteria API,
  custom types, dialect overrides — are guidance steps for the agent to
  perform call-site by call-site, not bulk transforms.

steps:
  - name: load-breaking-changes
    description: >
      Read `references/breaking-changes.md` for the full set of Hibernate
      5 → 6 breaking changes with before/after examples and the legacy-
      Criteria → JPA-Criteria mapping cheatsheet. This is the primary
      reference for the rest of the procedure.
    outputs:
      - name: breaking-changes-loaded
        type: boolean

  - name: discover
    description: >
      Scan the target directory for Hibernate 5 patterns that need attention.
      Output is grouped by category (legacy Criteria, deprecated @Type
      annotations, `update from`, redundant `distinct join fetch`, dialect
      references, legacy ID generators). Empty sections mean that category
      needs no action.
    script: scripts/find_hibernate5_patterns.sh
    depends_on: [load-breaking-changes]
    inputs:
      - name: target-dir
        type: string
        description: Directory to scan; defaults to current working directory.
    outputs:
      - name: hibernate5-pattern-hits
        type: object
        description: Categorized list of `<file>:<lineno>:<match>` hits.

  - name: fix-update-from
    description: >
      Mechanical rewrite of `update from <Entity>` HQL/JPQL to the standards-
      compliant `update <Entity>` form. Hibernate 6's stricter parser rejects
      the optional `from`. The script is idempotent and safe to skip if
      discovery found no `update from` matches.
    script: scripts/fix_update_from.sh
    depends_on: [discover]
    inputs:
      - name: target-dir
        type: string
    outputs:
      - name: update-from-rewrite-applied
        type: boolean

  - name: rewrite-legacy-criteria
    description: >
      For each `org.hibernate.Criteria` / `session.createCriteria` /
      `org.hibernate.criterion.Restrictions` hit from discovery, rewrite the
      call site to the JPA Criteria API (`CriteriaBuilder`, `CriteriaQuery`,
      `Root`). Use the mapping cheatsheet in
      `references/breaking-changes.md` §3. This is a structural rewrite —
      do not attempt a bulk sed transform. Skip if discovery found no hits.
    depends_on: [discover]
    inputs:
      - name: hibernate5-pattern-hits
        type: object
    outputs:
      - name: criteria-rewrite-complete
        type: boolean

  - name: rewrite-type-annotations
    description: >
      For each `@Type(type = "...")` and `@TypeDef` hit from discovery,
      replace per `references/type-mappings.md`:
      JSON columns → `@JdbcTypeCode(SqlTypes.JSON)`; other custom types →
      `@Type(value = CustomType.class)`. `@TypeDef` is removed entirely;
      the type class registration moves to the field-level `@Type`. Skip
      if discovery found no hits.
    depends_on: [discover]
    inputs:
      - name: hibernate5-pattern-hits
        type: object
    outputs:
      - name: type-rewrite-complete
        type: boolean

  - name: review-distinct-fetch
    description: >
      Review each `select distinct ... join fetch` hit. In Hibernate 6
      `distinct` is redundant for duplicate suppression on collection
      fetches. Drop it where the intent was just duplicate suppression;
      keep it where it has genuine unique-result semantics. Judgment call
      per call site — see `references/breaking-changes.md` §2.
    depends_on: [discover]
    inputs:
      - name: hibernate5-pattern-hits
        type: object
    outputs:
      - name: distinct-fetch-reviewed
        type: boolean

  - name: review-id-and-dialect
    description: >
      Review explicit dialect overrides and ID-generation strategies per
      `references/configuration.md` and `references/type-mappings.md` §ID
      Generation. Hibernate 6 auto-detects dialects from the JDBC URL —
      explicit overrides on removed/renamed classes (e.g. `MySQL57Dialect`,
      `PostgreSQL95Dialect`) must be dropped or replaced with the
      unversioned class. Pin `@GeneratedValue` to a specific strategy
      (`IDENTITY` or `SEQUENCE`) rather than relying on `AUTO`.
    depends_on: [discover]
    outputs:
      - name: id-and-dialect-reviewed
        type: boolean

  - name: enable-monitoring
    description: >
      Add the Hibernate-6 monitoring properties from
      `references/configuration.md` to `application.properties` (or the YAML
      equivalent) for the duration of the migration window: statistics,
      SQL logging, and on 6.2+ the slow-query log. This surfaces N+1
      regressions and query-plan shifts before they reach production. Plan
      to remove the debug-level logging after the migration stabilizes.
    outputs:
      - name: monitoring-enabled
        type: boolean

  - name: verify
    description: >
      Confirm no Hibernate-5 patterns remain that must be zero after
      migration: legacy Criteria API references, `@Type(type=...)`,
      `@TypeDef`, and `update from` queries. Non-zero exit means the
      upgrade is incomplete and the project will fail to compile or run
      under Hibernate 6.
    script: scripts/verify_upgrade.sh
    depends_on:
      - fix-update-from
      - rewrite-legacy-criteria
      - rewrite-type-annotations
    inputs:
      - name: target-dir
        type: string
    outputs:
      - name: verification-passed
        type: boolean

  - name: smoke-test
    description: >
      Build the project and run the existing test suite. Watch the SQL log
      enabled by `enable-monitoring` for unexpected query patterns,
      especially around `join fetch` paths and lazy collections. Where a
      regression appears, apply `@EntityGraph`, `join fetch`, or
      `@BatchSize` per `references/breaking-changes.md` §4.
    depends_on: [verify]
    outputs:
      - name: smoke-test-passed
        type: boolean

scenarios:
  - need: Spring Boot 3 build fails with "QuerySyntaxException" near `update from User`.
    context: Discovery script returns matches in `update-from-queries`.
    action: Run `scripts/fix_update_from.sh`, then `scripts/verify_upgrade.sh`.
    outcome: Update queries parse cleanly under Hibernate 6.

  - need: Build fails with "cannot find symbol Criteria" in a repository class.
    context: Discovery script returns hits in `legacy-criteria-api`.
    action: Rewrite each call site to JPA Criteria per the cheatsheet in `references/breaking-changes.md` §3.
    outcome: Queries compile against Hibernate 6 and produce equivalent results.

  - need: "@Type(type = \"json\") fails to compile after upgrade."
    context: Discovery script returns hits in `deprecated-type-annotations`.
    action: Replace with `@JdbcTypeCode(SqlTypes.JSON)`; remove the corresponding `@TypeDef` registration.
    outcome: JSON columns map cleanly using Hibernate 6's built-in JSON type.

  - need: Application starts but a previously fast endpoint now issues hundreds of SQL queries.
    context: Monitoring enabled per `enable-monitoring` reveals lazy-collection N+1 on a path that batched under Hibernate 5.
    action: Add `@EntityGraph` to the repository method (or a `join fetch`); re-test.
    outcome: Query count returns to baseline; endpoint latency restored.

  - need: "Startup fails with `ClassNotFoundException: org.hibernate.dialect.MySQL57Dialect`."
    context: "`spring.jpa.database-platform` pins a Hibernate-5-era versioned dialect class that was removed in Hibernate 6."
    action: Drop the override (let auto-detection run) or replace with `org.hibernate.dialect.MySQLDialect`.
    outcome: Application starts; dialect resolves from the JDBC URL.

anti_patterns:
  - Skipping discovery and trying to fix patterns from build errors alone. Build errors surface one class at a time; discovery surfaces every call site in one pass.
  - Attempting a bulk sed transform on the legacy Criteria API. The rewrite is structural — each call site has its own predicates and joins. Bulk transforms produce non-compiling salad.
  - Running `scripts/fix_update_from.sh` on a dirty working tree. The rewrite is mechanical but bulk; a clean tree makes the diff reviewable and the operation revertable.
  - Leaving an explicit Hibernate-5-era dialect override in place "just to be safe". Removed/renamed dialect classes cause startup failures; auto-detection from the JDBC URL is the Hibernate 6 default for a reason.
  - Removing `distinct` from every `join fetch` indiscriminately. Some `distinct` usages encode genuine unique-result semantics, not duplicate suppression. Review per call site.
  - Treating an N+1 regression as a Hibernate 6 bug. The regression is a behavior shift; the fix is the same as it always was — `@EntityGraph`, `join fetch`, or `@BatchSize`.
  - Declaring the upgrade complete without running `scripts/verify_upgrade.sh`. A missed `@TypeDef` or legacy `Criteria` import can hide in a rarely-built module and bite at runtime.
  - Leaving statistics + SQL debug logging on in production. They have meaningful overhead; turn them off once the migration stabilizes.
```

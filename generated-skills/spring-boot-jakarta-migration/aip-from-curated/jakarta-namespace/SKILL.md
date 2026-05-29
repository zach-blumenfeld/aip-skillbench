---
name: jakarta-namespace
description: Migrate Java EE javax.* imports to Jakarta EE jakarta.* namespace. Use when upgrading to Spring Boot 3.x, migrating javax.persistence, javax.validation, javax.servlet imports, or fixing compilation errors after Jakarta EE transition. Covers package mappings, batch sed commands, and verification steps.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a3
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a3/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Rewrite every migration-candidate `javax.*` import in a Java source tree to
  its `jakarta.*` equivalent for Spring Boot 3+. Java EE moved to Jakarta EE
  at Spring Boot 3.0, so packages like `javax.persistence`, `javax.validation`,
  and `javax.servlet` must move; JDK-internal packages (`javax.sql`,
  `javax.crypto`, `javax.net`, etc.) must stay. Work the tree end-to-end:
  inventory every javax import, apply the deterministic prefix rewrite, sweep
  the non-Java surfaces (persistence.xml, property keys) by hand, and finish on
  a green verifier plus `mvn clean compile` / `mvn test`.

trigger_when:
  - Upgrading a Spring Boot 2.x project to Spring Boot 3.x.
  - User mentions migrating `javax.persistence`, `javax.validation`, `javax.servlet`, or Jakarta EE.
  - Compilation fails after a Spring Boot 3 upgrade with "cannot find symbol" on JPA, validation, or servlet types.
  - Reviewing a codebase that mixes `javax.*` and `jakarta.*` imports and needs consolidation.
  - A new JPA entity, validation annotation, or servlet was added on `javax.*` in a Spring Boot 3 module.

do_not_use_when:
  - The project is staying on Spring Boot 2.x — Java EE `javax.*` is still correct there.
  - The only `javax.*` imports are JDK packages (`javax.sql`, `javax.crypto`, `javax.net`, `javax.security`, `javax.naming`, `javax.management`, `javax.xml.parsers`/`transform`/`stream`/`xpath`/etc.) — those stay on `javax` regardless of Spring Boot version.
  - The task is reactive HTTP-client migration, RestTemplate→RestClient, or other non-namespace Spring Boot 3 work — those have their own skills.

scope_and_approval: >
  Read-only on the source tree until `apply-namespace-migration` runs. The
  migration script edits `*.java` files in place (with a `.bak` removed on
  success) — preview with `--dry-run` first if the user wants confirmation
  before a write. No network calls unless the OpenRewrite arm is chosen
  (Maven downloads the plugin). No dependency manifest changes; the Spring
  Boot 3 upgrade is assumed already applied. `mvn clean compile` and
  `mvn test` are the final verification gates — both must pass.

steps:
  - name: inventory-javax-imports
    description: Scan the source tree for every `javax.*` import that needs migration. The script excludes JDK-internal packages (javax.sql, javax.crypto, javax.net, javax.security, javax.naming, javax.management, javax.xml.* except javax.xml.bind) — those stay on javax.
    script: scripts/inventory_javax_imports.sh
    inputs:
      - name: src-root
        type: string
        description: Path to the Java source root to scan (e.g., the project root or `src/`).
    outputs:
      - name: import-inventory
        type: list[object]
        description: One row per match — `{file, line, group, import}`. `group` is the Jakarta EE family (persistence, validation, servlet, annotation, transaction, ws.rs, mail, jms, xml.bind, inject, enterprise, ejb, json, batch, other). Used as the worklist for the rewrite and verification steps.

  - name: review-inventory-and-pick-approach
    description: >
      Read the inventory. If the count is non-trivial or coverage spans many
      Jakarta EE families, prefer the scripted batch rewrite. If the project
      already runs Maven and the user wants the broadest possible automated
      coverage (including XML and properties), prefer OpenRewrite. For a tiny
      number of files (≤3) or surgical edits, hand-rewrite with the Edit tool
      using `references/package-mappings.md` as the lookup.
    depends_on:
      - inventory-javax-imports
    inputs:
      - name: import-inventory
        type: list[object]
    outputs:
      - name: approach
        type: string
        description: One of `script`, `openrewrite`, `manual` — drives which path runs in `apply-namespace-migration`.
    one_of:
      - script — run scripts/migrate_javax_to_jakarta.sh (default; dependency-free, fast, covers every prefix in references/package-mappings.md).
      - openrewrite — add the rewrite-maven-plugin and run `mvn rewrite:run` (broader coverage including XML and properties, but requires Maven and network).
      - manual — Edit tool, file by file (only for ≤3 files or when the user wants every change reviewed individually).

  - name: apply-namespace-migration
    description: >
      Rewrite candidate `javax.*` imports to `jakarta.*` over the source tree.
      Run `scripts/migrate_javax_to_jakarta.sh <src-root>` for the scripted path
      (the script handles wildcard imports — the `javax.persistence` prefix
      match rewrites both `javax.persistence.Entity` and `javax.persistence.*`).
      For the OpenRewrite path, install the `rewrite-maven-plugin` per
      `references/package-mappings.md` § OpenRewrite alternative and run
      `mvn rewrite:run`. For the manual path, Edit each file using the mapping
      table in `references/package-mappings.md`.
    script: scripts/migrate_javax_to_jakarta.sh
    depends_on:
      - review-inventory-and-pick-approach
    inputs:
      - name: src-root
        type: string
      - name: approach
        type: string
    outputs:
      - name: rewrite-report
        type: list[object]
        description: One row per rewritten file — `{file, replacements}`. Plus a stderr totals summary.

  - name: handle-non-java-surfaces
    description: >
      The migration scripts only rewrite `import` statements in `*.java`
      files. Sweep the project for non-Java surfaces and edit them by hand —
      this is judgment work, not a sed run. Targets:
      `persistence.xml` (`xmlns` → `https://jakarta.ee/xml/ns/persistence`,
      `version` → `3.0` or higher),
      `web.xml` / `beans.xml` / `faces-config.xml` (same xmlns family swap),
      `application.properties` / `application.yml` keys starting with
      `javax.persistence.*` (e.g., `javax.persistence.schema-generation.*`
      → `jakarta.persistence.schema-generation.*`), and any fully-qualified
      `javax.<jakarta-family>.*` type references inside `.java` files that
      slipped past the import-only rewrite. See
      `references/package-mappings.md` § Non-Java surfaces.
    depends_on:
      - apply-namespace-migration
    outputs:
      - name: non-java-edits
        type: list[object]
        description: One row per non-Java file edited — `{file, kind}`. Empty list if the project has no such surfaces.

  - name: verify-jakarta-namespace
    description: >
      Run `scripts/verify_migration.sh <src-root>`. Two checks must pass —
      (1) zero remaining migration-candidate `javax.*` imports, and (2) every
      file containing `@Entity` has at least one `jakarta.persistence` import.
      The script exits 2 on any failure and emits `fail\t...` rows on stdout;
      address each before continuing. The "entity without jakarta" failure is
      the hard signal that the migration is incomplete and the app will not
      start.
    script: scripts/verify_migration.sh
    depends_on:
      - handle-non-java-surfaces
    inputs:
      - name: src-root
        type: string
    outputs:
      - name: verification-report
        type: list[object]
        description: Rows of `ok|warn|fail` findings.

  - name: verify-compile-and-tests
    description: >
      Run `mvn clean compile`, then `mvn test`, from the project root. Both
      must pass. On a compile failure, the usual causes are a missing
      Jakarta-family import after a fully-qualified type slipped through,
      a third-party library still pinned to a `javax`-namespace version, or
      a property/XML key still on `javax.persistence.*` that Spring Boot 3
      no longer recognizes.
    depends_on:
      - verify-jakarta-namespace
    outputs:
      - name: build-verification
        type: object
        description: "Shape: {compile: pass|fail, tests: pass|fail, failures: [...]}."

scenarios:
  - need: 'JPA entity class still on `javax.persistence` after a Spring Boot 3 upgrade — app fails to start with "cannot find symbol: class Entity".'
    context: Inventory tagged the file as `persistence`. Wildcard import `javax.persistence.*` plus a handful of explicit ones.
    action: |
      Run `scripts/migrate_javax_to_jakarta.sh <src-root>`. The `javax.persistence` prefix match rewrites both
      `import javax.persistence.*;` and `import javax.persistence.Entity;` in one pass. Re-run the verifier;
      `entity-without-jakarta` should no longer appear.
    outcome: Every `@Entity` class compiles against `jakarta.persistence`; app starts.

  - need: Bean Validation constraints still on `javax.validation`.
    context: Inventory tagged DTOs as `validation` — `@Email`, `@NotBlank`, plus `@Valid` on controller method params.
    action: |
      Same scripted rewrite handles `javax.validation` → `jakarta.validation` across both `validation.constraints.*`
      and `validation.Valid`. No separate step needed.
    outcome: Constraint annotations resolve against `jakarta.validation`; validator runs without `ClassNotFoundException`.

  - need: Servlet filters on `javax.servlet.http.HttpServletRequest` / `HttpServletResponse`.
    context: Inventory tagged the filter chain as `servlet`. The filter implements `javax.servlet.Filter` directly.
    action: |
      Scripted rewrite covers both `javax.servlet.http.*` and `javax.servlet.*`. The `Filter` interface contract
      is unchanged on Jakarta — only the package moves. No code changes beyond the imports.
    outcome: Filters wire up via `jakarta.servlet`; the chain runs unchanged.

  - need: '`@PostConstruct` and `@PreDestroy` on `javax.annotation` in Spring beans.'
    context: Inventory tagged a few `@Service` and `@Configuration` classes as `annotation`.
    action: |
      Scripted rewrite handles the whole `javax.annotation` subtree (PostConstruct, PreDestroy, Resource, etc.) —
      no need for the three separate sed commands the original SKILL.md spelled out.
    outcome: Lifecycle hooks fire on `jakarta.annotation`; no startup warnings.

  - need: After the script runs, `mvn clean compile` still fails on a fully-qualified `javax.persistence.EntityManager` in a method signature.
    context: The script only touches `import` lines. A handful of fully-qualified type references slipped through.
    action: |
      Grep for any remaining `javax.(persistence|validation|servlet|annotation|transaction)\.` in `.java` files
      (the verifier surfaces these via the `stray-javax` rows only if they're on import lines, so run a broader
      grep yourself). Replace each fully-qualified usage with the jakarta equivalent via Edit.
    outcome: Compile passes; verifier returns "all checks passed".

  - need: 'Project also uses a `persistence.xml` with `xmlns="http://xmlns.jcp.org/xml/ns/persistence"`.'
    context: The script left it untouched — XML isn't `*.java`.
    action: |
      Edit `META-INF/persistence.xml`: set `xmlns` to `https://jakarta.ee/xml/ns/persistence`, bump
      `version` to `3.0` or higher, update the matching `xsi:schemaLocation`. Same family swap for `web.xml`,
      `beans.xml`, `faces-config.xml` if present.
    outcome: Hibernate / JPA provider parses the descriptor against the Jakarta schema; persistence unit boots.

  - need: User wants every change driven from a single tool, including XML and property keys.
    context: Project already uses Maven; network access is available; user prefers a recipe-driven migration.
    action: |
      Pick the `openrewrite` arm of `review-inventory-and-pick-approach`. Add the `rewrite-maven-plugin` block
      from `references/package-mappings.md` to `pom.xml` and run `mvn rewrite:run`. Then run
      `scripts/verify_migration.sh` to confirm — OpenRewrite occasionally misses edge cases the verifier catches.
    outcome: Imports, XML descriptors, and JPA property keys all migrated in one Maven run; verifier passes.

anti_patterns:
  - Rewriting `javax.sql.*` or `javax.crypto.*` to `jakarta.*`. These are JDK packages, not Java EE — they never moved. The inventory script excludes them; do not add them back.
  - Skipping test sources. The `find` / scripts must run over the whole tree (including `src/test/java`), not just `src/main/java` — test classes use `@Entity` and validation annotations too.
  - Leaving `persistence.xml` (and `web.xml` / `beans.xml`) on the old `xmlns` after rewriting the `import` lines. Spring Boot 3 will fail to bootstrap the persistence unit even though the Java compiles.
  - Treating a wildcard import (`import javax.persistence.*;`) as a special case requiring its own sed command. The prefix rewrite covers it in one pass.
  - Mixing `javax.*` and `jakarta.*` imports in the same module. The runtime ClassLoader treats them as distinct types — `@Entity(javax)` and `@Entity(jakarta)` don't unify, and Hibernate ignores entities annotated with the wrong one.
  - Forgetting third-party dependencies. If a library is still on the `javax`-namespace artifact (e.g., a pre-Jakarta Hibernate Validator, an old Jakarta Mail named `javax.mail`), the imports will rewrite cleanly but the classes won't resolve. Bump the dependency to its Jakarta-namespace version.
  - Skipping `mvn test` after the rewrite. Compilation can succeed while runtime wiring fails — e.g., a property key still on `javax.persistence.schema-generation.database.action` no longer reaches Hibernate under Spring Boot 3.
```

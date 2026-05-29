---
name: jakarta-namespace
description: Migrate Java EE javax.* imports to Jakarta EE jakarta.* namespace. Use when upgrading to Spring Boot 3.x, migrating javax.persistence, javax.validation, javax.servlet imports, or fixing compilation errors after Jakarta EE transition. Covers package mappings, batch sed commands, and verification steps.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a2/assets/aip-schemas/procedure.schema.json
compatibility: Requires bash, grep, find, and sed (GNU or BSD). Optional OpenRewrite path requires Maven.
---

```yaml
purpose: >
  Migrate a Java codebase from Java EE `javax.*` imports to Jakarta EE
  `jakarta.*` imports — the breaking namespace change required by Spring Boot
  3.x. Covers which packages move (and which JDK packages must stay on
  `javax.*`), batch rewrite via sed, optional OpenRewrite path, and
  verification that the migration is complete.

trigger_when:
  - Upgrading a project to Spring Boot 3.x.
  - Compilation errors after a Spring Boot 3 upgrade naming `javax.persistence`,
    `javax.validation`, `javax.servlet`, `javax.annotation`, or
    `javax.transaction`.
  - JPA entities still using `@Entity` / `@Table` / `@Column` from
    `javax.persistence`.
  - User asks to migrate, rewrite, or replace `javax.*` imports with
    `jakarta.*`.

do_not_use_when:
  - The project targets Spring Boot 2.x or earlier — Jakarta namespace breaks
    those versions.
  - The only `javax.*` imports in the codebase are JDK packages
    (`javax.sql`, `javax.crypto`, `javax.net`). Those do NOT migrate.

scope_and_approval: >
  The migration step rewrites .java files in place. Recommend (or ensure) a
  clean git working tree before running `scripts/migrate_imports.sh` so the
  diff is reviewable and revertable. Discovery and verification scripts are
  read-only.

steps:
  - name: load-package-mappings
    description: >
      Read `references/package-mappings.md` to load the canonical list of
      Java EE packages that migrate, JDK packages that must stay on `javax.*`,
      and worked before/after examples for entities, validation, and servlets.
    outputs:
      - name: mapping-loaded
        type: boolean

  - name: discover
    description: >
      Scan the target directory for `javax.*` imports that need migration.
      The script excludes JDK packages (`javax.sql`, `javax.crypto`,
      `javax.net`) so its output is exactly the set of imports the next step
      will rewrite. Empty output means no migration is needed.
    script: scripts/find_javax_imports.sh
    depends_on: [load-package-mappings]
    inputs:
      - name: target-dir
        type: string
        description: Directory to scan; defaults to current working directory.
    outputs:
      - name: javax-import-hits
        type: list[string]
        description: One entry per match in `<file>:<lineno>:<import>` form.

  - name: choose-migration-path
    description: >
      Pick the rewrite strategy. Default to the sed-based script unless the
      project is Maven-based AND the team wants a build-plugin-driven
      migration, in which case use OpenRewrite (see `references/openrewrite.md`
      and the `openrewrite` mode below).
    depends_on: [discover]
    one_of:
      - sed-batch-rewrite
      - openrewrite-recipe
    outputs:
      - name: chosen-path
        type: string

  - name: rewrite-imports
    description: >
      Rewrite `import javax.<eePkg>` to `import jakarta.<eePkg>` across every
      .java file under the target directory. Handles specific and wildcard
      imports; idempotent. Skip this step if `choose-migration-path` picked
      `openrewrite-recipe` — run `mvn rewrite:run` per `references/openrewrite.md`
      instead.
    script: scripts/migrate_imports.sh
    depends_on: [choose-migration-path]
    inputs:
      - name: target-dir
        type: string
        description: Directory to migrate; defaults to current working directory.
    outputs:
      - name: rewrite-applied
        type: boolean

  - name: verify
    description: >
      Confirm no `javax.*` Java EE imports remain, and that any code using
      `@Entity` also has `jakarta.persistence` imports somewhere. Non-zero
      exit means the migration is incomplete and the project will fail to
      compile under Spring Boot 3.
    script: scripts/verify_migration.sh
    depends_on: [rewrite-imports]
    inputs:
      - name: target-dir
        type: string
    outputs:
      - name: verification-passed
        type: boolean

  - name: check-non-java-configs
    description: >
      Java files are not the only place namespaces appear. Check
      `persistence.xml` (if used) and any other XML configuration for
      `javax.*` schema URIs or class references, and update those to
      `jakarta.*` too. Also confirm that third-party dependencies have
      Jakarta-compatible versions — mixed namespaces at runtime cause
      ClassNotFoundException / NoClassDefFoundError.
    depends_on: [verify]
    outputs:
      - name: config-checked
        type: boolean

modes:
  - name: sed-batch-rewrite
    body: >
      Default path. Run `scripts/migrate_imports.sh [target_dir]`, which uses
      `find` + portable `sed -i` to rewrite imports across every .java file.
      Fast, transparent, no build changes. Pair with a clean git working tree
      so the diff is reviewable.
  - name: openrewrite-recipe
    body: >
      Maven-based projects can use the OpenRewrite recipe
      `org.openrewrite.java.migrate.jakarta.JavaxMigrationToJakarta` to
      perform the rewrite. Configuration and `mvn rewrite:run` invocation are
      in `references/openrewrite.md`. After running, still execute
      `scripts/verify_migration.sh` to confirm coverage.

scenarios:
  - need: Spring Boot 3 upgrade fails with "package javax.persistence does not exist".
    context: Discovery script returns multiple `import javax.persistence.*` hits in entity classes.
    action: Run `scripts/migrate_imports.sh` then `scripts/verify_migration.sh`.
    outcome: All entities compile under Spring Boot 3; verification reports OK.

  - need: Add Bean Validation annotations to a DTO during a Spring Boot 3 build.
    context: Developer pastes `import javax.validation.constraints.NotBlank;` from old docs.
    action: Identify the javax import, rewrite to `import jakarta.validation.constraints.NotBlank;` and run verification.
    outcome: DTO validates correctly; no stale javax imports remain.

  - need: Project compiles but throws NoClassDefFoundError for javax.persistence.EntityManager at runtime.
    context: Source migrated but a third-party dependency still ships javax classes; or persistence.xml still references javax schema.
    action: Per the `check-non-java-configs` step, update `persistence.xml` and bump the offending dependency to its Jakarta-compatible version.
    outcome: Application boots cleanly; jakarta and javax namespaces no longer mixed.

anti_patterns:
  - Rewriting `javax.sql.*` or `javax.crypto.*` — these are JDK packages and stay on `javax.*`. The discovery and rewrite scripts deliberately exclude them; do not bypass that.
  - Skipping test sources. Test classes have entities, validation, and servlet imports too — run the scripts against the whole repo, not just `src/main`.
  - Forgetting `persistence.xml` and other XML configs. Source-only migration leaves mixed namespaces and runtime errors.
  - Migrating Java sources but leaving a dependency on a `javax.*`-only library version. Mixed namespaces cause ClassNotFoundException / NoClassDefFoundError at runtime.
  - Running the migration with a dirty working tree. The rewrite is mechanical but bulk; a clean tree makes the diff reviewable and the operation revertable.
  - Declaring success without running `scripts/verify_migration.sh`. A missed JPA entity won't fail compilation in some module layouts but will fail at runtime.
```

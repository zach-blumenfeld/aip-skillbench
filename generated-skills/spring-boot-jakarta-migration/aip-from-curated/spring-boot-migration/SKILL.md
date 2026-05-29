---
name: spring-boot-migration
description: Migrate Spring Boot 2.x applications to Spring Boot 3.x at the Maven build-config layer — bump spring-boot-starter-parent, set java.version to 17 or 21, strip deprecated javax.xml.bind/JAXB/activation dependencies, and upgrade monolithic jjwt 0.9.1 to the modular jjwt-api/jjwt-impl/jjwt-jackson trio. Use when updating pom.xml for Spring Boot 3, removing javax→jakarta-conflicting dependencies, upgrading Java for Spring Boot 3, planning the Spring Boot 2.7 → 3.x migration order, or driving an OpenRewrite Spring Boot 3 recipe. Hands source-code namespace, Spring Security, RestTemplate, and Hibernate migration off to sibling skills.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a3
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a3/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Migrate Spring Boot 2.x → 3.x at the Maven build-configuration layer.
  This skill owns pom.xml: the spring-boot-starter-parent version bump,
  java.version bump to 17 or 21, removal of deprecated javax/JAXB/activation
  dependencies that collide with Jakarta EE in Spring Boot 3, and the
  jjwt monolithic → modular upgrade. It also encodes the recommended
  Spring Boot 2.7 → 3.x migration order and provides an OpenRewrite path
  for the same outcome. Source-code namespace migration, Spring Security
  6 configuration, RestTemplate → RestClient, and Hibernate 6 specifics
  are delegated to sibling skills.

trigger_when:
  - User asks to upgrade a Spring Boot 2.x project to Spring Boot 3.x.
  - User mentions Spring Boot 3, Jakarta EE migration, or Java 17/21 for an existing Spring Boot app.
  - pom.xml has spring-boot-starter-parent at a 2.x version.
  - pom.xml has javax.xml.bind:jaxb-api, com.sun.xml.bind:jaxb-impl/jaxb-core, or javax.activation deps.
  - pom.xml has the monolithic io.jsonwebtoken:jjwt:0.9.1 artifact.
  - User asks how to use OpenRewrite to automate the Spring Boot 3 upgrade.
  - Build fails with ClassNotFoundException involving javax.xml.bind or split-package errors after a Spring Boot bump.

do_not_use_when:
  - Project uses Gradle (this skill targets Maven pom.xml).
  - Goal is only upgrading Java without changing Spring Boot version.
  - Application is already on Spring Boot 3.x and pom.xml is clean.
  - User wants source-code import migration only — defer to the jakarta-namespace skill.

scope_and_approval: >
  Scripts edit pom.xml in place. Stage the file in git (or back it up)
  before running migrate. The scripts do not run Maven, do not commit,
  and do not touch .java sources — the agent runs `mvn clean compile`
  and `mvn test` itself after migration. Other Spring Boot 3 surface
  area (source imports, Spring Security config, RestTemplate, Hibernate
  dialect/property changes) is handed off to sibling skills rather than
  performed here.

steps:
  - name: scan-pom
    description: >
      Inspect pom.xml and report its current state — Spring Boot parent
      version, java.version, deprecated JAXB/activation dependencies
      present, whether the old monolithic jjwt 0.9.1 is in use, whether
      Jakarta XML binding is already declared, whether the OpenRewrite
      plugin is installed. This is the read-only baseline for the rest
      of the procedure.
    script: scripts/pom_migrate.py
    inputs:
      - name: pom-path
        type: string
        description: Path to the project's pom.xml (root pom in a multi-module build).
    outputs:
      - name: scan-report
        type: object
        description: JSON with spring_boot_parent_version, java_version, deprecated_dependencies, jjwt_old_present, jjwt_modular_present, jakarta_xml_bind_present, openrewrite_plugin_present.

  - name: apply-pom-migrations
    description: >
      Apply deterministic edits to pom.xml in place. Default targets are
      Spring Boot 3.2.0, Java 21, jjwt 0.12.3 — override via flags when
      the project pins different versions. The script bumps the
      spring-boot-starter-parent <version>, sets <java.version>, strips
      every deprecated JAXB/activation dependency block, and swaps the
      monolithic jjwt for the modular trio when jjwt_old_present. Edits
      are regex-based so comments and existing indentation survive.
      Invocation - `python scripts/pom_migrate.py migrate <pom-path>
      [--target-spring-boot 3.2.0] [--target-java 21] [--jjwt-version 0.12.3]`.
    script: scripts/pom_migrate.py
    depends_on: [scan-pom]
    inputs:
      - name: pom-path
        type: string
      - name: target-spring-boot
        type: string
        nullable: true
        description: spring-boot-starter-parent target. Defaults to 3.2.0.
      - name: target-java
        type: string
        nullable: true
        description: java.version target. 17 or 21. Defaults to 21.
      - name: jjwt-version
        type: string
        nullable: true
        description: Modular jjwt version to use when upgrading. Defaults to 0.12.3.
    outputs:
      - name: migrate-report
        type: object
        description: JSON summarizing version changes and removed dependencies.

  - name: consider-jakarta-xml-binding
    description: >
      Judgment call — do NOT script. After apply-pom-migrations the
      project has no XML-binding dependencies declared. Search the
      source tree for direct JAXB usage (`@XmlRootElement`,
      `@XmlElement`, `JAXBContext`, `Marshaller`, `Unmarshaller`, or
      imports of `jakarta.xml.bind` / `javax.xml.bind`). If any are
      found, add jakarta.xml.bind:jakarta.xml.bind-api and
      org.glassfish.jaxb:jaxb-runtime to <dependencies>. If nothing in
      the source code uses JAXB directly, do not add them — Spring Boot
      3's transitive deps cover any framework usage. See
      search_shortcuts › "Jakarta XML binding (only if needed)" for the
      exact XML.
    depends_on: [apply-pom-migrations]

  - name: verify-pom
    description: >
      Re-scan pom.xml and report residual issues — parent still 2.x,
      java.version still below 17, deprecated JAXB/activation deps
      still present, old jjwt still present. Exits 0 with `clean: true`
      when the pom is on Spring Boot 3.x / Java 17+ with no deprecated
      deps; exits 1 with an `issues` list otherwise. Re-run after any
      manual edit until clean. Invocation -
      `python scripts/pom_migrate.py verify <pom-path>`.
    script: scripts/pom_migrate.py
    depends_on: [apply-pom-migrations, consider-jakarta-xml-binding]
    inputs:
      - name: pom-path
        type: string
    outputs:
      - name: verify-report
        type: object
        description: JSON with the latest scan plus an `issues` list and a `clean` flag.

  - name: compile-and-test
    description: >
      Run `mvn clean compile` and then `mvn test`. Compile errors after
      this skill's work are expected — they surface the source-code
      changes the sibling skills handle (javax→jakarta imports, Spring
      Security 6 config, RestTemplate → RestClient, Hibernate 6
      property renames). Treat the compile output as the to-do list for
      those skills; do NOT edit pom.xml again to suppress the errors.
    depends_on: [verify-pom]

  - name: hand-off-source-migration
    description: >
      Activate sibling skills in this order to finish the migration in
      source code - jakarta-namespace (javax.* → jakarta.* imports),
      spring-security-6 (SecurityFilterChain refactor and deprecated
      method removal), restclient-migration (RestTemplate → RestClient),
      hibernate-upgrade (Hibernate 6 dialect, property keys, sequence
      defaults). Run `mvn test` after the chain completes.
    depends_on: [compile-and-test]

modes:
  - name: scripted-manual
    body: >
      Default. Run scan-pom → apply-pom-migrations →
      consider-jakarta-xml-binding → verify-pom → compile-and-test →
      hand-off-source-migration. Surgical edits to pom.xml only, no
      Maven plugin to install, comments and formatting preserved.
      Choose this when the project is single-module or the agent needs
      tight control over which transforms run.
  - name: openrewrite
    body: |
      Bulk alternative — OpenRewrite covers Spring Boot version bump,
      javax.* → jakarta.* imports across all sources, several
      deprecated Spring Security patterns, and Boot property renames
      in one `mvn rewrite:run`. It does NOT swap the monolithic jjwt
      and does NOT always remove javax.activation deps, so still run
      verify-pom afterward.

      Prereq: bump <java.version> to 17 or 21 first (OpenRewrite
      recipes target Java 17+). Either run apply-pom-migrations with
      `--target-spring-boot` matching the project's current 2.x line
      (no-op for that field) just to update Java, or edit
      <java.version> by hand.

      Add this plugin inside <build><plugins>:

          <plugin>
            <groupId>org.openrewrite.maven</groupId>
            <artifactId>rewrite-maven-plugin</artifactId>
            <version>5.42.0</version>
            <configuration>
              <activeRecipes>
                <recipe>org.openrewrite.java.spring.boot3.UpgradeSpringBoot_3_2</recipe>
              </activeRecipes>
            </configuration>
            <dependencies>
              <dependency>
                <groupId>org.openrewrite.recipe</groupId>
                <artifactId>rewrite-spring</artifactId>
                <version>5.21.0</version>
              </dependency>
            </dependencies>
          </plugin>

      Then run `mvn rewrite:run`. Follow with verify-pom and
      compile-and-test.

search_shortcuts:
  - category: Migration Order
    body: |
      Least-disruptive → most-disruptive sequence:
        1. Land Spring Boot 2.7.x (the latest 2.x) if not there yet.
        2. Bump <java.version> to 17 or 21.
        3. Strip deprecated deps (javax.xml.bind, javax.activation, old jjwt).
        4. Bump spring-boot-starter-parent to 3.2.x.
        5. Migrate javax.* → jakarta.* imports (jakarta-namespace skill).
        6. Refactor Spring Security configuration (spring-security-6 skill).
        7. Replace RestTemplate with RestClient (restclient-migration skill).
        8. Run `mvn test` end-to-end.

  - category: Deprecated Dependencies to Remove
    body: |
      Hardcoded — strip every match from pom.xml regardless of project shape:
        - javax.xml.bind:jaxb-api
        - com.sun.xml.bind:jaxb-impl
        - com.sun.xml.bind:jaxb-core
        - javax.activation:activation
        - javax.activation:javax.activation-api
      Reason - they ship classes that collide with Jakarta EE's
      jakarta.xml.bind on the Spring Boot 3 classpath, producing
      ClassNotFoundException and split-package errors at runtime.

  - category: jjwt Migration
    body: |
      Old monolithic artifact - io.jsonwebtoken:jjwt:0.9.1.

      Replace with the modular trio (default version 0.12.3):
        - io.jsonwebtoken:jjwt-api          (compile)
        - io.jsonwebtoken:jjwt-impl         (runtime)
        - io.jsonwebtoken:jjwt-jackson      (runtime)

      The signing-key (`Keys.hmacShaKeyFor`) and parser builder
      (`Jwts.parserBuilder()` → `Jwts.parser()`) APIs changed between
      0.9.x and 0.11+. Call-site updates are NOT in scope for this
      skill — handle them in the source-code phase.

  - category: Jakarta XML binding (only if needed)
    body: |
      Add ONLY when source code uses JAXB types directly. Otherwise
      skip — Spring Boot 3's transitive deps cover framework use.

          <dependency>
            <groupId>jakarta.xml.bind</groupId>
            <artifactId>jakarta.xml.bind-api</artifactId>
          </dependency>
          <dependency>
            <groupId>org.glassfish.jaxb</groupId>
            <artifactId>jaxb-runtime</artifactId>
          </dependency>

  - category: Verification commands
    body: |
      After migration, sanity-check the pom and the build:

          # Should print 3.x version
          grep -A2 "spring-boot-starter-parent" pom.xml | grep version

          # Should print 17 or 21
          grep "java.version" pom.xml

          # All three should return NO matches
          grep "jaxb-api" pom.xml
          grep "javax\.xml\.bind" pom.xml
          grep "<version>0\.9\.1</version>" pom.xml

          # End-to-end
          mvn clean compile && mvn test

integrations:
  - partner: jakarta-namespace
    body: >
      After pom migration, `mvn clean compile` surfaces hundreds of
      javax.* import errors. jakarta-namespace rewrites those across
      .java sources. Activate it before spring-security-6 — the
      security skill assumes jakarta.servlet types are already in place.
  - partner: spring-security-6
    body: >
      Spring Security 6 (shipped with Spring Boot 3) drops
      WebSecurityConfigurerAdapter in favor of a SecurityFilterChain
      bean and renames several deprecated method signatures. Activate
      after jakarta-namespace.
  - partner: restclient-migration
    body: >
      Spring Framework 6.1 deprecates RestTemplate in favor of
      RestClient. Activate to migrate HTTP client call sites; can run
      in parallel with spring-security-6 since the surface areas are
      disjoint.
  - partner: hibernate-upgrade
    body: >
      Spring Boot 3 ships Hibernate 6 — dialect class auto-detection,
      property key changes (`spring.jpa.properties.hibernate.*`), and
      different sequence/identity generation defaults. Activate when
      JPA tests fail after the rest of the migration lands.

scenarios:
  - need: >
      Single-module Spring Boot 2.7.18 + Java 8 user-management service.
      pom.xml has javax.xml.bind:jaxb-api, com.sun.xml.bind:jaxb-impl,
      com.sun.xml.bind:jaxb-core, javax.activation:activation, and
      io.jsonwebtoken:jjwt:0.9.1. Goal is Spring Boot 3.2 + Java 21.
    context: >
      scan-pom reports spring_boot_parent_version=2.7.18, java_version=1.8,
      four deprecated deps, jjwt_old_present=true, jakarta_xml_bind_present=false.
      A grep across src/ shows no direct `javax.xml.bind` or `jakarta.xml.bind`
      imports — JAXB is not used by application code.
    action: >
      Run apply-pom-migrations with defaults (target-spring-boot=3.2.0,
      target-java=21, jjwt-version=0.12.3). Skip
      consider-jakarta-xml-binding — no source-code JAXB usage.
      verify-pom returns clean. compile-and-test surfaces ~140 javax.*
      import errors plus Spring Security config errors. Hand off to
      jakarta-namespace → spring-security-6 → restclient-migration.
    outcome: >
      pom.xml on Spring Boot 3.2.0, Java 21, deprecated deps gone,
      modular jjwt in place, comments preserved. Remaining work scoped
      to four sibling skills.

  - need: >
      Multi-module Maven build already on Spring Boot 2.7 + Java 11 with
      the old jjwt and old JAXB deps. Team wants minimum manual edits.
    context: >
      OpenRewrite is preferred because the namespace work spans many
      modules. Java is at 11; OpenRewrite Spring Boot 3 recipes need
      17+.
    action: >
      Pick `modes.openrewrite`. Run apply-pom-migrations with
      `--target-spring-boot 2.7.18 --target-java 21` (bumps Java,
      removes deprecated deps, swaps jjwt, leaves parent on 2.x for now).
      Add the rewrite-maven-plugin to each module pom. Run
      `mvn rewrite:run`. Run verify-pom on every module pom and
      compile-and-test from the reactor root.
    outcome: >
      OpenRewrite handles javax→jakarta imports and the Spring Boot
      3.x parent bump across modules. Manual cleanup is limited to
      jjwt call sites and any custom Spring Security config — the
      sibling skills pick that up.

anti_patterns:
  - Bumping spring-boot-starter-parent to 3.x before bumping java.version to 17+. Maven fails with a Java compatibility error before any Jakarta work surfaces.
  - Leaving javax.xml.bind:jaxb-api on the classpath alongside Spring Boot 3. The two namespaces share class names and produce ClassNotFoundException at runtime.
  - Adding jakarta.xml.bind-api and jaxb-runtime unconditionally. Only add them when application source uses JAXB types directly; otherwise Spring Boot's transitive deps cover it and the explicit declaration just creates upgrade churn.
  - Removing the monolithic jjwt without adding the modular replacements when source code calls JJWT APIs. The build will fail to compile and the agent will be tempted to add back the wrong artifact.
  - Hand-editing multi-line <dependency> blocks with sed. Multi-line sed across XML reliably corrupts the file; use scripts/pom_migrate.py instead.
  - Running OpenRewrite while the project is still on Java 8 or 11. The Spring Boot 3 recipes target Java 17+ and the plugin fails to load.
  - Treating org.hibernate.dialect.H2Dialect as having been renamed in Spring Boot 3. The class name is unchanged in Hibernate 6 — what changed is that the dialect is now auto-detected, so the explicit setting can usually be removed. This is hibernate-upgrade's territory, not this skill's.
  - Re-editing pom.xml after compile-and-test to silence javax→jakarta import errors. Those errors are the to-do list for jakarta-namespace; suppressing them in the pom defeats the migration.
```

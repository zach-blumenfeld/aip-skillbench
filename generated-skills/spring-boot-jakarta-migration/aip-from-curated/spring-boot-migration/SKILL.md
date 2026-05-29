---
name: spring-boot-migration
description: Migrate Spring Boot 2.x applications to Spring Boot 3.x. Use when updating pom.xml versions, removing deprecated JAXB dependencies, upgrading Java to 17/21, or using OpenRewrite for automated migration. Covers dependency updates, version changes, and migration checklist.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a2/assets/aip-schemas/procedure.schema.json
compatibility: Requires a Maven project (pom.xml), bash, grep/sed, and Maven on PATH. OpenRewrite mode requires network access for plugin/recipe download.
---

```yaml
purpose: >
  Migrate Spring Boot 2.x applications to Spring Boot 3.x — the most
  significant upgrade in Spring Boot history because of the Java EE →
  Jakarta EE namespace transition. The procedure bumps the parent POM
  version, moves Java to 17 or 21, deletes legacy javax.xml.bind /
  javax.activation / monolithic jjwt dependencies, optionally drives the
  whole upgrade through OpenRewrite, and verifies the resulting pom.xml
  before handing off to the Jakarta namespace rename and downstream
  Spring Security 6 / RestClient migrations.

trigger_when:
  - User asks to upgrade Spring Boot from 2.x to 3.x.
  - pom.xml references spring-boot-starter-parent 2.x and the target is 3.x.
  - User asks to bump Java to 17 or 21 in a Spring Boot project.
  - User mentions JAXB, javax.xml.bind, jakarta.xml.bind, or the namespace conflict.
  - User asks to replace monolithic io.jsonwebtoken:jjwt with the modular jjwt-api/impl/jackson trio.
  - User asks for an OpenRewrite-driven Spring Boot 3 upgrade.
  - Build fails after a Spring Boot 3 bump with ClassNotFoundException or namespace conflicts pointing at javax.*.

do_not_use_when:
  - The project is already on Spring Boot 3.x and only individual javax.* → jakarta.* renames remain — defer to the Jakarta Namespace skill instead.
  - The project is Gradle-based — the scripts in this skill assume Maven (pom.xml). The narrative still applies; the verification scripts do not.
  - The user only wants Spring Security 6 changes or RestTemplate → RestClient — defer to those dedicated skills.

scope_and_approval: >
  Default mode is write — sed-based pom.xml edits and OpenRewrite both
  modify files in place. Always commit or stash the working tree before
  running the version-bump script or `openrewrite_run.sh`. Manual XML
  edits (removing the JAXB dependency blocks, replacing the jjwt block)
  must be done with an editor or via OpenRewrite — sed is not safe for
  multi-line XML element deletion. Compile + test steps run unaltered
  Maven commands and only write to target/.

steps:
  - name: detect-current-state
    description: Inspect pom.xml to capture current Spring Boot version, java.version, and which legacy dependencies are still present. Output drives every downstream branch.
    script: scripts/detect_state.sh
    inputs:
      - name: pom_path
        type: string
        description: Path to the project pom.xml. Defaults to ./pom.xml.
    outputs:
      - name: state
        type: object
        description: JSON object with spring_boot_version, java_version, has_jaxb_api, has_jaxb_impl_or_core, has_javax_activation, has_old_monolithic_jjwt, has_modular_jjwt, has_openrewrite_plugin.
  - name: pick-target-versions
    description: Decide target Spring Boot patch (default 3.2.0) and target Java version (17 or 21; prefer 21 for new work). If the project is on a 2.x line older than 2.7, first bump to 2.7.x in a separate pass before continuing — see references/common-issues.md § Recommended migration order.
    inputs:
      - name: state
        type: object
    outputs:
      - name: target_spring_boot
        type: string
      - name: target_java
        type: string
  - name: choose-execution-mode
    description: Select automated (OpenRewrite drives the whole upgrade) or manual (step-by-step sed + editor). See top-level `modes`. OpenRewrite also rewrites javax → jakarta imports, which the manual path defers to the Jakarta Namespace skill.
    one_of:
      - automated-openrewrite
      - manual-step-by-step
    inputs:
      - name: state
        type: object
    outputs:
      - name: mode
        type: string
  - name: update-spring-boot-parent
    description: Bump the spring-boot-starter-parent version. Safe sed bump only covers 2.7.x → target. For older 2.x lines, upgrade to 2.7.x first (per `pick-target-versions`). See references/pom-snippets.md § 1 for the canonical before/after XML.
    script: scripts/update_pom_versions.sh
    inputs:
      - name: pom_path
        type: string
      - name: target_spring_boot
        type: string
      - name: target_java
        type: string
    outputs:
      - name: pom_updated
        type: boolean
  - name: update-java-version
    description: Set <java.version> to 17 or 21. Folded into the same script as the parent bump — both substitutions run in one invocation. See references/pom-snippets.md § 2.
    depends_on:
      - update-spring-boot-parent
  - name: remove-legacy-deps
    description: >
      Delete the legacy javax.xml.bind / javax.activation / monolithic
      jjwt dependency blocks from pom.xml. This is a multi-line XML edit
      — sed cannot do it safely, so the agent must edit the file
      directly (or rely on OpenRewrite in automated mode). Use
      `scripts/check_jaxb_removal.sh` to locate the exact line ranges
      and to confirm clean removal. The blocks to delete and the
      Jakarta replacements (only if XML binding is actually used) are
      in references/pom-snippets.md § 3.
    script: scripts/check_jaxb_removal.sh
    inputs:
      - name: pom_path
        type: string
    outputs:
      - name: legacy_deps_clean
        type: boolean
  - name: update-jwt
    description: Replace any monolithic <artifactId>jjwt</artifactId> block with the modular jjwt-api / jjwt-impl / jjwt-jackson trio at version 0.12.3. Multi-line XML — edit by hand. Canonical snippet in references/pom-snippets.md § 4.
    inputs:
      - name: state
        type: object
  - name: run-openrewrite
    description: When `choose-execution-mode` selected automated, invoke the OpenRewrite UpgradeSpringBoot_3_2 recipe. This also rewrites javax.* → jakarta.* imports across the whole tree, replacing the dedicated `fix-namespace-imports` handoff for the automated path.
    script: scripts/openrewrite_run.sh
    depends_on:
      - choose-execution-mode
    inputs:
      - name: mode
        type: string
      - name: pom_dir
        type: string
    outputs:
      - name: openrewrite_applied
        type: boolean
  - name: fix-namespace-imports
    description: For the manual path, rename every javax.* import to its jakarta.* equivalent across src/. Defer to the Jakarta Namespace skill — see integrations. Skip this step when `run-openrewrite` already ran in automated mode (it performs the same rewrite).
    depends_on:
      - update-spring-boot-parent
  - name: verify-pom
    description: Run the post-migration pom.xml gate. Confirms parent is 3.x, java.version is 17/21, no legacy javax.* / monolithic jjwt remains. Re-run after any manual edit.
    script: scripts/verify_migration.sh
    inputs:
      - name: pom_path
        type: string
    outputs:
      - name: pom_clean
        type: boolean
  - name: compile-and-test
    description: Run `mvn clean compile` to surface remaining compilation errors (most will be unresolved javax.* imports — route them back through `fix-namespace-imports`). Then `mvn test` to confirm functional equivalence.
    depends_on:
      - verify-pom

modes:
  - name: automated-openrewrite
    body: >
      Drive the whole upgrade through `org.openrewrite.java.spring.boot3.UpgradeSpringBoot_3_2`.
      The recipe bumps the parent version, rewrites javax.* → jakarta.*,
      updates deprecated Spring Security patterns, and fixes property
      name changes. Invoke via `scripts/openrewrite_run.sh` (transient
      Maven invocation, no permanent pom edit) or by adding the plugin
      block from references/pom-snippets.md § 5 and running
      `mvn rewrite:run`. After the recipe completes, still run
      `verify-pom` and `compile-and-test` — OpenRewrite is not infallible
      on bespoke security configs.
  - name: manual-step-by-step
    body: >
      Run `update_pom_versions.sh` for the version bumps, then hand-edit
      pom.xml to delete the JAXB blocks and rewrite the jjwt block
      (using references/pom-snippets.md). After the pom is clean, hand
      off the namespace rename to the Jakarta Namespace skill, then
      compile and test. Use this path when the project has non-standard
      build plugins or hand-rolled Spring Security configs that the
      OpenRewrite recipe is known to misrewrite.

integrations:
  - partner: Jakarta Namespace skill
    body: >
      Owns the bulk javax.* → jakarta.* rename across src/. Invoke after
      `update-spring-boot-parent` on the manual path. Skipped on the
      automated-openrewrite path because the OpenRewrite recipe performs
      the same rewrite.
  - partner: Spring Security 6 skill
    body: >
      Spring Security configuration patterns changed in 6.x — `WebSecurityConfigurerAdapter`
      is removed, `authorizeRequests` is replaced by `authorizeHttpRequests`, etc.
      Hand off after `verify-pom` and before `compile-and-test` whenever
      the project carries a custom `SecurityConfig` or `WebSecurityConfigurerAdapter`.
  - partner: RestClient Migration skill
    body: >
      Spring Boot 3.2 introduces `RestClient` as the modern replacement
      for `RestTemplate`. Hand off after the rest of the migration is
      green; not a blocker for the Spring Boot 3 build.

scenarios:
  - need: Spring Boot 2.7.18 app on Java 11 with jaxb-api and monolithic jjwt 0.9.1; user wants Spring Boot 3.2 on Java 21.
    context: >
      `detect_state.sh` reports
      spring_boot_version=2.7.18, java_version=11, has_jaxb_api=true,
      has_old_monolithic_jjwt=true, has_openrewrite_plugin=false.
    action: >
      Picked automated-openrewrite mode (clean project, no custom security
      config). Ran `openrewrite_run.sh` with the default UpgradeSpringBoot_3_2
      recipe. Ran `check_jaxb_removal.sh` — clean. Hand-edited the jjwt
      block per references/pom-snippets.md § 4 (recipe does not handle
      this). Ran `verify_migration.sh` (all PASS) then `mvn clean compile`
      and `mvn test`.
    outcome: Build green on Spring Boot 3.2.0 / Java 21; modular jjwt active; no javax.* remaining.
  - need: Same project, but with a hand-rolled WebSecurityConfigurerAdapter and bespoke Maven plugins.
    context: detect_state.sh reports same legacy versions but the security config is non-standard.
    action: >
      Picked manual-step-by-step mode. Ran `update_pom_versions.sh pom.xml
      3.2.0 21`. Hand-deleted the JAXB and jjwt blocks; pasted the modular
      jjwt block from references/pom-snippets.md § 4. Handed off to the
      Jakarta Namespace skill for the rename, then to the Spring Security 6
      skill for the config rewrite. Re-ran `verify_migration.sh`, then
      `mvn clean compile` and `mvn test`.
    outcome: Build green without OpenRewrite touching the bespoke security wiring.

anti_patterns:
  - Leaving javax.xml.bind:jaxb-api on the classpath alongside jakarta.xml.bind — produces ClassNotFoundException at runtime even when the build appears clean.
  - Bumping the spring-boot-starter-parent to 3.x without bumping java.version to 17 or 21 — Spring Boot 3 refuses to start on Java 11 or earlier.
  - Skipping a separate 2.x → 2.7.x bump when the project is on 2.5 or 2.6 — the safe-sed bump in `update_pom_versions.sh` only targets 2.7.x.
  - Using sed to delete the multi-line JAXB <dependency> blocks — sed mangles cross-line XML; edit by hand or rely on OpenRewrite.
  - Treating compile success as migration success — run `verify_migration.sh` and `mvn test`; runtime ClassNotFoundException for old JAXB only fires when an XML binding code path executes.
  - Adding `jakarta.xml.bind-api` and `jaxb-runtime` "just in case" — Spring Boot 3 brings them transitively when needed; adding them eagerly produces classpath duplication warnings.
```

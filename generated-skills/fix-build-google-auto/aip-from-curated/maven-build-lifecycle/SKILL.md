---
name: maven-build-lifecycle
description: Diagnose, configure, and run Maven builds for Java projects — pick the right phase or goal, navigate the default/clean/site lifecycles, activate profiles, configure Surefire/Failsafe tests, tune multi-module reactors, and debug failures with -X, dependency:tree, and help:effective-pom. Use when working with Maven build phases, goals, profiles, or customizing the build process for Java projects.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a3
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a3/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Drive Maven builds end-to-end for Java projects — choose the right
  phase or goal, navigate the default / clean / site lifecycles,
  activate the right profile, configure unit vs integration tests via
  Surefire/Failsafe, orchestrate multi-module reactors, and debug
  failures with verbose mode, effective-POM, and dependency analysis.
  Reference content (full phase lists, profile XML, plugin config XML)
  is bundled under references/ and loaded on demand rather than carried
  in the body on every invocation.

trigger_when:
  - Diagnosing a failing Maven build (mvn clean install, mvn package, mvn verify).
  - Choosing which Maven phase or goal to run for a given task.
  - Defining, configuring, or activating a build profile (env, OS, JDK, CI).
  - Customizing the build (source/target version, output dirs, finalName).
  - Configuring resource filtering or property substitution.
  - Splitting unit vs integration tests across Surefire and Failsafe.
  - Tuning multi-module builds (reactor -pl/-am/-amd/-rf, parallel -T).
  - Optimizing build speed (parallel, incremental, build cache, mvnd).
  - Setting up CI/CD pipelines that run Maven (GitHub Actions, Jenkins).

do_not_use_when:
  - Resolving the dependency-version or BOM conflicts themselves (use maven-dependency-management).
  - Authoring or wiring a brand-new Maven plugin's configuration block (use maven-plugin-configuration).
  - The build tool is not Maven (Gradle, Bazel, Ant — different lifecycle model).

steps:
  - name: classify-need
    description: >
      Read the user's request or the failing build output and decide
      which category of Maven work this is — debug-failure, run-phase,
      customize-build, configure-profile, configure-tests, multi-module,
      optimize, or ci-cd. The category drives which reference to load
      next and which downstream steps apply.
    outputs:
      - name: need-category
        type: string
        description: One of debug-failure, run-phase, customize-build, configure-profile, configure-tests, multi-module, optimize, ci-cd.

  - name: load-relevant-references
    description: >
      Read only the reference files matching the need. Map:
      debug-failure → references/debugging-and-optimization.md +
      references/lifecycle-phases-and-goals.md;
      run-phase → references/lifecycle-phases-and-goals.md;
      customize-build → references/build-customization.md;
      configure-profile → references/profiles.md;
      configure-tests → references/test-configuration.md;
      multi-module → references/multi-module-builds.md;
      optimize → references/debugging-and-optimization.md;
      ci-cd → references/ci-cd-integration.md.
      Do not guess Maven flags or XML — load the reference.
    depends_on:
      - classify-need
    inputs:
      - name: need-category
        type: string
    outputs:
      - name: reference-content
        type: string

  - name: identify-failing-phase
    description: >
      When debugging a failure, scan the build output for the last
      `--- plugin:goal (execution-id) @ module ---` header before
      `[ERROR] BUILD FAILURE`. That is the failing goal; the phase it
      is bound to in the default lifecycle is the failing phase. Map
      the goal back via references/lifecycle-phases-and-goals.md
      (phase-to-goal bindings). Note the module in multi-module
      reactors — the failing phase in one module is unrelated to phases
      already completed in earlier reactor modules.
    depends_on:
      - load-relevant-references
    outputs:
      - name: failing-phase
        type: string
      - name: failing-goal
        type: string
      - name: failing-module
        type: string
        nullable: true

  - name: pick-debug-strategy
    description: >
      Choose the smallest probe that surfaces root cause before editing
      files. Compilation / class-resolution errors → re-run with `-X`
      for full stacktrace and `mvn dependency:tree` to expose
      transitive conflicts. Surprising plugin/config behavior →
      `mvn help:effective-pom` to see resolved config after inheritance
      and profile activation. Surprising profile selection →
      `mvn help:active-profiles` (remember `activeByDefault=true`
      profiles deactivate as soon as ANY `-P` flag is passed). Failing
      only on CI → reproduce locally with the same `-P<ci-profile>`
      flag, since the CI profile may toggle Failsafe or set different
      compiler flags.
    depends_on:
      - identify-failing-phase
    inputs:
      - name: failing-phase
        type: string
      - name: failing-goal
        type: string
    outputs:
      - name: debug-commands
        type: list[string]

  - name: propose-fix
    description: >
      Form the fix as a concrete change with the minimum diff. Decide
      whether the change is in source, in pom.xml (plugin version,
      configuration, profile, resource filter), in invocation flags
      (e.g. add `-am`, switch `test` → `verify`), or in environment
      (missing JDK version, missing system property). When the task
      workflow requires writing a patch file, capture the change as a
      unified diff and apply it.
    depends_on:
      - pick-debug-strategy
    outputs:
      - name: fix-plan
        type: object

  - name: verify
    description: >
      Re-run the original Maven command (commonly `mvn clean install`
      or whatever the task specifies) and confirm the previously
      failing phase now passes AND no earlier phase regressed. Do NOT
      add `-DskipTests` or `-Dmaven.test.skip=true` to make verification
      green — a build that passes only because tests were skipped is
      not a real fix unless the task explicitly demands it. For
      multi-module fixes, verify with the full reactor (`mvn install`
      from the parent), not just the failing module in isolation.
    depends_on:
      - propose-fix
    outputs:
      - name: build-result
        type: object

search_shortcuts:
  - category: Lifecycle quick reference
    body: >
      Default lifecycle key phases in order: validate → compile →
      test-compile → test → package → integration-test → verify →
      install → deploy. Clean lifecycle: clean. Site lifecycle: site,
      site-deploy. Full phase list in
      references/lifecycle-phases-and-goals.md.

  - category: Most-used commands
    body: |
      mvn clean install              — clean build, install to local repo
      mvn verify                     — full build through integration-test + verify
      mvn package                    — compile + test + build JAR/WAR
      mvn compile                    — compile only (no tests)
      mvn test                       — Surefire unit tests only (NOT Failsafe)
      mvn deploy                     — install + push to remote repo
      mvn dependency:tree            — inspect dependency graph
      mvn help:effective-pom         — resolved POM after inheritance + profiles
      mvn help:active-profiles       — which profiles actually activated
      mvn versions:display-plugin-updates  — plugin update report
      mvn versions:display-dependency-updates  — dependency update report

  - category: Debug flags
    body: |
      -X       debug logging (very verbose; includes plugin classpath, dependency resolution)
      -e       full error stacktrace
      -q       quiet mode (errors and summary only)
      -B       batch mode (no interactive prompts, no progress noise) — required in CI
      -ff      fail fast in reactor (first module failure stops the reactor)
      -o       offline mode

  - category: Reactor flags
    body: |
      -pl <module>          build only this module
      -pl <module> -am      also-make: build this module + every module it depends on
      -pl <module> -amd     also-make-dependents: build this module + every module that depends on it
      -rf :<module>         resume from this module after a failure
      -T 4                  4 worker threads
      -T 1C                 1 thread per CPU core

  - category: Profile flags
    body: |
      -Pname                activate profile `name`
      -Pa,b,c               activate multiple profiles
      -P!name               deactivate profile `name`
      -PactivebyDefault     `activeByDefault=true` profiles auto-deactivate when ANY -P flag is present

  - category: Skip flags
    body: |
      -DskipTests           skip test execution but still compile tests
      -Dmaven.test.skip=true  skip test compilation AND execution (also skips Failsafe)
      -DskipUnitTests       skip Surefire only (used with -P profile gating)

anti_patterns:
  - Skipping tests (-DskipTests, -Dmaven.test.skip=true) to make a build pass when the task is to fix the underlying failure. A green-because-skipped build is not a fix.
  - Running `mvn install` when only `mvn compile` is needed — wastes time chasing test/package failures unrelated to the user's question.
  - Editing source to "fix" what is actually a profile activation problem (and vice versa). Always confirm with `mvn help:effective-pom` and `mvn help:active-profiles` before editing pom.xml or .java files.
  - Forgetting `mvn clean` when stale target/ artifacts are masking the real state — especially after switching branches or changing plugin versions.
  - Leaving `-SNAPSHOT` versions in a release build.
  - Setting `<filtering>true</filtering>` on a wildcard resource block — Maven attempts UTF-8 substitution and corrupts binaries (images, keystores, fonts).
  - Treating Surefire and Failsafe as interchangeable. Surefire runs in `test`; Failsafe in `integration-test` + `verify`. Running `mvn test` never invokes Failsafe.
  - Building only one module when downstream modules depend on it — use `-pl X -am` (also-make) to pull in upstream deps, or `-pl X -amd` (also-make-dependents) when verifying that shared changes don't break consumers.
  - Running `mvn -T <n>` (parallel) on a build with non-thread-safe plugins — surfaces as flaky, non-deterministic failures.
  - Letting `activeByDefault=true` profiles silently deactivate. The moment any `-P` flag is present, ALL `activeByDefault` profiles turn off — re-activate explicitly with `mvn install -Pproduction,development`.
  - Pinning some plugin versions and inheriting others. Lock every plugin version in `<pluginManagement>` for reproducible builds — Maven's default plugin version can change between Maven releases.

scenarios:
  - need: Build fails with BUILD FAILURE during the `compile` phase, complaining about a missing symbol from a sibling module.
    context: >
      Multi-module Maven project. The failing module depends on a
      sibling module whose latest code is not in the local repo because
      the agent ran `mvn compile -pl failing-module` (no -am). The
      sibling never rebuilt, so its target/classes is stale or absent.
    action: >
      Identify the failing phase (compile) and goal (compiler:compile).
      Re-run with reactor also-make: `mvn install -pl failing-module
      -am`. Confirm with `mvn dependency:tree -pl failing-module` that
      the sibling resolves to the just-built version.
    outcome: Build passes. Root cause was reactor scope, not source code — no source edit needed.

  - need: Integration test fails locally with `mvn test` but the CI pipeline catches it earlier.
    context: >
      The test is named `*IntegrationTest` and was meant to run under
      Failsafe at the `integration-test` / `verify` phase. The agent
      invoked `mvn test`, which only runs Surefire — the integration
      test never executed. CI runs `mvn verify`, which is why it
      surfaces there.
    action: >
      Read references/test-configuration.md. Confirm Failsafe is bound
      to `integration-test` and `verify` via its `<executions>` block.
      Locally reproduce with `mvn verify` instead of `mvn test`. If the
      naming convention is mixed, align tests to Failsafe's `*IT.java`
      / `*IntegrationTest.java` patterns OR widen the `<includes>` in
      the Failsafe configuration.
    outcome: Local invocation now mirrors CI. The integration test runs in the right plugin.

  - need: User asks to add a `production` profile that disables integration tests and enables optimized compilation.
    context: >
      Existing pom.xml has a `development` profile with `activeByDefault=true`
      that sets `skip.integration.tests=true`.
    action: >
      Read references/profiles.md. Add a `<profile id="production">`
      that overrides `skip.integration.tests=false` and configures
      maven-compiler-plugin with `<optimize>true</optimize>`,
      `<debug>false</debug>`. Document the invocation:
      `mvn install -Pproduction,!development` — the `!development`
      is required because the default-active profile would otherwise
      keep running alongside `production` and re-enable
      `skip.integration.tests`.
    outcome: >
      `mvn install -Pproduction,!development` produces an optimized
      build with integration tests enabled. `mvn help:active-profiles`
      confirms only `production` is active.
```

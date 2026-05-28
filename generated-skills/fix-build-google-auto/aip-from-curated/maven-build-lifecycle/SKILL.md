---
name: maven-build-lifecycle
description: Use when working with Maven build phases, goals, profiles, or customizing the build process for Java projects. Drives the lifecycle-aware workflow for diagnosing and repairing Maven build failures — locate the failing phase, pull the resolved POM and active profiles, classify the failure, and apply the targeted fix. Pairs with maven-dependency-management and maven-plugin-configuration on the same task.
license: Apache-2.0
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a2/assets/aip-schemas/procedure.schema.json
  aip-conversion: zach-blumenfeld
compatibility: Requires `mvn` (Maven 3.6+) on PATH and Python 3.8+ for the phase-lookup helper.
---

```yaml
purpose: >
  Drive Maven's three lifecycles (default, clean, site) as a single
  diagnostic workflow for Java build repair. Locate the failing phase on
  the ordered lifecycle, resolve the effective POM and active profiles,
  classify the failure (compile / test / profile / plugin / resource /
  multi-module / dependency), and apply the smallest targeted fix —
  pom.xml edit, command-line flag change, or source edit. Lifecycle
  knowledge lets the agent skip every phase before the failing one
  (those passed), focus on the named phase plus the plugin bound to it,
  and avoid blunt fixes like `-Dmaven.test.skip=true` that mask the
  underlying problem.

trigger_when:
  - A Maven build (`mvn ...`) fails and the failing phase or plugin needs to be identified.
  - The agent is asked to set up, customize, or optimize a Maven build.
  - Tests pass locally but fail in CI (or vice versa) — typically a profile / property delta.
  - A multi-module reactor build is failing and the agent needs `-pl` / `-am` / `-rf` to make progress.
  - User mentions Maven phases, goals, profiles, Surefire, Failsafe, effective-pom, or build lifecycle.
  - Working on the `fix-build-google-auto` style task — diagnose a failing Java build inside a BugSwarm-style sandbox and write a patch.

do_not_use_when:
  - The build tool is Gradle, sbt, Bazel, or anything other than Maven.
  - The failure is purely a missing/conflicting dependency version — defer to `maven-dependency-management` (lifecycle knowledge still applies, but dependency-management owns the resolution rules).
  - The failure is a misconfigured plugin (parameters, executions, phase binding) with no lifecycle ambiguity — defer to `maven-plugin-configuration`.

scope_and_approval: >
  Read-only diagnostics (`mvn help:*`, `mvn dependency:tree`, `mvn -X`,
  `scripts/diagnose_build.sh`, `scripts/lookup_phase.py`) need no
  approval — they only read the POM and write to a diagnostics
  directory under the project. Write actions — editing `pom.xml`,
  editing Java/test sources, writing patch files, applying patches with
  `git apply` / `patch` — should follow the host task's instructions
  (for build-repair tasks the patch path is dictated by
  `instruction.md`).

steps:
  - name: locate-failing-phase
    description: >
      Read the raw `mvn` failure output and extract the failing phase
      and the plugin/goal bound to it. Look for the line starting with
      `[ERROR] Failed to execute goal …:<goal>` and the preceding
      `[INFO] --- <plugin>:<version>:<goal> (id) @ <module> ---`.
      Then resolve the phase's position on its lifecycle by running
      `scripts/lookup_phase.py <phase> --before`. Every phase listed in
      `runs_before_it` already succeeded — the fix lives in the failing
      phase or its plugin binding, not earlier.
    script: scripts/lookup_phase.py
    inputs:
      - name: build-log
        type: string
        description: stdout/stderr from the failing `mvn` invocation.
    outputs:
      - name: failure-locus
        type: object
        description: '{phase, lifecycle, position, plugin, goal, module, runs_before_it}'

  - name: resolve-effective-config
    description: >
      Run the read-only diagnostic sequence (effective POM, effective
      settings, active profiles, dependency tree, dependency analyze,
      clean compile, and on success, test). `scripts/diagnose_build.sh`
      bundles these into one call and writes each command's output to a
      named file plus an `index.log`. Pass any profile flags from the
      failing build (`-Pci`, `-P!development`, …) via `-- -Pci`, so the
      resolution matches the failing context. Read `index.log` first,
      then the file matching the failing phase from
      `locate-failing-phase`.
    depends_on: [locate-failing-phase]
    script: scripts/diagnose_build.sh
    inputs:
      - name: project-dir
        type: string
      - name: profile-flags
        type: list[string]
        nullable: true
        description: e.g. ["-Pci", "-DskipITs"] — extra args to mirror the failing invocation.
    outputs:
      - name: diagnostics-dir
        type: string
        description: path containing index.log + per-command output files.

  - name: classify-failure
    description: >
      Pick the failure category from the failing phase and the
      diagnostics output. Load the matching reference for category
      details — do not load all of them.

      - phases 7 (`compile`) or 13 (`test-compile`) →
        `references/lifecycle-phases.md` (phase semantics) plus
        `references/resources-and-customization.md` (source/target/encoding).
      - phase 15 (`test`) or 19 (`integration-test`) or 21 (`verify`) →
        `references/test-and-package.md` (Surefire / Failsafe specifics,
        skip-option semantics).
      - phase 17 (`package`) failure on shade/assembly/war plugins →
        `references/test-and-package.md` § Packaging gotchas.
      - active-profile mismatch surfaced by `mvn help:active-profiles`
        differing from expectation → `references/profiles.md`.
      - multi-module build needing `-pl` / `-am` / `-rf`, or modules
        building in the wrong order → `references/multi-module-and-optimization.md`.
      - resource filtering corrupting binaries or substituting wrong
        values → `references/resources-and-customization.md`.
      - the failure is opaque and needs more depth than `-e` →
        `references/debugging-and-ci.md` (then re-run with `-X` and the
        relevant `help:` command).
    depends_on: [locate-failing-phase, resolve-effective-config]
    one_of:
      - compile-or-test-compile
      - test-or-integration-test
      - packaging-step
      - profile-misactivation
      - reactor-or-multi-module
      - resource-filtering
      - opaque-needs-deeper-debug
    inputs:
      - name: failure-locus
        type: object
      - name: diagnostics-dir
        type: string
    outputs:
      - name: category
        type: string
      - name: reference-file
        type: string

  - name: plan-fix
    description: >
      Synthesize the smallest fix that addresses the classified cause.
      Default to fixing the underlying issue rather than skipping
      around it — `-DskipTests` and `-Dmaven.test.skip=true` are
      diagnostic tools, not fixes. Use them only when the host task
      explicitly says so. The fix is one of: edit `pom.xml` (plugin
      version, source/target, profile activation, resource filter
      include/exclude), edit a Java source or test file, or change the
      `mvn` invocation (add `-pl`/`-am`/`-rf`, switch profile, set a
      property). Write the plan out before producing diffs — host tasks
      such as `fix-build-google-auto` require a `failed_reasons.txt`
      analysis file at a fixed path before any patch is applied.
    depends_on: [classify-failure]
    inputs:
      - name: category
        type: string
      - name: reference-file
        type: string
      - name: failure-locus
        type: object
    outputs:
      - name: fix-plan
        type: object
        description: '{root_cause, files_to_change, mvn_invocation_change, rationale}'

  - name: apply-fix
    description: >
      Produce the patch in the format the host task demands
      (standard unified diff for `fix-build-google-auto`; in-place edits
      for interactive sessions). Keep the diff minimal — touching only
      the lines necessary to fix the failing phase. If the task spec
      mandates a path like `patch_{i}.diff` under the repo root, write
      to that path. Then apply with `git apply` (preferred — preserves
      attribution and detects conflicts) or `patch -p1` (fallback when
      the repo is not a git checkout).
    depends_on: [plan-fix]
    inputs:
      - name: fix-plan
        type: object
    outputs:
      - name: patch-paths
        type: list[string]

  - name: verify-fix
    description: >
      Re-run the same `mvn` invocation that originally failed
      (including the same profile flags). For build-repair tasks, the
      grading verifier runs the full build — so success at the
      originally-failing phase is necessary but not sufficient; if the
      verifier compiles the whole project, run `mvn -B clean verify`
      (or `install`) to confirm later phases also pass. If a later
      phase now fails, loop back to `locate-failing-phase` with the new
      log.
    depends_on: [apply-fix]
    inputs:
      - name: patch-paths
        type: list[string]
      - name: failure-locus
        type: object
    outputs:
      - name: build-passed
        type: boolean
      - name: new-failure-log
        type: string
        nullable: true

search_shortcuts:
  - category: Diagnostic commands
    body: >
      `mvn -B -e <phase>` for stack traces; `mvn -X <phase>` for full
      debug; `mvn help:effective-pom`, `mvn help:effective-settings`,
      `mvn help:active-profiles`, `mvn help:evaluate
      -Dexpression=<prop>`, `mvn help:describe -Dplugin=<id> -Ddetail`.

  - category: Dependency inspection
    body: >
      `mvn dependency:tree -Dverbose -Dincludes=<group>`,
      `mvn dependency:analyze`, `mvn dependency:resolve`,
      `mvn versions:display-plugin-updates`,
      `mvn versions:display-dependency-updates`.

  - category: Reactor control
    body: >
      `-pl <module>` (only this module), `-am` (also-make: build deps),
      `-amd` (also-make-dependents), `-rf :<module>` (resume from
      module), `-T 1C` (one thread per core), `-fae` / `-ff`
      (fail-at-end / fail-fast).

  - category: Skip switches — diagnostic only
    body: >
      `-DskipTests` (compile tests but don't run),
      `-Dmaven.test.skip=true` (also skip test-compile),
      `-Dtest=ClassName#method` (run a single test).

  - category: Profile activation
    body: >
      `-P<name>` (activate), `-P!<name>` (deactivate); auto-activation
      via `<jdk>`, `<os>`, `<property>`, `<file>` in `<activation>`.

integrations:
  - partner: maven-dependency-management
    body: >
      When `classify-failure` lands on a `NoClassDefFoundError`,
      `NoSuchMethodError`, version-conflict note in
      `dependency-tree.txt`, or `dependency:analyze` flags
      used-undeclared / unused-declared, hand off to
      `maven-dependency-management` for resolution rules
      (`<dependencyManagement>`, `<exclusions>`, version pinning). Stay
      driving the lifecycle workflow — the dependency skill informs
      `plan-fix`.

  - partner: maven-plugin-configuration
    body: >
      When the failure is a plugin parameter, plugin execution binding,
      or plugin-version mismatch (rather than the phase order itself),
      defer the `<plugin>` block edit to
      `maven-plugin-configuration`. This skill still owns the phase
      identification and the verify step.

  - partner: fix-build-google-auto (host task)
    body: >
      The task instruction requires `failed_reasons.txt` before
      patches and `patch_{i}.diff` files in standard unified-diff
      format. Write `failed_reasons.txt` at the end of `plan-fix`;
      write `patch_{i}.diff` files at the start of `apply-fix`.

scenarios:
  - need: Build fails at `mvn install` with `[ERROR] Failed to execute goal org.apache.maven.plugins:maven-compiler-plugin:3.8.1:compile`.
    context: >
      `lookup_phase.py compile --before` confirms phases 1–6 passed.
      `diagnose_build.sh` writes `effective-pom.txt`; grepping for
      `<source>` shows the parent declares 17 but the failing module
      inherits 8 from a `<pluginManagement>` block.
    action: >
      Edit the module's `pom.xml` to set
      `<maven.compiler.source>17</maven.compiler.source>` and
      `<maven.compiler.target>17</maven.compiler.target>`. Write the
      change as `patch_1.diff`, apply with `git apply patch_1.diff`,
      and re-run `mvn -B clean compile`.
    outcome: Compile passes; full `mvn -B clean verify` then succeeds.

  - need: CI build fails on `mvn -B install -Pci`; same command passes locally.
    context: >
      `mvn help:active-profiles -Pci` in CI shows `ci` plus `production`;
      locally it shows `ci` plus `development`. The `production` profile
      enables a Failsafe execution missing a test resource.
    action: >
      Either move the missing test resource under the path the profile
      expects, or convert the profile's activation to a property-driven
      switch so it doesn't auto-fire when `env.CI` is set. Patch the
      narrower of the two.
    outcome: CI build passes; local build unchanged.

  - need: Multi-module reactor fails on module `service` after `common` and `api` succeed.
    context: >
      `dependency-tree.txt` for `service` lists `api:1.2-SNAPSHOT` but
      `effective-pom.txt` for `api` shows `1.3-SNAPSHOT`. `common` and
      `api` are already installed in the local repo from the partial
      build.
    action: >
      Align the `<version>` in `service/pom.xml` (or the parent
      `<dependencyManagement>`) to `1.3-SNAPSHOT`. Resume with
      `mvn -B install -rf :service` to avoid rebuilding `common` and
      `api`.
    outcome: Reactor completes; the cross-module version drift is gone.

  - need: Test phase fails with a single flaky integration test blocking the build.
    context: >
      The host task is build-repair, not test-stability triage. The
      failure is in the Failsafe-bound phase `verify`, not in real
      product code. Skipping it the wrong way (`-Dmaven.test.skip=true`)
      would also skip unit test compilation.
    action: >
      Use `-DskipITs` (Failsafe's own switch) to skip only integration
      tests, or `-Dit.test=!FlakyIT` to exclude the single class. Reach
      for these only when the host task explicitly permits skipping;
      otherwise fix the test.
    outcome: >
      Unit tests still compile and run; the flaky IT is excluded with a
      narrow switch instead of a blanket skip.

anti_patterns:
  - Reaching for `-Dmaven.test.skip=true` to "fix" a build before diagnosing — it also skips `test-compile`, so a broken test file silently masks itself.
  - Editing `pom.xml` from memory of `<source>17</source>` etc. instead of reading `mvn help:effective-pom` — profile inheritance and `<pluginManagement>` routinely override what the raw file shows.
  - Re-running `mvn install` from the top of a multi-module build after a single module fails. Use `mvn install -rf :failed-module` to resume.
  - Assuming a `package`-phase failure is in source code. Phase 17 runs after `test` (15); failures here are usually shade/assembly/war plugin configuration.
  - "Treating profile auto-activation (`activeByDefault: true`) as guaranteed. Naming any other profile on `-P` deactivates the default set."
  - Filtering binary resources. Maven rewrites `${...}` tokens inside the bytes and silently corrupts the file — always exclude binary extensions from filtered resource sets.
  - Forgetting that `mvn integration-test` alone hides failures. Failsafe reports failures at `verify`; always run `mvn -B verify` (or `install`) for integration coverage.
  - Loading every reference file at activation. Classify the failure first, then load only the matching reference — progressive disclosure keeps context lean.
```

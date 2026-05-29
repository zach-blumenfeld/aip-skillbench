---
name: maven-plugin-configuration
description: Use when configuring Maven plugins, setting up common plugins like compiler, surefire, jar, or creating custom plugin executions. Covers pom.xml plugin definitions, <pluginManagement>, executions, phase bindings, and resolving build failures that trace to plugin misconfiguration — pinned versions, missing executions, wrong lifecycle phase, fork/parallel settings, and skipped tests.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a3
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a3/assets/aip-schemas/procedure.schema.json
compatibility: Maven projects (pom.xml). Requires `mvn` on PATH for the validate step.
---

```yaml
purpose: >
  Configure Maven plugins inside pom.xml — pin versions, set configuration,
  define executions, bind goals to lifecycle phases, and centralize shared
  setup in <pluginManagement>. Includes the standard catalog of common
  plugins (compile, test, coverage, quality, packaging, framework,
  versioning, codegen) so the agent can diagnose plugin-related build
  failures and apply a working configuration without re-deriving plugin
  coordinates and execution shapes from scratch.

trigger_when:
  - Configuring or modifying Maven plugins in a pom.xml.
  - Fixing a Maven build failure that traces to a plugin — missing version, wrong phase, failed goal, misconfigured execution, fork/memory issue, unexpected skip.
  - Adding a common plugin (maven-compiler-plugin, maven-surefire-plugin, maven-failsafe-plugin, maven-jar-plugin, maven-source-plugin, maven-javadoc-plugin, jacoco-maven-plugin, maven-enforcer-plugin, maven-checkstyle-plugin, spotbugs-maven-plugin, maven-pmd-plugin, maven-assembly-plugin, maven-shade-plugin, maven-war-plugin, spring-boot-maven-plugin, versions-maven-plugin, maven-release-plugin, build-helper-maven-plugin, exec-maven-plugin).
  - Creating custom plugin executions or binding goals to lifecycle phases.
  - Centralizing plugin versions across a multi-module project via <pluginManagement>.
  - Tuning build performance — parallel tests, forking, memory (argLine).
  - Setting up CI/release plugins behind a profile.
  - Generating source code via build-helper or exec plugin executions.

do_not_use_when:
  - The build failure is a pure dependency issue (missing artifact, version conflict) with no plugin definition involved — use a dependency-resolution skill instead.
  - Authoring a new Maven plugin from scratch (Mojo development), rather than configuring an existing one.
  - The project uses Gradle, sbt, or another build tool.

scope_and_approval: >
  Editing pom.xml files is a write action — apply edits directly to the
  working tree once the agent has identified the change. Running `mvn`
  goals locally is read-only for the project source but may download
  artifacts and write to ~/.m2; treat as safe by default. Do not run
  release, deploy, or version-bumping goals (mvn release:*, mvn deploy,
  mvn versions:set, mvn versions:commit) without explicit confirmation —
  those mutate tags, remote repositories, or VCS state.

steps:
  - name: identify-plugin-need
    description: >
      From the user's request or build-failure output, identify which
      plugin family is implicated — core build (compiler, resources, jar,
      source, javadoc), testing (surefire, failsafe, jacoco), quality
      (enforcer, checkstyle, spotbugs, pmd), packaging (assembly, shade,
      war), framework (spring-boot), version/release (versions, release),
      or codegen (build-helper, exec). If the trigger is a build failure,
      read the failing goal coordinate (`groupId:artifactId:version:goal`)
      from the Maven error and map it to a family.
    outputs:
      - name: plugin-family
        type: string
        description: One of plugin-basics, build-and-test, quality-and-packaging, ecosystem.
      - name: target-plugins
        type: list[string]
        description: Specific plugin artifactIds the change will touch.

  - name: inspect-current-pom
    description: >
      Read the relevant pom.xml(s). Note the current plugin entries,
      versions, executions, <pluginManagement> blocks, and any parent POM
      that may already set plugin coordinates the agent would otherwise
      duplicate. For multi-module projects, check the root POM before
      editing a child.
    inputs:
      - name: target-plugins
        type: list[string]
    outputs:
      - name: pom-state
        type: object
        description: Existing plugin definitions, versions, and where they live (root vs module, plugins vs pluginManagement).

  - name: load-plugin-reference
    description: >
      Open the references file matching the plugin family identified in
      step `identify-plugin-need`. Each reference file holds canonical
      XML snippets for the plugins in that family — copy and adapt rather
      than re-deriving coordinates and executions. Use `search_shortcuts`
      below to confirm which file to open.
    inputs:
      - name: plugin-family
        type: string
    one_of:
      - references/plugin-basics.md — plugin structure & <pluginManagement>
      - references/build-and-test-plugins.md — compiler, resources, jar, source, javadoc, surefire, failsafe, jacoco
      - references/quality-and-packaging-plugins.md — enforcer, checkstyle, spotbugs, pmd, assembly, shade, war
      - references/ecosystem-plugins.md — spring-boot, versions, release, build-helper, exec
    outputs:
      - name: reference-snippet
        type: string
        description: The XML snippet(s) from the chosen reference file that will seed the pom.xml edit.

  - name: apply-configuration
    description: >
      Edit pom.xml to apply the change. Pin every plugin version
      explicitly. Prefer placing version and shared configuration in
      <pluginManagement> on a parent or root POM and the bare <plugin>
      entry where it is actually used. Give every <execution> a
      meaningful id and bind it to the right lifecycle phase. If a
      configuration value is environment-sensitive (CI vs local, release
      vs dev), wrap it in a profile rather than hardcoding it into the
      default build. Read references/best-practices.md before committing
      non-trivial changes.
    inputs:
      - name: pom-state
        type: object
      - name: reference-snippet
        type: string
    outputs:
      - name: pom-edit
        type: object
        description: Files changed and a summary of plugin/execution additions or modifications.

  - name: validate-build
    description: >
      Run the narrowest Maven goal that exercises the changed plugin —
      `mvn validate` for enforcer/checkstyle, `mvn compile` for the
      compiler plugin, `mvn test` for surefire/jacoco, `mvn verify` for
      failsafe and most quality/packaging plugins, `mvn package` for
      jar/shade/assembly/war/spring-boot, `mvn javadoc:jar` for javadoc.
      If the build still fails, read the new error, return to
      `identify-plugin-need` with the updated coordinate, and iterate.
    inputs:
      - name: pom-edit
        type: object
    outputs:
      - name: build-result
        type: object
        description: Pass/fail, the goal run, and (on failure) the next plugin coordinate to investigate.

search_shortcuts:
  - category: Core build & compile
    body: >
      maven-compiler-plugin (compile Java, release flag, annotation processors),
      maven-resources-plugin (filter & copy resources, non-filtered extensions),
      maven-jar-plugin (build jar w/ manifest, test-jar execution),
      maven-source-plugin (jar-no-fork to attach sources),
      maven-javadoc-plugin (attach javadoc jar). See references/build-and-test-plugins.md.
  - category: Testing & coverage
    body: >
      maven-surefire-plugin (unit tests, includes/excludes, parallel, forkCount,
      argLine, systemPropertyVariables), maven-failsafe-plugin (integration
      tests with verify goal, skipAfterFailureCount), jacoco-maven-plugin
      (prepare-agent, report, check rules on LINE/BRANCH coverage). See
      references/build-and-test-plugins.md.
  - category: Quality gates
    body: >
      maven-enforcer-plugin (requireMavenVersion, requireJavaVersion,
      dependencyConvergence, bannedDependencies), maven-checkstyle-plugin
      (configLocation, fail severity, plugin <dependencies> for the
      checkstyle jar), spotbugs-maven-plugin (effort/threshold, exclude
      filter file), maven-pmd-plugin (rulesets, cpd-check). See
      references/quality-and-packaging-plugins.md.
  - category: Packaging & distribution
    body: >
      maven-assembly-plugin (jar-with-dependencies descriptor),
      maven-shade-plugin (uber-jar, ManifestResourceTransformer,
      ServicesResourceTransformer, signature-file excludes, package
      relocations), maven-war-plugin (failOnMissingWebXml,
      packagingExcludes, webResources). See
      references/quality-and-packaging-plugins.md.
  - category: Application frameworks
    body: >
      spring-boot-maven-plugin (repackage goal, layered jars, image build
      via paketo buildpacks, exclude annotation processors from the fat
      jar). See references/ecosystem-plugins.md.
  - category: Version & release
    body: >
      versions-maven-plugin (display-dependency-updates,
      display-plugin-updates, display-property-updates, update-properties,
      use-latest-releases, update-parent), maven-release-plugin
      (tagNameFormat, autoVersionSubmodules, releaseProfiles). See
      references/ecosystem-plugins.md.
  - category: Code generation & exec
    body: >
      build-helper-maven-plugin (add-source for generated-sources),
      exec-maven-plugin (run arbitrary scripts in a lifecycle phase). See
      references/ecosystem-plugins.md.
  - category: Foundations
    body: >
      Plugin element structure (groupId/artifactId/version/configuration/
      executions/goals) and <pluginManagement> for centralized versions
      and shared configuration. See references/plugin-basics.md.

scenarios:
  - need: Build fails because tests are running but not being picked up by Surefire.
    context: The project uses non-standard test class names; default include patterns (`**/*Test.java`, `**/Test*.java`, `**/*Tests.java`) don't match.
    action: Add maven-surefire-plugin with explicit <includes> covering the project's test class naming convention. Snippet from references/build-and-test-plugins.md.
    outcome: "Tests run on `mvn test`; failsafe stays scoped to `*IT.java` and `*IntegrationTest.java`."
  - need: Multi-module build has plugin-version drift; each module pins its own maven-compiler-plugin version.
    context: pom-state inspection shows three different versions across submodules and no <pluginManagement> entry in the root POM.
    action: "Move the version (and shared `<release>` config) into <pluginManagement> in the root POM per references/plugin-basics.md; reduce each child to a bare `<plugin>` entry inheriting from management."
    outcome: One source of truth for the compiler plugin; future bumps touch one file.
  - need: An executable jar produced by maven-jar-plugin is missing its dependencies at runtime.
    context: The user wants a runnable single-jar artifact and the current build only builds the thin jar.
    action: Add maven-shade-plugin bound to the package phase with ManifestResourceTransformer pointing at the main class, plus signature-file excludes. Snippet from references/quality-and-packaging-plugins.md.
    outcome: "`mvn package` produces a runnable uber-jar; ServicesResourceTransformer preserves merged META-INF/services entries."
  - need: CI fails on `mvn verify` because JaCoCo coverage check is below threshold.
    context: The build owns a coverage gate that should warn but not currently block; a release branch needs to ship.
    action: Read references/build-and-test-plugins.md for the JaCoCo `check` execution; either lower the rule's `minimum` to a defensible interim value or move the `check` execution behind a CI-only profile. Do not silently delete the gate.
    outcome: Build passes; coverage gate stays enforceable on the next iteration.
  - need: A Spring Boot app fails `mvn package` with "Unable to find main class".
    context: The project has multiple `public static void main` candidates.
    action: "Set `<mainClass>` explicitly on spring-boot-maven-plugin per references/ecosystem-plugins.md."
    outcome: "`mvn package` produces the repackaged executable jar pointing at the intended entry point."

anti_patterns:
  - Relying on Maven's default plugin version — always pin a version on every plugin entry, including those inherited from a parent.
  - Binding a plugin execution to the wrong lifecycle phase (e.g., `check` goals not bound to `verify`, jar plugin executions running at `compile`).
  - Duplicate <execution> blocks that run the same goal multiple times with conflicting configuration.
  - Insufficient JVM heap for memory-hungry plugins — set `<argLine>-Xmx…</argLine>` on Surefire/Failsafe rather than letting the forked JVM OOM mid-suite.
  - Unintended plugin inheritance from a parent POM that wasn't reviewed — always inspect the effective POM before adding what looks like a missing plugin.
  - Misunderstanding Surefire fork semantics — `forkCount=1C reuseForks=true` runs one fork per CPU and reuses it; setting `reuseForks=false` with high parallelism multiplies process startup cost.
  - Tests accidentally skipped in CI via `-Dmaven.test.skip=true` (skips compile too) or `-DskipTests=true`. Prefer explicit Surefire excludes over global skip flags.
  - Leaving plugin versions scattered across modules instead of centralizing in <pluginManagement> on a parent or root POM.
  - Mixing CI/release-only plugins (release, deploy, signing) into the default build instead of profile-gating them.
  - Editing a child module's pom.xml to add a plugin version when the same plugin is already managed in the parent — the child override silently wins and re-introduces drift.
  - Running `mvn versions:set`, `mvn release:*`, or `mvn deploy` without explicit user confirmation — these mutate VCS tags or remote repositories.
```

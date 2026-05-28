---
name: maven-plugin-configuration
description: Use when configuring Maven plugins, setting up common plugins like compiler, surefire, jar, or creating custom plugin executions. Also use when triaging a failing Maven build (`mvn ...` exits non-zero) where the failure points at a specific plugin/goal — covers the compiler, surefire/failsafe, jar/shade/assembly/spring-boot, enforcer/checkstyle/spotbugs/pmd, jacoco, versions, release, build-helper, and exec plugins, plus annotation-processor and pluginManagement patterns.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a2/assets/aip-schemas/procedure.schema.json
  source: TheBushidoCollective/han/jutsu/jutsu-maven/skills (via SkillsBench fix-build-google-auto)
compatibility: Requires Maven 3.x on PATH, Java (JDK matching the project's `<release>`), bash, and python3 for the helper scripts.
---

```yaml
purpose: >
  Configure Maven plugins correctly the first time, and repair a Maven build
  when a plugin goal fails. Covers core build, testing, quality, packaging,
  version-management, and code-generation plugins. The freeform cookbook of
  XML snippets lives in `references/`; this procedure routes an agent from
  symptom → plugin → fix → applied patch → green build.

trigger_when:
  - User asks to add, configure, or tune a Maven plugin (compiler, surefire,
    failsafe, jar, shade, assembly, war, spring-boot, enforcer, checkstyle,
    spotbugs, pmd, jacoco, versions, release, build-helper, exec).
  - A `mvn` invocation has failed and the log contains `[ERROR] Failed to
    execute goal <group>:<artifact>:<version>:<goal>`.
  - User needs to set up annotation processors (Lombok, AutoValue,
    AutoService, AutoFactory, Dagger, MapStruct, Immutables) via
    `<annotationProcessorPaths>`.
  - User wants to centralize plugin versions via `<pluginManagement>` in a
    parent POM.
  - User is bootstrapping CI builds, executable jars, code coverage gates,
    or static-analysis gates on a Maven project.
  - Repairing a BugSwarm-style build failure in a Java/Maven repo (e.g.
    `google/auto`-family modules where AutoValue/AutoService/AutoFactory
    processors must be declared explicitly).

do_not_use_when:
  - The failure is a dependency-resolution error (missing artifact, version
    conflict, classpath resolution). Use the `maven-dependency-management`
    skill instead.
  - The question is about Maven lifecycle phases or goal-to-phase binding
    in the abstract (no specific plugin involved). Use the
    `maven-build-lifecycle` skill instead.
  - The build tool is Gradle, sbt, Bazel, or Ant — this skill is
    Maven-specific.

scope_and_approval: >
  Read actions (parsing `mvn` logs, scanning `pom.xml`, reading reference
  files) are always allowed. Writes are limited to (a) producing diff files
  under `/home/travis/build/failed/<repo>/<id>/patch_*.diff` when the task
  follows the BugSwarm convention, or (b) editing `pom.xml` in place when
  the user explicitly asks for an applied fix. Never bump the project's
  Java `<release>`, Maven required version, or any version the user has
  not opted into changing — surface the recommendation instead.

steps:
  - name: parse-failure-log
    description: >
      Parse the Maven build log to identify the failing plugin coordinates,
      goal, execution id, and the trailing error lines. Skip this step if
      the user is configuring a plugin from scratch rather than repairing a
      failure.
    script: scripts/diagnose_plugin.sh
    inputs:
      - name: maven-log-path
        type: string
        description: Path to the captured `mvn` output (use `-` for stdin).
    outputs:
      - name: failure-record
        type: object
        description: >
          `{failed, plugin_group, plugin_artifact, plugin_version, goal,
          execution_id, module, error_lines, hints}` — see the script header
          for the schema.

  - name: locate-pom-and-plugin-block
    description: >
      Find the POM(s) where the failing or target plugin is declared. Walks
      the reactor from the working directory. For each candidate POM, run
      `extract_plugin_block.py <pom> <groupId> <artifactId>` to retrieve the
      `<plugin>` block with its line offsets and a flag for whether it
      sits inside `<pluginManagement>`.
    script: scripts/extract_plugin_block.py
    depends_on: [parse-failure-log]
    inputs:
      - name: failure-record
        type: object
        nullable: true
      - name: target-plugin
        type: object
        description: >
          When invoked outside a failure (greenfield configuration), the
          agent supplies `{group_id, artifact_id}` directly.
    outputs:
      - name: plugin-sites
        type: list[object]
        description: >
          For each match `{pom_path, start_line, end_line, in_management,
          block}`. Empty when the plugin is not yet declared.

  - name: consult-plugin-reference
    description: >
      Load the reference file for the plugin family in question and extract
      the canonical configuration snippet for the goal at hand. Reference
      files are progressive-disclosure documents — load only the one needed.
        - Plugin structure, `<pluginManagement>`, best practices, common
          pitfalls → `references/plugin-basics.md`.
        - Compiler / Resources / JAR / Source / Javadoc →
          `references/core-build-plugins.md`.
        - Surefire / Failsafe / JaCoCo → `references/testing-plugins.md`.
        - Enforcer / Checkstyle / SpotBugs / PMD →
          `references/quality-plugins.md`.
        - Assembly / Shade / WAR / Spring Boot →
          `references/packaging-plugins.md`.
        - Versions / Release / Build Helper / Exec →
          `references/version-and-codegen-plugins.md`.
    depends_on: [parse-failure-log]
    inputs:
      - name: failure-record
        type: object
        nullable: true
    outputs:
      - name: canonical-snippet
        type: string
        description: The reference XML snippet to model the fix on.

  - name: diagnose-and-pick-fix
    description: >
      Translate the failure signature into a specific configuration change.
      Cross-reference the failing goal and `hints` from `parse-failure-log`
      against `references/diagnosis-playbook.md`, which maps error messages
      to the concrete plugin-configuration knob to turn. For greenfield
      configuration, use the canonical snippet from
      `consult-plugin-reference` and adapt to the project's coordinates,
      Java release, and naming conventions.
    depends_on: [locate-pom-and-plugin-block, consult-plugin-reference]
    inputs:
      - name: failure-record
        type: object
        nullable: true
      - name: plugin-sites
        type: list[object]
      - name: canonical-snippet
        type: string
    outputs:
      - name: fix-plan
        type: object
        description: >
          `{action, pom_path, edit_kind, new_block, rationale}` where
          `action ∈ {add-plugin, modify-config, add-execution,
          fix-version, move-to-pluginmanagement, add-annotation-processor}`.

  - name: apply-or-emit-patch
    description: >
      Materialize the fix. For BugSwarm-style tasks, write a unified diff
      to `/home/travis/build/failed/<repo>/<id>/patch_<i>.diff` and apply
      with `git apply`. For interactive use, edit the POM in place.
      Preserve original indentation; Maven POMs are commonly two-space
      indented and downstream tools (`xmllint`, IDE formatters) will rewrap
      otherwise-clean diffs.
    depends_on: [diagnose-and-pick-fix]
    one_of:
      - emit-diff-file
      - edit-pom-in-place
    inputs:
      - name: fix-plan
        type: object
    outputs:
      - name: applied-changes
        type: list[object]
        description: '`[{pom_path, patch_path?, summary}]`.'

  - name: verify-build
    description: >
      Re-run the failing Maven invocation (or `mvn -pl <module> -am
      compile` / `package` / `verify` as appropriate) and confirm the
      original failure no longer reproduces. If a new failure surfaces,
      loop back to `parse-failure-log` with the new log. Cap at three
      iterations before surfacing the situation to the human.
    depends_on: [apply-or-emit-patch]
    inputs:
      - name: applied-changes
        type: list[object]
    outputs:
      - name: build-result
        type: object
        description: '`{passed, mvn_command, returncode, fresh_failure?}`.'

modes:
  - name: diagnose-only
    body: >
      Run only `parse-failure-log` → `locate-pom-and-plugin-block` →
      `diagnose-and-pick-fix`, then return the `fix-plan` for human review.
      Use when the user wants advice but not a patch.
  - name: patch-and-verify
    body: >
      Default mode for the `fix-build-google-auto` task family. Runs every
      step and emits diffs under `/home/travis/build/failed/<repo>/<id>/`
      per the task's instruction.md, then re-runs the build to confirm.
  - name: greenfield-configure
    body: >
      Skip `parse-failure-log`. The user supplies the target plugin
      coordinates; the procedure goes straight to
      `consult-plugin-reference` → `diagnose-and-pick-fix` (configuring,
      not repairing) → `apply-or-emit-patch`.

integrations:
  - partner: maven-build-lifecycle
    body: >
      When the failure is "plugin bound to wrong phase" or "goal fires too
      early/late", read the lifecycle skill first to pick the right phase,
      then return here to author the `<execution><phase>` block.
  - partner: maven-dependency-management
    body: >
      Enforcer `dependencyConvergence` / `requireUpperBoundDeps` violations
      are dependency problems wearing a plugin-configuration mask — hand
      off to the dependency-management skill, then return here only if a
      banned-dependency exclusion needs to be added to the Enforcer rule.
  - partner: fix-build-google-auto (SkillsBench task)
    body: >
      This skill is the primary lever for BugSwarm-style Java repair tasks.
      Inputs `bugswarm_image_tag`, `REPO_ID`, and the working directory
      `/home/travis/build/failed/<REPO_ID>` come from the task environment.
      The task expects diff files at
      `/home/travis/build/failed/<repo>/<id>/patch_*.diff` applied via
      `git apply` (see the task's `instruction.md`).

scenarios:
  - need: >
      `mvn package` on a `google/auto`-family module fails with
      `cannot find symbol: class AutoValue_Foo`.
    context: >
      `diagnose_plugin.sh` reports
      `plugin_artifact=maven-compiler-plugin`, goal `compile`,
      hints include `annotation-processor`. The pom's compiler block
      lacks `<annotationProcessorPaths>`.
    action: >
      Consult `references/core-build-plugins.md` § Compiler Plugin,
      then add the AutoValue processor under
      `<annotationProcessorPaths>` in the existing
      `maven-compiler-plugin` block.
    outcome: >
      Generated `AutoValue_Foo` reappears under
      `target/generated-sources/annotations`, compile succeeds.

  - need: >
      Multi-module reactor build emits
      `[ERROR] forked VM terminated without properly saying goodbye`
      from Surefire in one module.
    context: >
      Hints include `fork-heap`. The module's Surefire block has no
      `<argLine>`.
    action: >
      Add `<argLine>-Xmx1024m</argLine>` and drop `<forkCount>` to `1`
      with `<reuseForks>false</reuseForks>` per
      `references/testing-plugins.md` § Surefire Plugin.
    outcome: >
      Tests run to completion; coverage of forked-tests is preserved.

  - need: >
      Greenfield project needs an executable jar.
    context: User has not yet declared a packaging plugin.
    action: >
      Run in `greenfield-configure` mode. Load
      `references/packaging-plugins.md` § Spring Boot Plugin if the
      project is Spring Boot; otherwise § Shade Plugin (for SPI-rich
      uber-jars) or § Assembly Plugin (for the canned
      `jar-with-dependencies` descriptor). Adapt `mainClass` to the
      project's entry point.
    outcome: >
      `mvn package` produces an executable jar in `target/`.

anti_patterns:
  - >
      Editing `pom.xml` before running `diagnose_plugin.sh` — the failing
      plugin and goal are visible in the log and inferring them by hand
      misses the execution id when the same goal appears in multiple
      executions.
  - >
      Relying on the default plugin version. Maven core's "super POM"
      pins only a handful of plugins; everything else resolves to the
      latest available, which is non-deterministic across CI nodes.
      Always pin via `<version>` or in `<pluginManagement>`.
  - >
      Putting annotation processors on the classpath instead of
      `<annotationProcessorPaths>` on Java 9+. The compiler emits a
      deprecation warning today and may stop discovering them entirely
      in a future release.
  - >
      Bumping `<release>`, `<requireJavaVersion>`, or
      `<requireMavenVersion>` to make a failure go away without
      confirming with the user. These are project-wide policy changes,
      not local fixes.
  - >
      Patching the wrong `<plugin>` block when the same plugin appears
      in both `<pluginManagement>` and `<build><plugins>`. Use the
      `in_management` flag from `extract_plugin_block.py` to choose
      deliberately — version/policy lives in management, behavior lives
      in `<plugins>`.
  - >
      Stacking executions with duplicate ids in parent and child POMs.
      Maven *merges* by execution id; reuse of an inherited id silently
      overrides the parent's configuration.
  - >
      Adding `-DskipTests` or `<skipTests>true</skipTests>` to "fix" a
      Surefire failure. The failure must either be fixed or the test
      explicitly excluded with rationale.
  - >
      Removing the signed-jar excludes
      (`META-INF/*.SF|*.DSA|*.RSA`) from a Shade configuration. They
      are not optional — the resulting jar will throw
      `SecurityException: Invalid signature file digest` on startup.
```

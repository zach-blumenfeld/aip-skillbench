---
name: maven-dependency-management
description: Use when managing Maven dependencies, resolving dependency conflicts, configuring BOMs, fixing broken Java/Maven builds, or optimizing dependency trees. Triggers on Maven build failures, `mvn dependency:tree` inspection, `mvn dependency:analyze` warnings, missing-artifact errors, version-conflict errors, enforcer convergence violations, duplicate-class errors, BOM/import-scope decisions, and multi-module pom.xml edits.
compatibility: Requires `mvn` (Maven 3.x+), `python3`, and `bash`. Internet access needed for `mvn` to resolve artifacts from Maven Central or a private repository.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a2/assets/aip-schemas/procedure.schema.json
  source: vendor/skillsbench/tasks/fix-build-google-auto/environment/skills/maven-dependency-management/SKILL.md
---

```yaml
purpose: >
  Diagnose and resolve Maven dependency issues — missing artifacts, version
  conflicts, convergence failures, duplicate classes, scope mistakes,
  unused/used-undeclared dependencies — by running a fixed diagnostic
  sweep, classifying each issue against a decision table, and emitting the
  XML snippet that resolves it. Optimized for build-repair work where the
  agent must produce a pom.xml diff (and matching patch file) that takes
  a failing Maven build to green.

trigger_when:
  - "A Maven build (`mvn` / Travis / CI) fails with a dependency-resolution error."
  - "`mvn dependency:tree` shows multiple versions of the same `groupId:artifactId`."
  - "`mvn dependency:analyze` flags used-undeclared or unused-declared dependencies."
  - "Enforcer plugin reports `dependencyConvergence` or `requireUpperBoundDeps` failures."
  - "The agent is editing pom.xml to add, upgrade, or exclude a dependency."
  - "A BOM (`<scope>import</scope>`) is being added, removed, or upgraded."
  - "Runtime errors (`ClassNotFoundException`, duplicate classes, `NoSuchMethodError`) point at dependency mis-resolution rather than code."
  - "The task is build-repair on a Java/Maven repo (e.g., the `fix-build-google-auto` benchmark family)."

do_not_use_when:
  - "The failure is a pure Java compilation error in source code unrelated to dependency resolution (use a code-fix skill instead)."
  - "The project uses Gradle, Bazel, sbt, or another non-Maven build tool."
  - "The failure is in a Maven *plugin* configuration rather than a `<dependency>` (use `maven-plugin-configuration` if available)."
  - "The failure is in the Maven lifecycle binding itself (use `maven-build-lifecycle` if available)."

scope_and_approval: >
  Read-only diagnostic commands (mvn dependency:tree, dependency:analyze,
  help:effective-pom, compile) may run without confirmation. Writes are
  limited to pom.xml edits, generated patch files, and files inside the
  diagnostic working directory the inspect script creates. Do not modify
  ~/.m2/settings.xml or any file outside the project tree. When the task
  asks for a diff/patch file, emit it first and apply it second — do not
  hand-edit pom.xml without producing the matching patch artifact.

steps:
  - name: inspect-current-state
    description: >
      Run the standard diagnostic sweep against the project. Captures the
      dependency tree (plain + verbose), dependency-analyze report,
      effective POM, and a fresh `mvn compile` log into a working
      directory the next steps consume.
    script: scripts/inspect_dependencies.sh
    inputs:
      - name: project_dir
        type: string
        description: Path to the project root (the directory containing pom.xml).
      - name: out_dir
        type: string
        nullable: true
        description: Optional override for where diagnostics are written. Defaults to <project_dir>/.mvn-diagnostic.
    outputs:
      - name: diagnostic_dir
        type: string
        description: Directory containing dep-tree.txt, dep-tree-verbose.txt, dep-analyze.txt, effective-pom.xml, compile.txt.

  - name: diagnose-issues
    description: >
      Parse the diagnostic outputs and classify each problem by issue_type
      (missing-artifact, version-conflict, convergence-error,
      unused-declared, used-undeclared, duplicate-class,
      snapshot-in-release). All regexes and classification rules live in
      the script.
    depends_on:
      - inspect-current-state
    script: scripts/diagnose_conflict.py
    inputs:
      - name: diagnostic_dir
        type: string
    outputs:
      - name: issues
        type: list[object]
        description: One entry per detected issue with issue_type, coordinates, and short evidence text.

  - name: choose-resolution-strategy
    description: >
      For each issue, pick a resolution strategy from the fixed decision
      table — add-missing-dependency, bom-import,
      dependency-management-pin, transitive-exclusion, scope-fix,
      declare-used-undeclared, remove-unused-declared, or
      swap-snapshot-for-release. Recognises well-known BOM groups (Spring
      Boot, Jackson, AWS SDK, Google Cloud, JUnit, Netty, gRPC) and
      prefers BOM imports over per-artifact pins for those families.
    depends_on:
      - diagnose-issues
    script: scripts/choose_strategy.py
    inputs:
      - name: issues
        type: list[object]
    outputs:
      - name: strategies
        type: list[object]
        description: Same issues annotated with strategy and rationale.

  - name: load-pattern-references
    description: >
      Before authoring the pom.xml edit, load only the reference files the
      strategy needs. Read references/xml-patterns.md for the basic shapes
      (dependency, exclusion, version pin), references/boms.md for BOM
      import templates and ordering rules, references/scopes.md when a
      scope-fix is involved, references/multi-module.md when the pom has
      a <parent> element, and references/repositories.md only when the
      missing artifact looks like it lives in a private repo. Skip files
      whose patterns the chosen strategy does not need.
    depends_on:
      - choose-resolution-strategy
    inputs:
      - name: strategies
        type: list[object]
    outputs:
      - name: loaded_references
        type: list[string]

  - name: generate-pom-snippets
    description: >
      Emit the XML fragment for each strategy with placeholders flagged
      for the agent to fill (BOM_VERSION, RELEASED_VERSION, parent
      coordinates for exclusions). The snippet is positional advice
      (which section it goes in); the agent decides exact insertion
      point based on the existing pom layout.
    depends_on:
      - choose-resolution-strategy
    script: scripts/generate_patch_snippet.py
    inputs:
      - name: strategies
        type: list[object]
    outputs:
      - name: snippets
        type: list[string]

  - name: locate-target-pom
    description: >
      Pick which pom.xml each snippet belongs in. In a multi-module
      project, version pins and BOM imports go in the highest ancestor
      pom that all affected modules inherit from; add/remove
      dependencies stay in the module that uses them. When in doubt,
      prefer the project root pom and verify with `mvn -pl <module>
      dependency:tree` after applying.
    depends_on:
      - generate-pom-snippets
    inputs:
      - name: snippets
        type: list[string]
      - name: project_dir
        type: string
    outputs:
      - name: insertion_plan
        type: list[object]
        description: Each entry binds a snippet to a target pom.xml path and section (dependencies vs dependencyManagement).

  - name: write-diff-and-apply
    description: >
      Build the unified diff(s) the task expects (e.g., patch_1.diff,
      patch_2.diff) from the insertion plan, then apply them with `git
      apply` or `patch -p1`. Write notes (root cause + fix plan) to the
      task's analysis file (e.g., failed_reasons.txt) before generating
      the diffs.
    depends_on:
      - locate-target-pom
    inputs:
      - name: insertion_plan
        type: list[object]
    outputs:
      - name: diff_paths
        type: list[string]

  - name: verify-fix
    description: >
      Re-run the diagnostic sweep and a full `mvn clean verify`. The fix
      is accepted only when the build exits 0 and the issue list from
      diagnose_conflict.py is empty. On failure, return to
      diagnose-issues with the new logs — do not iterate on the patch
      blindly.
    depends_on:
      - write-diff-and-apply
    script: scripts/verify_fix.sh
    inputs:
      - name: project_dir
        type: string
    outputs:
      - name: build_ok
        type: boolean
      - name: remaining_issues
        type: list[object]

modes:
  - name: diagnostic-only
    body: >
      Run steps inspect-current-state → diagnose-issues and stop. Use
      when the user asks for a dependency audit without an authorisation
      to edit pom.xml. Emits the JSON issue list as the deliverable.
  - name: patch-and-verify
    body: >
      Full run, including write-diff-and-apply and verify-fix. Default
      mode for build-repair tasks. The verify step is non-negotiable —
      a build that compiles is not the same as a build whose
      dependencies converge.
  - name: planning-only
    body: >
      Run through generate-pom-snippets and stop. Use when the user
      wants to review the proposed edit before any file is touched.
      Emits the snippets plus the insertion plan as the deliverable.

search_shortcuts:
  - category: Diagnostic commands
    body: |
      - `mvn dependency:tree` — resolved tree
      - `mvn dependency:tree -Dverbose` — shows omitted-for-conflict markers
      - `mvn dependency:tree -Dincludes=org.slf4j` — filter by groupId
      - `mvn dependency:analyze -DignoreNonCompile=false` — used/unused report
      - `mvn dependency:list -DincludeScope=runtime` — flat list per scope
      - `mvn help:effective-pom -Doutput=epom.xml` — fully-resolved POM
      - `mvn -U clean install` — force refresh of cached metadata
      - `mvn dependency:purge-local-repository` — wipe local cache
  - category: Well-known BOMs
    body: |
      - Spring Boot: org.springframework.boot:spring-boot-dependencies
      - Spring Cloud: org.springframework.cloud:spring-cloud-dependencies
      - Jackson: com.fasterxml.jackson:jackson-bom
      - JUnit 5: org.junit:junit-bom
      - AWS SDK v2: software.amazon.awssdk:bom
      - Google Cloud: com.google.cloud:libraries-bom
      - Netty: io.netty:netty-bom
      - gRPC: io.grpc:grpc-bom
  - category: References on demand
    body: |
      - references/xml-patterns.md — dependency, exclusion, version-range XML
      - references/scopes.md — scope-to-classpath table and symptom triage
      - references/boms.md — BOM list, import template, ordering rules
      - references/multi-module.md — parent-pom dependencyManagement, enforcer
      - references/repositories.md — central, private repo, credential setup

integrations:
  - partner: maven-build-lifecycle
    body: >
      When the failure is in goal binding, packaging type, or phase
      ordering rather than a <dependency> entry, defer to
      maven-build-lifecycle. A symptom that points there: the error
      names a Maven *phase* or *plugin goal* without naming a
      coordinate.
  - partner: maven-plugin-configuration
    body: >
      When the failure is in a <plugin> configuration (compiler source
      level, surefire arguments, shade transformer) rather than a
      <dependency>, defer to maven-plugin-configuration. Plugin
      dependencies declared inside <plugin><dependencies> are still in
      scope for this skill.
  - partner: java-build-repair-host-task
    body: >
      In the fix-build-google-auto benchmark family, write the diagnosis
      to the task's analysis file (e.g., failed_reasons.txt) before
      generating diffs, and produce numbered patch files
      (patch_1.diff, patch_2.diff, …) at the repo root. The verify step
      still applies — the host task scores on a green build, not a
      clean diff.

scenarios:
  - need: >
      A Spring Boot project fails to build because two transitive paths
      pull in jackson-databind at different versions and the runtime
      throws NoSuchMethodError on a method the older one lacks.
    context: >
      inspect-current-state writes dep-tree-verbose.txt; diagnose-issues
      flags a version-conflict on
      com.fasterxml.jackson.core:jackson-databind.
    action: >
      choose-resolution-strategy picks bom-import because the groupId
      is in the well-known BOM table; generate-pom-snippets emits the
      jackson-bom import; the agent inserts it in the root pom's
      <dependencyManagement> and drops any explicit <version> on
      Jackson artifacts in module poms.
    outcome: >
      Tree converges to a single Jackson version; verify-fix exits 0.

  - need: >
      mvn dependency:analyze shows commons-logging as a used-undeclared
      dependency, and the test suite fails because it is excluded by
      spring-boot-starter.
    context: >
      diagnose-issues emits a used-undeclared issue on
      commons-logging:commons-logging.
    action: >
      Strategy mapping picks declare-used-undeclared; the snippet adds
      an explicit <dependency> for commons-logging in the module that
      references it. The agent reviews whether the right fix is instead
      to remove the offending import in source code — the skill flags
      this as a judgement call.
    outcome: >
      Declared explicitly; build passes; tech-debt note added to remove
      the dependency once source code is migrated to SLF4J.

  - need: >
      A leaf module of a multi-module project hits a
      dependencyConvergence enforcer failure on org.slf4j:slf4j-api.
    context: >
      Verbose tree shows three different SLF4J versions across modules.
    action: >
      Strategy is dependency-management-pin; locate-target-pom points
      to the project root pom; snippet pins slf4j-api under root
      <dependencyManagement>. Leaf module poms keep their version-less
      <dependency> entries.
    outcome: >
      Convergence rule passes; SLF4J upgrades flow from a single line.

anti_patterns:
  - "Editing pom.xml without first running `mvn dependency:tree -Dverbose` — the version Maven actually picks is rarely the one nearest in the file."
  - "Adding an <exclusion> to fix a version conflict when a <dependencyManagement> pin or BOM import would resolve it more durably and across modules."
  - "Using <version>LATEST</version> or <version>RELEASE</version> — non-reproducible, removed in Maven 4, and silently breaks future builds."
  - "Pinning a transitive in a leaf module's <dependencies> when the rest of the multi-module project still resolves the old version — only <dependencyManagement> controls the whole tree."
  - "Using <scope>system</scope> to point at a local JAR — hardcoded paths break portability; use an install-file goal or a private repo instead."
  - "Marking a required runtime dependency as <optional>true</optional> — downstream consumers will compile but fail at runtime."
  - "Leaving SNAPSHOT versions in a release build — non-reproducible; replace with the matching released version before tagging."
  - "Calling the fix \"done\" because `mvn compile` passed — only `mvn clean verify` (the verify-fix step) catches the convergence and packaging-time issues."
  - "Skipping the <parent> lookup when applying a fix in a multi-module project — the pin may already live in an ancestor pom and conflict with the new one."
  - "Adding a private repository entry into pom.xml to chase a missing artifact when the artifact is actually on Maven Central and the failure is a cache or network issue (try `mvn -U` first)."
```

---
name: maven-dependency-management
description: Use when managing Maven dependencies, resolving dependency conflicts, configuring BOMs, or optimizing dependency trees in Java projects. Diagnoses Maven build failures (missing artifacts, version conflicts, ClassNotFoundException, NoSuchMethodError, "package does not exist") and emits pom.xml fixes as unified diffs ready for `git apply`.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a3
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a3/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Diagnose and fix Maven dependency problems in Java projects — version
  conflicts, missing or wrongly-scoped transitives, BOM misconfiguration,
  unreachable artifacts — and produce pom.xml changes as unified diffs
  that `git apply` accepts. Covers Maven's nearest-wins resolution model,
  scopes, BOMs, exclusions, and the diagnostic commands (`dependency:tree`,
  `dependency:analyze`, `help:effective-pom`) that surface the root cause.

trigger_when:
  - A Maven build fails with a dependency-shaped error (Could not find artifact, Failure to find, Could not resolve dependencies, package does not exist, ClassNotFoundException, NoSuchMethodError, dependency convergence).
  - Adding, upgrading, or removing a Maven dependency.
  - Reconciling transitive versions across a multi-module project.
  - Configuring or importing a BOM (Spring Boot, Jackson, AWS SDK, JUnit, Netty, etc.).
  - Excluding a problematic transitive dependency.
  - Diagnosing classpath issues (compile vs runtime vs test vs provided).

do_not_use_when:
  - The failure is a pure Java source-code bug unrelated to dependencies (syntax, project-internal type errors).
  - The failure is in plugin behavior unrelated to dependency resolution (e.g., surefire fork settings, compiler source/target).
  - CI infrastructure (Docker base image, shell wrapper) is at fault rather than pom.xml.

scope_and_approval: >
  Read-only until `apply-and-verify` writes `patch_*.diff` and invokes
  `git apply`. The skill never installs Maven plugins, never touches
  `~/.m2/settings.xml` (it only documents what belongs there), and never
  changes repository credentials. The `failed_reasons.txt` write and the
  patch application are expected, in-task side effects.

steps:
  - name: capture-build-failure
    description: >
      Run the failing Maven goal (typically `mvn -B clean install` or
      whatever the upstream CI ran) from the repo root and capture full
      stdout+stderr to a log file. Note the failing phase
      (validate / compile / test / package / install) and the first ERROR
      line — that line usually carries the error class.
    outputs:
      - { name: build-log-path, type: string, description: "Absolute path to the captured log." }
      - { name: failing-phase, type: string }

  - name: classify-error
    description: Pattern-match the build log against known Maven dependency failure modes. Emits a primary error class plus per-match artifact coordinates / symbol names.
    script: scripts/classify_maven_error.py
    inputs:
      - { name: build-log-path, type: string }
    outputs:
      - { name: error-class, type: string, description: "missing-artifact | package-not-found | class-not-found | method-not-found | version-conflict | compile-symbol | other" }
      - { name: candidates, type: "list[object]", description: "Each: error_class + match + class-specific keys (groupId/artifactId/version, package, fqcn, method, symbol)." }

  - name: diagnose
    description: >
      Run the Maven diagnostic commands relevant to the error class — verbose
      `dependency:tree` (optionally filtered to the offending coordinate),
      `dependency:analyze`, and `help:effective-pom` (skipped in quick mode).
      Returns the file paths so the agent can read whichever capture the
      situation needs.
    script: scripts/diagnose.sh
    inputs:
      - { name: repo-root, type: string }
      - { name: filter, type: string, nullable: true, description: "groupId or groupId:artifactId to pass as -Dincludes=" }
      - { name: error-class, type: string }
    outputs:
      - { name: diagnostics, type: object, description: "{tree, analyze, effective_pom, mode} — paths or null." }

  - name: pick-fix-pattern
    description: >
      Read `references/fix-patterns.md` and apply its error-class→pattern
      decision table to the diagnostics. Pick the smallest fix that
      resolves the failure; prefer `<dependencyManagement>` over per-dep
      `<version>` so all transitives converge. Record the target pom
      path(s) and the edits to make.
    inputs:
      - { name: error-class, type: string }
      - { name: candidates, type: "list[object]" }
      - { name: diagnostics, type: object }
    outputs:
      - { name: fix-plan, type: object, description: "pattern + target pom path(s) + an edits list (each edit is an object)." }
    one_of:
      - pin-version-in-dependencyManagement
      - import-bom
      - add-exclusion
      - change-scope
      - add-missing-dependency
      - fix-repository-config

  - name: write-reasons-note
    description: >
      Write a short analysis to `/home/travis/build/failed/failed_reasons.txt`
      summarizing the failing phase, the error class, the root-cause
      artifact(s), and the chosen fix pattern with a one-sentence rationale.
      The file must be non-empty — the verifier asserts this — and is the
      agent's own working note for the patch step.
    inputs:
      - { name: failing-phase, type: string }
      - { name: error-class, type: string }
      - { name: candidates, type: "list[object]" }
      - { name: fix-plan, type: object }
    outputs:
      - { name: reasons-path, type: string }

  - name: generate-patches
    description: >
      Edit the target pom(s) in place per `fix-plan.edits`, then produce
      unified diffs with `git diff --no-color` and write them to the repo
      root as `patch_0.diff`, `patch_1.diff`, ... (one diff per logical
      change, or one combined diff if the edits are inseparable). Paths
      must be `a/<path>` and `b/<path>` style — raw `diff -u` output is
      rejected by `git apply`.
    inputs:
      - { name: fix-plan, type: object }
      - { name: repo-root, type: string }
    outputs:
      - { name: patch-paths, type: "list[string]" }

  - name: apply-and-verify
    description: >
      Apply each patch from the repo root (`git apply patch_<i>.diff` in
      filename order), then re-run the originally-failing Maven goal. If
      the build passes, stop. If it fails with a *different* error class,
      stop and surface — fixing one class can unmask another but the loop
      should not chase unrelated failures silently. If it fails with the
      *same* error class, loop back to `diagnose` with the new log.
    inputs:
      - { name: patch-paths, type: "list[string]" }
      - { name: repo-root, type: string }
    outputs:
      - { name: build-status, type: string, description: "passed | failed-same-class | failed-other-class" }

modes:
  - name: quick
    body: >
      Skip `help:effective-pom` and skip the second loop iteration. Use when
      the error class is unambiguous (missing-artifact with typo, obvious
      scope bug) and reading the full effective pom would waste time.
  - name: full
    body: >
      Run all three diagnostics, read the effective pom before picking a
      pattern, and loop back to `diagnose` on `failed-same-class`. Default.

search_shortcuts:
  - category: Maven diagnostic commands
    body: |
      mvn -B dependency:tree -Dverbose=true                # show conflict resolution
      mvn -B dependency:tree -Dincludes=<groupId>          # filter by groupId
      mvn -B dependency:tree -Dincludes=<groupId>:<artifactId>
      mvn -B dependency:analyze                            # unused + undeclared
      mvn -B dependency:analyze -DignoreNonCompile=false   # include test scope
      mvn -B help:effective-pom -Doutput=effective.xml     # resolved pom
      mvn -B -X <goal>                                     # debug-level log
      mvn -B -U clean install                              # force snapshot refresh
      mvn -B dependency:purge-local-repository             # nuke local cache
  - category: Scope cheat sheet (full table in references/maven-reference.md)
    body: |
      compile  (default) → compile + test + runtime; transitive
      provided           → compile + test only; not packaged; not transitive
      runtime            → test + runtime; transitive (drivers, impls)
      test               → test classpath only; not transitive
      system             → like provided + path-based; do not use
      import             → only inside <dependencyManagement> for BOMs
  - category: Common BOMs
    body: |
      org.springframework.boot:spring-boot-dependencies
      com.fasterxml.jackson:jackson-bom
      org.junit:junit-bom
      software.amazon.awssdk:bom
      io.netty:netty-bom
  - category: Diff-format reminders for patch_*.diff
    body: |
      Generate with `git -C <repo> diff --no-color > patch_<i>.diff` so paths are a/<path> and b/<path>.
      Raw `diff -u` paths are rejected by `git apply`.
      Number patches `patch_0.diff`, `patch_1.diff`, ... in the repo root (not a subdir).
      Patches must apply cleanly without `--3way`; strip BOM / CRLF before writing.

integrations:
  - partner: references/fix-patterns.md
    body: >
      Load before `pick-fix-pattern`. Contains the decision table mapping
      `error_class` to the six `one_of` patterns plus a copy-pastable XML
      template per pattern and the `patch_<i>.diff` format spec.
  - partner: references/maven-reference.md
    body: >
      Load on demand when the quick cheat sheets above are insufficient —
      full scope semantics, version-range syntax, multi-module parent pom
      wiring, repository configuration with credentials, the enforcer
      plugin block, and the troubleshooting commands.

scenarios:
  - need: Two transitive paths bring slf4j-api 1.7.x and 2.0.x; runtime fails with java.lang.NoSuchMethodError on a 2.x method.
    context: classify-error → method-not-found. diagnose tree shows path A wins at 1.7.x.
    action: pin-version-in-dependencyManagement at the parent pom for slf4j-api 2.0.9.
    outcome: Both paths converge to 2.0.9; runtime resolves the method.
  - need: spring-boot-starter-web pulls in tomcat but the project must use jetty.
    context: Build passes but wrong server starts. classify-error → other; diagnose tree confirms tomcat under starter-web.
    action: add-exclusion of spring-boot-starter-tomcat under starter-web; add spring-boot-starter-jetty.
    outcome: Jetty starts; tomcat absent from the packaged jar.
  - need: '`package javax.servlet does not exist` at compile in a web module.'
    context: classify-error → package-not-found. Sibling module declares the servlet API as provided; this one doesn't.
    action: change-scope — declare jakarta.servlet-api with <scope>provided</scope> in this module's pom.
    outcome: Compiles; container supplies the API at runtime; no fat-jar bloat.
  - need: '`Could not find artifact com.example:foo:jar:1.2.3` during dependency resolution.'
    context: classify-error → missing-artifact. Coordinate isn't on Maven Central.
    action: fix-repository-config — verify spelling first; if it's a private artifact, add the <repository> entry (and matching <server> in settings.xml).
    outcome: Artifact resolves; build proceeds past the resolution failure.
  - need: '`dependency:analyze` reports "Used undeclared dependencies: com.google.guava:guava".'
    context: classify-error → compile-symbol on guava classes after a refactor.
    action: add-missing-dependency — declare guava explicitly at the version currently coming in transitively.
    outcome: Compile succeeds; no longer relies on a transitive that could disappear.

anti_patterns:
  - Bumping a *direct* <version> when the conflict is *transitive* — fix in <dependencyManagement> so every path converges, not just the one you noticed.
  - Re-adding <version> on a dep already managed by an imported BOM — defeats the BOM and reintroduces drift.
  - Using <scope>system</scope> with an absolute path — breaks on any machine without that file.
  - Pinning LATEST or RELEASE, or an open-ended range like [1.0,), in production poms — non-reproducible builds.
  - Excluding a transitive without supplying a replacement (e.g., excluding tomcat without adding jetty).
  - Marking a runtime-required dependency <optional>true</optional> — silent runtime ClassNotFoundException.
  - Writing patches with raw `diff -u` paths instead of `git diff` a/<path> b/<path> — `git apply` rejects them.
  - Leaving /home/travis/build/failed/failed_reasons.txt empty or missing — the verifier asserts it exists and is non-empty.
  - Numbering patches outside the repo root or in a subdir — the verifier scans the repo root only.
  - Chasing an unrelated downstream error after the first fix — return failed-other-class and surface, don't loop.
```

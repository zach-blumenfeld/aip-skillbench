---
name: maven-build-fix
description: Diagnose and fix a failing Maven build (Java) so the original CI command passes. Finds the root/aggregator POM (including non-standard ones like build-pom.xml), lints POMs, picks the CI's JDK (jdk_switcher), runs the build, classifies the failure from the log (dependency/plugin resolution, HTTPS/TLS repository errors, POM model errors, JDK mismatch, javac and annotation-processor errors, test failures and fork crashes, enforcer, javadoc, quality gates, OOM), then iterates fix-and-rebuild. Carries Maven lifecycle, dependency-management, and plugin-configuration knowledge. Use for broken Maven/Travis/BugSwarm builds, "mvn install fails", or repairing a Java project's pom.xml.
metadata:
  aip-version: "0.5a1"
---

# AIP runtime — format 0.5a1

You are executing an Agent Instruction Protocol (AIP) procedure: the fenced YAML block in this skill's `SKILL.md`. AIP is a protocol for cheaply, quickly, and accurately executing multi-step tasks as a graph of typed steps. You drive the run and execute every step yourself, following the semantics below.

Critical terminology:

- **Client**: you, the agent running this procedure; the `client_task` step kind is named for it. You supply each step's input, run its script, answer its questions by your own judgment, perform its task, follow its router, and make the final call at every step.
- **State**: the JSON object a step receives. Each step declares its required keys as `inputs`; extra keys pass through.
- **Step kinds**: `execution` runs a script, `decision` asks typed questions about the state, `client_task` hands work to you, `router` branches on a value in the state, `end` declares the final state's shape.

## Execution

The state is one JSON object. It starts as the start step's `inputs` and flows along `inputs_to`; each step's output is merged over it, so keys accumulate and extra keys pass through untouched. A step runs only if the state holds every key it declares in `inputs`, with the declared types; check that before each step. You may change the state before any step runs; you have the final say at every step.

- **`execution`**: run `script` with one JSON object on stdin, `{"currentState": <state>, "assets": {<file stem>: <content>}, "expects": <the next step's inputs>}`. The script writes one JSON object to stdout; merge it over the state.
- **`decision`**: answer each question against the state. Each answer collapses to one value under its question name and is merged over the state: a noul to `true`/`false`, a choice to its label, a score to its level number. `thresholds` name the questions where an uncertain answer matters most; when your answer to one is a close call, reconsider it before continuing.
- **`client_task`**: render `template` with `{key}` from the state, `{assets[stem]}` for its assets, and `{meta.name}` for the skill name. Perform the task, loading `references` if their descriptions apply, and produce the next step's `inputs`; merge them over the state.
- **`router`**: read the state's `branch_on` key and continue at `branches[value]`. A value with no branch is an error.
- **`end`**: the state must hold `end`'s `inputs`. That state is the procedure's result.

```yaml
purpose: >
  Make a failing Maven build pass for the right reason. A script inspects the project
  (root POM, reactor modules, compiler levels, profiles, CI config, installed JDKs, ~/.m2)
  and lints the POMs; the agent confirms the build command and JDK; a script runs the build
  and classifies the log against a catalog of Maven failure modes with a playbook for each;
  a decision fixes the layer to change; the agent applies the smallest correct fix and the
  build re-runs until it passes or the round limit is hit. Adds what an agent lacks:
  non-standard aggregator POMs, CI-default commands, JDK switching and TLS/HTTPS repository
  pitfalls of archived builds, log-to-cause mapping, and the Maven lifecycle, dependency,
  and plugin rules needed to fix the cause instead of hiding it.

trigger_when:
  - A Maven build (mvn compile/test/install/verify) fails and must be repaired.
  - A task asks to fix a broken CI build of a Java project that has a pom.xml (Travis CI, BugSwarm, GitHub Actions, Jenkins).
  - A Maven reactor module fails on dependency resolution, compilation, tests, or a plugin goal.
  - Debugging Maven phases, profiles, dependency conflicts, or plugin configuration as part of getting a build green.

do_not_use_when:
  - The project builds with Gradle, Ant, sbt, or Bazel and has no pom.xml.
  - The task is to design a new Maven project or write new features, not to repair a failing build.

steps:
  - name: inspect-project
    kind: execution
    description: Locate the root POM and reactor, lint every POM, read .travis.yml, and survey JDKs, Maven, and ~/.m2.
    inputs:
      - name: project_dir
        type: string
        description: Repository root holding the root POM. Empty string searches /home/travis/build/failed and other usual roots.
      - name: failure_report
        type: string
        description: What the task says about the failure (error text, failing module or test); empty string if nothing.
    script: scripts/inspect_project.py
    timeout: 120
    inputs_to: confirm-build

  - name: confirm-build
    kind: client_task
    description: Choose the exact build command and JDK that reproduce the CI failure.
    inputs:
      - name: project_dir
        type: string
      - name: project_facts
        type: object
        description: Root POM, modules, compiler levels, profiles, CI config, environment.
      - name: pom_findings
        type: list[*]
        description: Static POM problems found by the linter.
      - name: build_command
        type: string
        description: Suggested command (CI script command, else CI default, else mvn -B -e clean install).
      - name: jdk
        type: string
        description: Suggested JDK (CI jdk value or derived from the compiler level).
    template: assets/confirm_build.md
    references:
      - path: references/environment-gotchas.md
        description: Where archived CI checkouts live, non-standard aggregator POMs, jdk_switcher aliases, JDK 7 TLS, HTTPS-only Central, the /home/travis ~/.m2 cache, LANG=C encoding, Travis default commands. Load when choosing the JDK or command.
      - path: references/build-lifecycle.md
        description: Lifecycle phase order, phase vs goal, profiles and activation, reactor flags (-pl -am -amd -rf -T), skip flags, debugging flags. Load when the command or the module selection is unclear.
    inputs_to: run-build

  - name: run-build
    kind: execution
    description: Run the build command under the chosen JDK (or read external_log_path), then classify the failure and extract the evidence.
    inputs:
      - name: project_dir
        type: string
      - name: build_command
        type: string
      - name: jdk
        type: string
      - name: round
        type: integer
        description: Build rounds completed so far; the script increments it.
    script: scripts/run_build.py
    assets:
      - assets/failure_catalog.json
    timeout: 3600
    inputs_to: by-outcome

  - name: by-outcome
    kind: router
    description: Green builds and exhausted round budgets go to the report; failures go to diagnosis.
    branch_on: build_outcome
    branches:
      passed: report
      failed: assess-cause
      exhausted: report

  - name: assess-cause
    kind: decision
    description: Check the classifier's category against the evidence and pick the layer the fix belongs in.
    inputs:
      - name: failure_category
        type: string
        description: Catalog category chosen from the log.
      - name: first_error
        type: string
        description: The first meaningful error line of the log.
      - name: diagnosis
        type: object
        description: Failing goal, module, phase, first error lines, javac errors, failed tests, reactor summary, log tail, layer_hint.
      - name: pom_findings
        type: list[*]
    questions:
      category_matches:
        type: noul
        instructions: Does failure_category describe first_error, the first real error (check diagnosis.error_excerpt in case first_error is only a header or a cascade)?
        criteria:
          true: The first error line is the kind of failure the category names.
          false: The first error belongs to another category, or the category is unknown.
      fix_layer:
        type: choice
        instructions: >
          Where must the change be made so the original build command passes? Use the first error,
          the failing goal and phase, and diagnosis.layer_hint as a prior. A javac error caused by a
          dependency version is build-config only when the code is correct for the intended version.
        criteria:
          build-config: POM content — versions, scopes, exclusions, dependencyManagement, plugin versions or configuration, repositories, modules, profiles.
          main-source: Java code or resources under src/main (including annotation processors and their META-INF/services registration).
          test-code: Tests or test resources under src/test are wrong while the production code is right.
          environment: JDK choice, Maven version, network/TLS, HOME/~/.m2, memory; nothing in the code or POM is wrong for the intended toolchain.
          transient: A network timeout or flaky test with no code or config cause; rerunning unchanged should pass.
    thresholds:
      category_matches: 0.2
      fix_layer: 0.6
    inputs_to: apply-fix

  - name: apply-fix
    kind: client_task
    description: Apply the smallest fix for the root cause in the chosen layer and verify it with the focused command.
    inputs:
      - name: project_dir
        type: string
      - name: build_command
        type: string
      - name: jdk
        type: string
      - name: round
        type: integer
      - name: failure_category
        type: string
      - name: fix_playbook
        type: string
        description: Catalog playbook for the category.
      - name: diagnosis
        type: object
      - name: build_log_path
        type: string
      - name: category_matches
        type: boolean
      - name: fix_layer
        type: string
    template: assets/apply_fix.md
    references:
      - path: references/dependency-management.md
        description: Scope table (compile/provided/runtime/test/system/import), version ranges, property versions, dependencyManagement and BOM import, exclusions, nearest-wins conflict resolution, enforcer convergence, dependency:tree/analyze, repositories, -U and purge. Load for resolution, conflict, scope, or missing-version failures.
      - path: references/plugin-configuration.md
        description: Plugin structure and pluginManagement, compiler (release, annotationProcessorPaths, compilerArgs), resources, jar, source, javadoc, surefire, failsafe, JaCoCo, enforcer, checkstyle, SpotBugs, PMD, assembly, shade, war, versions, release, build-helper, exec. Load when a plugin goal fails or must be configured or pinned.
      - path: references/build-lifecycle.md
        description: Phase order and phase-to-goal binding, profiles and activation triggers, resource filtering, source/target settings, reactor options, test configuration, debugging (-X, -e, help:effective-pom, help:active-profiles). Load when the failure involves phases, profiles, filtering, or module order.
      - path: references/environment-gotchas.md
        description: JDK switching, TLS and HTTPS repository errors, ~/.m2 cache location, LANG=C encoding, durable .mvn/jvm.config and .mvn/maven.config, what counts as fixed. Load for environment-layer fixes.
    inputs_to: run-build

  - name: report
    kind: client_task
    description: Summarize the root cause, the changes, and the final build result.
    inputs:
      - name: project_dir
        type: string
      - name: build_outcome
        type: string
      - name: build_command
        type: string
      - name: jdk
        type: string
      - name: round
        type: integer
      - name: build_log_path
        type: string
      - name: diagnosis
        type: object
    template: assets/report.md
    inputs_to: end

  - name: end
    kind: end
    description: The build outcome with a summary of the root cause and every change made.
    inputs:
      - name: build_outcome
        type: string
      - name: summary
        type: string
      - name: changes_made
        type: list[*]

anti_patterns:
  - Making the build green with -DskipTests, -Dmaven.test.skip=true, -fn/-fae, testFailureIgnore, @Ignore, deleting tests, or dropping modules; the build is fixed only when the original command runs everything and passes.
  - Fixing a later cascade error instead of the first [ERROR] in the log.
  - Running Maven on whatever JDK is default instead of the CI's JDK, then "fixing" code for a JDK mismatch.
  - Running a bare `mvn` from the root of a project whose aggregator is build-pom.xml (or another -f file), so the reactor never builds.
  - Leaving plugin or dependency versions unpinned, or pinning them in one module instead of the root pluginManagement/dependencyManagement.
  - Using version ranges, LATEST/RELEASE, or external SNAPSHOTs as a fix; pin exact published versions.
  - Fixing an environment problem only in the shell (export, jdk_switcher) when the evaluator re-runs the build fresh; put durable settings in .mvn/ or the POM.
  - Lowering coverage, checkstyle, PMD, SpotBugs, or enforcer rules instead of fixing the violation.
  - Adding exclusions or forced versions without a comment saying why.
  - Rebuilding the whole reactor for every experiment instead of the focused -pl :module -am command.
```

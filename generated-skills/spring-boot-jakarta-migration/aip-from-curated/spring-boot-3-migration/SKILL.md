---
name: spring-boot-3-migration
description: Migrate a Spring Boot 2.x Maven application to Spring Boot 3.2 and Java 21 in place. Upgrades the pom (parent 3.2.0, java.version 21, removes javax.xml.bind jaxb-api and activation, replaces jjwt 0.9.1 with jjwt-api/impl/jackson 0.12.3), rewrites javax.persistence/validation/servlet/annotation/transaction imports to jakarta, converts WebSecurityConfigurerAdapter to a SecurityFilterChain bean with lambda DSL, @EnableGlobalMethodSecurity to @EnableMethodSecurity, antMatchers to requestMatchers, RestTemplate to RestClient, and fixes Hibernate 6 HQL/Criteria/@Type changes; then verifies statically and compiles and tests with Maven on Java 21. Use for Spring Boot 2 to 3 upgrades, Jakarta EE namespace migration, Spring Security 6 or Hibernate 6 migration.
metadata:
  aip-version: "0.5a1"
  version: "1.0"
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
  Migrate a Spring Boot 2.x (Java 8/11, Maven) application to Spring Boot 3.2 on Java 21 in
  place: pom upgrade (parent 3.2.0, java.version 21, JAXB/activation removed, modular jjwt
  0.12.3), javax.* to jakarta.* across main and test sources, Spring Security 6
  (SecurityFilterChain bean, lambda DSL, @EnableMethodSecurity, requestMatchers), RestTemplate
  to RestClient, and Hibernate 6 query/type changes. Scripts do the deterministic rewrites and
  the grep-style verification; the agent hand-refactors what can't be rewritten mechanically,
  then compiles and tests on Java 21.

trigger_when:
  - Upgrading or migrating a Spring Boot 2.x project (spring-boot-starter-parent 2.x) to Spring Boot 3.x.
  - A project must move from Java 8/11 to Java 17/21 together with a Spring Boot upgrade.
  - Code still uses javax.persistence, javax.validation or javax.servlet imports, WebSecurityConfigurerAdapter, @EnableGlobalMethodSecurity, antMatchers, RestTemplate, or javax.xml.bind:jaxb-api / jjwt 0.9.x.
  - Compilation fails after bumping the Spring Boot parent to 3.x.

do_not_use_when:
  - The project is not Spring Boot (plain Jakarta EE / Quarkus / Micronaut) or is already fully on Boot 3 with no javax EE imports or deprecated security/HTTP-client code.
  - The task is a Spring Boot 3.x to 4.x upgrade or a reactive WebFlux rewrite.

steps:
  - name: scan-project
    kind: execution
    description: Inventory the project (poms, Boot/Java versions, dependencies, javax EE usage, security, RestTemplate, Hibernate patterns, Maven/JDKs available) and list every migration issue before any edit.
    inputs:
      - name: project_dir
        type: string
        description: Absolute path to the project root holding pom.xml (in the task container usually /workspace).
    script: scripts/scan.py
    assets:
      - assets/config.json
    inputs_to: apply-rewrites

  - name: apply-rewrites
    kind: execution
    description: Apply the deterministic Boot 3 edits in place (pom parent/java/JAXB/jjwt, javax->jakarta EE packages, EnableMethodSecurity, requestMatchers, authorizeHttpRequests, HQL update-from), then re-scan and return what is left.
    inputs:
      - name: project_dir
        type: string
      - name: inventory
        type: object
        description: Project inventory from scan-project.
      - name: initial_issues
        type: list[*]
        description: Issues found before any edit.
    script: scripts/apply_rewrites.py
    assets:
      - assets/config.json
    inputs_to: refactor-code

  - name: refactor-code
    kind: client_task
    description: Hand-refactor what scripts cannot rewrite safely (SecurityFilterChain, RestClient, Hibernate 6 APIs, jjwt 0.12, leftovers), guided by remaining_issues.
    inputs:
      - name: project_dir
        type: string
      - name: changes
        type: list[*]
        description: Edits apply-rewrites made (file, rule, count/detail).
      - name: remaining_issues
        type: list[*]
        description: Open issues with id, area, severity (blocking/advisory), file, line, match and fix.
    template: assets/refactor-task.md
    references:
      - path: references/security-6.md
        description: Spring Security 6 full before/after SecurityConfig, change table (adapter, AuthenticationManager, lambda DSL, matchers, exception handling, headers), pitfalls, verification greps. Load for any issue with area security.
      - path: references/restclient.md
        description: RestTemplate to RestClient conversions for GET, POST with headers, exchange, DELETE, complete service with @Value base URL, RestClient bean, onStatus error handling, ParameterizedTypeReference. Load for any issue with area http-client.
      - path: references/hibernate-6.md
        description: Hibernate 6 breaking changes (HQL update-from, distinct join fetch, legacy Criteria, @Type/@TypeDef, ID generation, dialects, properties, troubleshooting). Load for any issue with area hibernate.
      - path: references/jakarta-namespace.md
        description: javax to jakarta package table, JDK javax packages that must stay, affected annotations, XML descriptor namespaces, manual sed/grep fallback, OpenRewrite recipe. Load for any issue with area jakarta or if scripts could not run.
      - path: references/boot-3-build.md
        description: pom changes (parent, java.version, JAXB removal, jjwt 0.12 deps and API changes, third-party Jakarta swaps), common issues (H2 dialect, actuator, property renames), manual pom commands, OpenRewrite, verification. Load for any issue with area build or jwt.
    inputs_to: verify-static

  - name: verify-static
    kind: execution
    description: Re-scan the edited project; verify_passed is true only when no blocking issue remains (no javax EE imports, no adapter/old annotations/matchers/chained DSL, no RestTemplate, pom on Boot 3/Java 17+ without JAXB or jjwt 0.9).
    inputs:
      - name: project_dir
        type: string
      - name: refactor_notes
        type: string
        description: What refactor-code changed per file, plus waived issue ids with reasons.
    script: scripts/verify.py
    assets:
      - assets/config.json
    inputs_to: static-gate

  - name: static-gate
    kind: router
    description: Blocking issues left go back to refactor-code with the fresh remaining_issues; a clean scan moves on to compile and test.
    branch_on: verify_passed
    branches:
      "true": build-and-test
      "false": refactor-code

  - name: build-and-test
    kind: client_task
    description: Compile and run the test suite on Java 21 with Maven, fixing small migration errors along the way, and report the result.
    inputs:
      - name: project_dir
        type: string
      - name: verify_passed
        type: boolean
      - name: static_checks
        type: object
        description: Final static facts from verify-static (versions, security/RestClient/jakarta presence).
    template: assets/build-task.md
    references:
      - path: references/boot-3-build.md
        description: Container build setup (SDKMAN, Java 21, Maven, offline caveat) and dependency facts. Load before running Maven.
      - path: references/security-6.md
        description: Load when a compile or test error is in security configuration.
      - path: references/restclient.md
        description: Load when a compile error is in RestClient code.
      - path: references/hibernate-6.md
        description: Load when startup or tests fail on entity mapping, query parsing or dialect.
      - path: references/jakarta-namespace.md
        description: Load when errors mention javax/jakarta classes that cannot be found.
    inputs_to: build-outcome

  - name: build-outcome
    kind: decision
    description: Classify the build/test report so code problems loop back for fixing and environment limits end the run with an honest report.
    inputs:
      - name: build_report
        type: string
        description: Commands run, JDK/Maven versions, compile and test results, first error verbatim, files changed.
    questions:
      build_outcome:
        type: choice
        instructions: >
          What does the report show about the migrated code? Judge from the actual Maven output
          in the report, not from intentions. A run that never reached compilation because
          artifacts could not be downloaded says nothing about the code.
        criteria:
          passed: mvn compile succeeded and mvn test ran with zero failures and zero errors.
          code_errors: Compilation failed, the Spring context failed to start, or tests failed or errored because of the project's code or configuration (missing import, wrong API, bad query, mapping or security error).
          environment_blocked: Maven or the JDK could not run, or dependencies could not be resolved or downloaded (offline, repository unreachable), so the code could not be judged; the static verification is the best available evidence.
    thresholds:
      build_outcome: 0.7
    inputs_to: outcome-gate

  - name: outcome-gate
    kind: router
    description: Code errors go back to refactor-code (the build_report travels in the state); passed or environment-blocked runs end.
    branch_on: build_outcome
    branches:
      passed: end
      environment_blocked: end
      code_errors: refactor-code

  - name: end
    kind: end
    description: The project migrated in place to Spring Boot 3 / Java 21, with the edit log, remaining advisories and the build verdict.
    inputs:
      - name: project_dir
        type: string
      - name: changes
        type: list[*]
        description: Automated edits applied.
      - name: refactor_notes
        type: string
      - name: remaining_issues
        type: list[*]
        description: Issues left after the last verification (advisory only when verify_passed).
      - name: build_report
        type: string
      - name: build_outcome
        type: string
        description: passed or environment_blocked.

anti_patterns:
  - Rewriting JDK javax packages (javax.sql, javax.crypto, javax.net, javax.transaction.xa, javax.xml.parsers, javax.annotation.processing) or JSR-305 javax.annotation.Nonnull to jakarta; they do not exist under jakarta.
  - Bumping the parent to 3.x while leaving javax.xml.bind:jaxb-api or jjwt 0.9.1 in the pom; the old JAXB API conflicts with Jakarta and breaks the build at runtime.
  - Swapping @EnableGlobalMethodSecurity in the annotation but not the import, or deleting it entirely while @PreAuthorize is still used; method security then silently stops being enforced.
  - Keeping the chained security DSL (.csrf().disable().and()...) or calling .authorizeHttpRequests() with no lambda; it is deprecated and verification treats it as unmigrated.
  - Dropping or reordering authorization rules (e.g. the POST /api/users permitAll, h2-console frame options, the 401 entry point) while rewriting SecurityConfig.
  - Leaving comments or Javadoc that still name WebSecurityConfigurerAdapter or RestTemplate; grep-based checks match comments too.
  - Turning regexMatchers into requestMatchers with the same string; requestMatchers(String) is an ant/mvc pattern, not a regex.
  - Passing a field-injected @Value baseUrl into RestClient.builder() inside the constructor, where it is still null; keep RestClient.create() and build the full URI per call, or inject a configured RestClient bean.
  - Adding WebFlux just to replace RestTemplate; RestClient is the synchronous replacement in servlet apps.
  - Running Maven on the container's Java 8 (or skipping tests, deleting tests, downgrading versions) to get a green build.
  - Forgetting test sources; they need the same javax to jakarta migration.
```

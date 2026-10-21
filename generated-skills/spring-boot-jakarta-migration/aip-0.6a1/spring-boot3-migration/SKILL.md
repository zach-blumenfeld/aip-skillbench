---
name: spring-boot3-migration
description: Migrate a Maven Spring Boot 2.x / Java 8 service to Spring Boot 3.2.x / Java 21. Covers pom upgrade (parent 3.2, java.version 21, remove javax.xml.bind jaxb-api, jjwt 0.9.1 to modular 0.12.3), javax to jakarta namespace (persistence, validation, servlet), Hibernate 6 compatibility, Spring Security 6 (WebSecurityConfigurerAdapter to SecurityFilterChain, @EnableGlobalMethodSecurity to @EnableMethodSecurity, antMatchers to requestMatchers, lambda DSL), RestTemplate to RestClient, then mvn clean compile and mvn test until green. Use for any Spring Boot 2 to 3 / Jakarta EE upgrade task.
metadata:
  aip-version: "0.6a1"
---

# AIP runtime — format 0.6a1

You are executing an Agent Instruction Protocol (AIP) procedure: the fenced YAML block in this skill's `SKILL.md`. AIP is a protocol for cheaply, quickly, and accurately executing multi-step tasks as a graph of typed steps. You drive the run and execute every step yourself, following the semantics below.

Critical terminology:

- **Client**: you, the agent running this procedure; the `client_task` step kind is named for it. You supply each step's input, run its script, answer its questions by your own judgment, perform its task, follow its router, and make the final call at every step.
- **State**: the one JSON object a run carries. Each step declares the keys it reads as `inputs`; `execution` and `client_task` steps declare the keys they add as `outputs`, and a `decision` adds one key per question.
- **Step kinds**: `execution` runs a script, `decision` asks typed questions about the state, `client_task` hands work to you, `router` branches on a value in the state, `end` declares the procedure's result.

## Execution

The state starts as the start step's `inputs` and flows along `inputs_to`; each step adds its outputs to it. Every key is produced by exactly one step, so keys accumulate and nothing is overwritten. A step runs only if the state holds every key it declares in `inputs`, with the declared types; check that before each step. A step sees only those keys: give it its declared `inputs` and nothing else from the state. You have the final say at every step.

- **`execution`**: before the first one, check that this machine has everything `requires` names (the interpreter at its minimum version, the packages, the tools); if anything is missing, stop and name all of it. Run `script` from its folder, launched with the step's `command` when it has one and `python <script>` otherwise, with one JSON object on stdin, `{"state": <the step's inputs>, "assets": {<file stem>: <content>}, "expects": <the next step's inputs>}`. The script writes one JSON object to stdout holding exactly the step's `outputs`; add them to the state. A non-zero exit, or output missing a declared key, fails the step: stop there and report it rather than doing the step by hand.
- **`decision`**: answer each question from the step's inputs, and from the run so far only when the step sets `history: true`. Each answer collapses to one value under its question name and is added to the state: a noul to `true`/`false`, a choice to its label, a score to its level number. `thresholds` name the questions where an uncertain answer matters most; when your answer to one is a close call, reconsider it before continuing.
- **`client_task`**: render `template` with `{key}` from the step's inputs, `{assets[stem]}` for its assets, and `{meta.name}` for the skill name. Perform the task, loading `references` if their descriptions apply, and produce the step's `outputs`; add them to the state.
- **`router`**: read the state's `branch_on` key and continue at `branches[value]`. A value with no branch is an error.
- **`end`**: the state must hold `end`'s `inputs`. Those keys are the procedure's result.

```yaml
purpose: >
  Migrate a Maven Spring Boot 2.x (Java 8/11) application in place to Spring Boot 3.2.x on Java 21,
  and finish with `mvn clean compile` and `mvn test` passing and no legacy patterns left. A script makes
  every deterministic rewrite: parent and Java versions, removal of JAXB and activation, jjwt to
  modular 0.12.3, javax to jakarta for Jakarta EE packages only, Security 6 renames, Hibernate 6 HQL,
  dialect names and artifact coordinates. It also inventories what still needs hand edits. Routers
  send the agent only to the rewrites the project needs: SecurityFilterChain, RestClient, and removed
  Hibernate, jjwt or Spring APIs. A verify script runs the two Maven commands and checks for
  remaining legacy patterns. If anything is left, a fix loop runs.

trigger_when:
  - A task asks to upgrade or migrate a Spring Boot 2.x (often 2.7.x) project to Spring Boot 3.x, or Java 8/11 to 17/21.
  - Compilation fails after a Boot 3 bump with javax.persistence, javax.validation or javax.servlet errors, or a missing WebSecurityConfigurerAdapter or EnableGlobalMethodSecurity.
  - A task asks to replace RestTemplate with RestClient, update to Spring Security 6, or ensure Hibernate 6 compatibility in a Spring Boot service.

do_not_use_when:
  - The project builds with Gradle only (no pom.xml). The scripts handle Maven; apply the references by hand instead.
  - The project is already on Spring Boot 3.x and only needs a minor 3.x bump.
  - The target is a reactive WebFlux rewrite. RestClient is synchronous; use WebClient there.

requires:
  interpreter:
    name: bash
    version: "3.2"
  tools:
    - perl
    - grep
    - find
    - cksum
    - mktemp
    - java
    - mvn

steps:
  - name: apply-mechanical
    kind: execution
    description: >
      Rewrite every pom.xml: spring-boot-starter-parent 2.x to 3.2.0; java.version and compiler
      source/target/release to 21; remove javax.xml.bind:jaxb-api, com.sun.xml.bind jaxb-impl and
      jaxb-core, javax.activation; jjwt 0.9.x to jjwt-api plus runtime jjwt-impl and jjwt-jackson
      0.12.3; javax EE artifacts and org.hibernate:hibernate-core to their Jakarta or
      org.hibernate.orm coordinates; old Lombok left to Boot. Rewrite every .java file (main and
      test): Jakarta EE javax.* to jakarta.*, keeping JDK javax.sql, crypto, net, naming,
      transaction.xa and annotation.processing; @EnableGlobalMethodSecurity to @EnableMethodSecurity;
      antMatchers and mvcMatchers to requestMatchers; authorizeRequests to authorizeHttpRequests;
      HQL "update from X" to "update X". Rewrite resources: versioned Hibernate dialects to Hibernate
      6 names, javax.persistence keys and the persistence.xml namespace. Then inventory what is left.
      Idempotent.
    inputs:
      - name: workspace
        type: string
        description: Absolute path to the Maven project root that holds pom.xml (for example /workspace).
    script: scripts/migrate.sh
    command: ["bash", "migrate.sh", "apply"]
    timeout: 300
    outputs:
      - name: baseline
        type: object
        description: Spring Boot and java.version before and after, and the count of Java files.
      - name: mechanical_changes
        type: list[*]
        description: One "file - change" line per rewrite applied.
      - name: security_findings
        type: list[*]
        description: Lines of the form file:line - code that still need a hand-written Security 6 rewrite.
      - name: rest_template_findings
        type: list[*]
        description: Lines of the form file:line - code that use RestTemplate, RestTemplateBuilder or AsyncRestTemplate.
      - name: legacy_api_findings
        type: list[*]
        description: Removed Hibernate 5, jjwt 0.9 or Spring 5 APIs, wildcard javax imports, old dialect or property names, and spring.factories auto-config.
      - name: pom_review
        type: list[*]
        description: Dependencies to review by hand, such as springfox, javax artifacts, pinned Spring versions, old jjwt or Spring Cloud.
      - name: needs_security_rewrite
        type: boolean
        description: True when security_findings is non-empty.
      - name: uses_rest_template
        type: boolean
        description: True when rest_template_findings is non-empty.
      - name: needs_legacy_api_rewrite
        type: boolean
        description: True when legacy_api_findings or pom_review is non-empty.
    inputs_to: route-security

  - name: route-security
    kind: router
    description: Rewrite the security configuration only if adapter-style or chained-DSL code remains.
    branch_on: needs_security_rewrite
    branches:
      "true": rewrite-security
      "false": route-rest-client

  - name: rewrite-security
    kind: client_task
    description: Replace WebSecurityConfigurerAdapter and chained DSL with SecurityFilterChain and AuthenticationManager beans in the lambda DSL, keeping every rule.
    inputs:
      - name: workspace
        type: string
      - name: security_findings
        type: list[*]
    template: assets/rewrite-security.md
    references:
      - path: references/spring-security-6.md
        description: Full Security 5 to 6 before/after for this kind of config (csrf, stateless session, entry point, permitAll matchers, H2 frame options), lambda DSL, matcher changes, and gotchas (multiple-servlet requestMatchers fallback, regexMatchers, rule order). Load for every security rewrite.
    outputs:
      - name: security_changes
        type: string
        description: Files changed and what each now contains.
    inputs_to: route-rest-client

  - name: route-rest-client
    kind: router
    description: Migrate HTTP clients only if RestTemplate is still used.
    branch_on: uses_rest_template
    branches:
      "true": migrate-restclient
      "false": route-legacy-apis

  - name: migrate-restclient
    kind: client_task
    description: Replace RestTemplate with RestClient, keeping every public method's signature and error behaviour.
    inputs:
      - name: workspace
        type: string
      - name: rest_template_findings
        type: list[*]
    template: assets/migrate-restclient.md
    references:
      - path: references/restclient-migration.md
        description: RestTemplate to RestClient before/after for GET, POST with headers, exchange, DELETE, configured beans, status handlers and ParameterizedTypeReference, plus gotchas (@Value is null in constructors, terminal call required). Load for every RestClient migration.
    outputs:
      - name: restclient_changes
        type: string
        description: Each migrated class and method.
    inputs_to: route-legacy-apis

  - name: route-legacy-apis
    kind: router
    description: Fix removed Hibernate, jjwt or Spring APIs and pom review items only if any were found.
    branch_on: needs_legacy_api_rewrite
    branches:
      "true": fix-legacy-apis
      "false": verify

  - name: fix-legacy-apis
    kind: client_task
    description: Port removed Hibernate 5, jjwt 0.9 and Spring 5 APIs and resolve the pom review items.
    inputs:
      - name: workspace
        type: string
      - name: legacy_api_findings
        type: list[*]
      - name: pom_review
        type: list[*]
    template: assets/fix-legacy-apis.md
    references:
      - path: references/hibernate-6.md
        description: Hibernate 5 to 6 changes (ID generation, dialects, stricter JPQL/HQL, update-from, distinct, Criteria API removal, @Type/@TypeDef to @JdbcTypeCode, fetch strategies, properties, N+1 monitoring). Load for any Hibernate finding.
      - path: references/jjwt-0.12.md
        description: jjwt 0.9 to 0.12 API mapping (parser builder, verifyWith, parseSignedClaims, Keys.hmacShaKeyFor, Decoders) and weak-key gotcha. Load only when Java code imports io.jsonwebtoken.
      - path: references/boot3-pom-and-jakarta.md
        description: Spring Boot 3 pom rules (JAXB removal, jjwt, OpenRewrite alternative, migration order and checklist), the full javax to jakarta package table and pitfalls, and common Boot 3 compile and test failures. Load for Spring/pom findings.
    outputs:
      - name: legacy_api_changes
        type: string
        description: Per-file changes, and the findings that needed none.
    inputs_to: verify

  - name: verify
    kind: execution
    description: >
      In the workspace, run `mvn -B clean compile`, then (if compile passes) `mvn -B test`, on the
      java on PATH (reported; 17+ required, 21 targeted). Check for remaining legacy patterns:
      parent not 3.2.x, java.version not 21, jaxb-api, javax.xml.bind or monolithic jjwt in the pom,
      javax EE imports, WebSecurityConfigurerAdapter, @EnableGlobalMethodSecurity, antMatchers,
      authorizeRequests, authenticationManagerBean, chained security DSL, RestTemplate, HQL "update
      from", legacy Criteria and @Type/@TypeDef, @PreAuthorize without @EnableMethodSecurity, @Entity
      without jakarta.persistence, and @EnableWebSecurity without @Configuration.
    inputs:
      - name: workspace
        type: string
    script: scripts/migrate.sh
    command: ["bash", "migrate.sh", "verify"]
    timeout: 1800
    outputs:
      - name: verify_report
        type: object
        description: JDK and Maven versions, compile and test exit codes, tests summary, first compile and test errors, residual issues, and the log directory.
      - name: migration_complete
        type: boolean
        description: True only when compile and test both exit 0 and no residual issue remains.
    inputs_to: route-build

  - name: route-build
    kind: router
    description: Finish when the build is green and clean, otherwise enter the fix loop.
    branch_on: migration_complete
    branches:
      "true": end
      "false": fix-build

  - name: fix-build
    kind: client_task
    description: Fix compile errors, test failures and residual legacy patterns, re-running mvn clean compile and mvn test until both pass.
    inputs:
      - name: workspace
        type: string
      - name: verify_report
        type: object
    template: assets/fix-build.md
    references:
      - path: references/boot3-pom-and-jakarta.md
        description: Common Boot 3 compile and test failures (wrong JDK, HttpStatusCode, removed adapters, renamed properties, bean wiring), pom rules and the javax to jakarta table. Load first for any build failure.
      - path: references/spring-security-6.md
        description: Security 6 config patterns and gotchas. Load when errors or residuals mention security classes.
      - path: references/restclient-migration.md
        description: RestClient patterns. Load when residuals mention RestTemplate or errors are in HTTP client code.
      - path: references/hibernate-6.md
        description: Hibernate 6 changes. Load for JPQL/HQL, mapping or type errors.
      - path: references/jjwt-0.12.md
        description: jjwt 0.12 API. Load for io.jsonwebtoken compile errors.
    outputs:
      - name: build_fixes
        type: string
        description: What was wrong and what changed.
      - name: final_build_status
        type: string
        description: The last mvn clean compile and mvn test results.
    inputs_to: end

  - name: end
    kind: end
    description: The migrated workspace, with the baseline, the mechanical changes and the verify report. On the fix path, verify_report is the pre-fix state.
    inputs:
      - name: workspace
        type: string
      - name: baseline
        type: object
      - name: mechanical_changes
        type: list[*]
      - name: verify_report
        type: object

anti_patterns:
  - Running a blanket javax to jakarta replace. javax.sql, javax.crypto, javax.net, javax.naming, javax.security.auth, javax.xml.parsers and transform, javax.transaction.xa and javax.annotation.processing are JDK packages and must stay javax.
  - Keeping javax.xml.bind:jaxb-api "for safety". It conflicts with Jakarta XML Binding; if code really needs XML binding, use jakarta.xml.bind-api plus org.glassfish.jaxb:jaxb-runtime.
  - Leaving jjwt 0.9.1 in place, or adding only jjwt-api without runtime jjwt-impl and jjwt-jackson.
  - Rewriting the security config from memory and dropping a matcher, an HTTP method qualifier, the entry point or the frame-options setting. Translate rule by rule, in order.
  - Turning regexMatchers into requestMatchers by a plain rename. requestMatchers(String) is a path pattern, not a regex.
  - Migrating RestTemplate by changing method signatures, return values or exception swallowing, removing the no-arg constructor, or reading @Value fields inside the constructor.
  - Ending a RestClient chain at retrieve() without body(), toEntity() or toBodilessEntity(). No request is sent.
  - Getting a green build by deleting, disabling or weakening tests, by pinning Spring Boot back to 2.x, or by lowering java.version below 21.
  - Running Maven on Java 8. Spring Boot 3 needs JDK 17+, and the container's default java (21) is the one to use.
  - Stopping at a green build while verify still reports residual RestTemplate, chained DSL, javax imports or old dependencies. The task also requires the API migration itself.
```

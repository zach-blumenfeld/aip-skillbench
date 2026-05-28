---
name: senior-java
description: >-
  Enterprise Java and Spring Boot development toolkit for building, securing, and
  tuning production applications, microservices, and cloud-native systems. Six
  runnable generators (Spring Boot project scaffolder, JPA entity stack, REST
  endpoints, Spring Security config, Maven/Gradle dependency vulnerability
  analyzer, JVM/JPA performance profiler) plus reference guides for Spring Boot
  3.x, Spring Cloud microservices, JPA/Hibernate, Spring Security, and JVM
  performance. Use when starting a Spring Boot project or microservice;
  implementing JPA/Hibernate data layers; designing REST APIs (Spring MVC or
  WebFlux); setting up JWT/OAuth2 authentication, RBAC, or method security;
  auditing Maven/Gradle dependencies for CVEs and outdated versions; profiling
  JVM/query performance; or reviewing Java code for enterprise patterns. Targets
  Java 17/21, Spring Boot 3.x, Spring Framework 6.x, Spring Cloud, Spring Data
  JPA, Hibernate, Maven/Gradle.
compatibility: >-
  Skill scripts are pure Python 3.8+ (standard library only, no external
  dependencies) and run on macOS, Linux, and Windows. Generated code targets
  Java 17/21 LTS, Spring Boot 3.x, and Maven (the scaffolder emits pom.xml).
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a2/assets/aip-schemas/procedure.schema.json
  author: Claude Skills Team
  version: v1.0.0
license: MIT
---

```yaml
purpose: >
  Production-grade Java/Spring Boot development capability, organized as a
  toolkit of six runnable generators/analyzers plus five reference guides. It
  covers the full lifecycle: scaffold a Spring Boot 3.x project (layered
  architecture, profiles, Docker, CI/CD), generate JPA entity stacks and REST
  endpoints, wire Spring Security (JWT/OAuth2/RBAC/method security), audit
  Maven/Gradle dependencies for known CVEs and outdated versions, and profile
  JVM/JPA performance for N+1 queries and tuning. Beyond general agent
  knowledge it adds the runnable generators (so boilerplate is consistent and
  correct rather than hand-written each time), a dependency vulnerability table
  with severity-coded exit codes, a static query-performance scanner, and
  reference guides that encode the Spring Boot / JPA / Security / microservices
  / performance patterns and pitfalls. Apply it by classifying the development
  need, running the matching generator or analyzer, then hardening the result
  against the relevant reference's best practices and quality bars.

trigger_when:
  - Starting a new Spring Boot project or microservice (monolith, microservice, or reactive WebFlux).
  - Implementing a JPA/Hibernate data layer — entities, repositories, services, DTOs, mappers.
  - Designing REST APIs with Spring MVC or WebFlux (CRUD endpoints, validation, pagination, OpenAPI docs, RFC 7807 error handling).
  - Setting up authentication/authorization — JWT, OAuth2 resource server, role-based access control, @PreAuthorize/@PostAuthorize method security.
  - Auditing Maven (pom.xml) or Gradle (build.gradle) dependencies for known CVEs, outdated versions, or upgrade paths.
  - Profiling JVM applications or JPA query performance (N+1 detection, fetch strategy, GC/heap/connection-pool tuning).
  - Reviewing or hardening Java/Spring code for enterprise patterns, security checklist items, and performance anti-patterns.
  - User mentions Spring Boot, Spring Cloud, JPA, Hibernate, Spring Security, JWT, OAuth2, microservices, WebFlux, Maven, or Gradle.

do_not_use_when:
  - The work is not Java/JVM — these generators emit Java + Spring Boot 3.x + Maven and the references are Spring-specific.
  - You need a non-Spring Java framework (Quarkus, Micronaut, Jakarta EE without Spring); the patterns and generated code assume Spring.
  - The task is a one-off script or algorithm with no project/web/data-layer/security/perf dimension.

scope_and_approval: >
  The generators write files to disk: spring_project_scaffolder.py creates a new
  project directory tree, entity_generator.py and security_config_generator.py
  (with --output) write package files, api_endpoint_generator.py writes a
  controller (or prints to stdout without --output). Run them into a fresh or
  intended output directory and review the generated code before integrating it
  into an existing repository — they scaffold opinionated defaults, not a
  finished feature. dependency_analyzer.py and performance_profiler.py are
  read-only: they parse/scan and report, changing nothing, and signal severity
  through exit codes (2 = critical, 1 = high). Editing existing source files,
  running Maven/Gradle builds, and deploying artifacts are write actions —
  follow the host task's approval and verification norms for those.

steps:
  - name: classify-need
    description: >
      Determine which capabilities the task requires — most tasks use a subset,
      not all. Map the need to one or more of: new project (scaffold), data
      layer (entity stack), API surface (REST endpoints), auth (security
      config), dependency hygiene (vulnerability audit), or performance
      (profiler). Capture the constraints the generators take as flags: project
      type (microservice/monolith/reactive), database
      (postgresql/mysql/mongodb/h2), Java version (17/21), auth method
      (jwt/oauth2/basic), base package, and build tool. Treat the remaining
      generation/analysis steps as options invoked as the need calls for them,
      not a mandatory pipeline.
    outputs:
      - name: need-spec
        type: object
        description: The required capabilities plus project-type / database / java-version / security / package constraints.
  - name: scaffold-project
    description: >
      Generate a production-ready Spring Boot 3.x project skeleton when the need
      is a new service. Emits Maven pom.xml, profile-based application.yml
      (dev/prod), main class, OpenAPI config, exception handling
      (ResourceNotFoundException + ErrorResponse + GlobalExceptionHandler),
      optional security scaffolding, Dockerfile, docker-compose.yml, and a
      GitHub Actions CI/CD workflow. Layered package layout
      (config/controller/service/repository/entity/dto/mapper/exception).
    script: scripts/spring_project_scaffolder.py
    depends_on: [classify-need]
    inputs:
      - name: need-spec
        type: object
    outputs:
      - name: project-path
        type: string
        description: Root directory of the generated project.
  - name: generate-entity-stack
    description: >
      Generate a complete JPA entity stack from a field/relation spec: entity
      (Lombok, optional audit fields and soft-delete), Spring Data repository
      (JpaRepository + JpaSpecificationExecutor), transactional service, REST
      controller with OpenAPI + validation, DTO with Jakarta validation, and a
      MapStruct mapper. Field syntax is name:Type[:modifiers] (e.g.
      id:Long,email:String:unique); relations are field:RelationType
      (ManyToOne/OneToMany/ManyToMany/OneToOne).
    script: scripts/entity_generator.py
    depends_on: [classify-need]
    inputs:
      - name: need-spec
        type: object
    outputs:
      - name: entity-files
        type: list[string]
        description: Generated entity/repository/service/controller/dto/mapper file paths.
  - name: generate-rest-endpoints
    description: >
      Scaffold a standalone REST controller for a resource when you need the API
      surface without the full entity stack. Choose HTTP methods
      (GET,POST,PUT,PATCH,DELETE) and optionally --paginated; emits OpenAPI
      @Operation annotations, @Valid request bodies, and Page/Pageable wiring.
      Prints to stdout unless --output is given.
    script: scripts/api_endpoint_generator.py
    depends_on: [classify-need]
    inputs:
      - name: need-spec
        type: object
    outputs:
      - name: controller-code
        type: string
  - name: generate-security-config
    description: >
      Generate Spring Security configuration for the chosen auth method. --type
      jwt emits a Role enum, SecurityConfig (stateless, CORS, CSRF disabled for
      APIs), JwtAuthenticationEntryPoint, AuthController, and auth DTOs; --type
      oauth2 (with --issuer-uri) emits a resource-server SecurityConfig and the
      application-security.yml. Method security (@EnableMethodSecurity) is
      enabled so @PreAuthorize/@PostAuthorize work.
    script: scripts/security_config_generator.py
    depends_on: [classify-need]
    inputs:
      - name: need-spec
        type: object
    outputs:
      - name: security-files
        type: list[string]
  - name: audit-dependencies
    description: >
      Scan a Maven pom.xml or Gradle build.gradle for known-vulnerable
      dependencies (e.g. log4j-core CVE-2021-44228, jackson-databind
      CVE-2019-12086, spring-core CVE-2022-22965) and outdated versions, with
      upgrade recommendations. Read-only; exits 2 if any CRITICAL vuln is found,
      1 if any HIGH — treat a non-zero exit as a gate, not advisory. This is the
      runnable form of the "dependencies scanned for vulnerabilities" security
      checklist item. Caveat: it matches against a small static CVE table and
      only counts dependencies it can parse (the file must be named pom.xml /
      build.gradle, and it under-counts namespaced Maven POMs — including the
      ones spring_project_scaffolder.py emits — reporting 0 deps), so a clean
      run is necessary but NOT sufficient. A non-zero exit is authoritative;
      exit 0 is not proof of zero CVEs — corroborate critical dependencies
      against an authoritative source (OSV/NVD).
    script: scripts/dependency_analyzer.py
    depends_on: [classify-need]
    inputs:
      - name: need-spec
        type: object
    outputs:
      - name: vuln-report
        type: object
        description: Dependencies, vulnerabilities (count/critical/high/issues), and available updates; markdown or JSON.
  - name: profile-performance
    description: >
      Statically scan a Java source directory (--analyze-queries DIR) for
      JPA/query performance issues — potential N+1 from collection relationships,
      EAGER fetch, repositories missing @EntityGraph, unbounded findAll() without
      Pageable, and finder methods that imply needed indexes — and emit JVM
      tuning recommendations (heap, G1GC, tiered compilation, GC logging,
      HikariCP). Read-only; exits 2 on critical, 1 on high. (The shipped script
      supports --analyze-queries; it does not implement a live --profile mode.)
      The scan is heuristic and pattern-based — read the flagged files to
      confirm, and note it may surface an N+1 risk indirectly (e.g. as an
      EAGER_FETCH or UNBOUNDED_QUERY finding rather than a POTENTIAL_N1_QUERY).
    script: scripts/performance_profiler.py
    depends_on: [classify-need]
    inputs:
      - name: need-spec
        type: object
    outputs:
      - name: perf-report
        type: object
        description: Issues by severity, database/index recommendations, and JVM optimization recommendations.
  - name: harden-and-apply-best-practices
    description: >
      Generated code is an opinionated starting point, not a finished feature —
      harden it against the relevant reference before shipping. Externalize
      config with profiles and ${VAR:default} (never hardcode secrets); validate
      every controller input with Jakarta annotations; return RFC 7807 problem
      details via a global handler; put @Transactional on write service methods
      and keep queries readOnly; prefer LAZY fetch with @EntityGraph/fetch joins
      over EAGER; paginate unbounded queries; disable open-in-view in production;
      never block inside a WebFlux reactive pipeline. Load the matching reference
      (see search_shortcuts) for the concrete patterns.
    depends_on: [scaffold-project, generate-entity-stack, generate-rest-endpoints, generate-security-config]
    inputs:
      - name: project-path
        type: string
        nullable: true
  - name: verify-quality
    description: >
      Check the result against the skill's quality bars before declaring done:
      80%+ test coverage on business logic (60%+ overall), 100% OpenAPI coverage
      of public endpoints, zero critical/high dependency vulnerabilities, and a
      P99 latency target under ~200ms for CRUD. Re-run audit-dependencies until
      it exits 0 (no critical/high), and re-run profile-performance after fetch
      changes to confirm the N+1/unbounded-query findings are resolved. The
      coverage and latency numbers are targets to design toward, not values this
      skill computes.
    depends_on: [harden-and-apply-best-practices, audit-dependencies, profile-performance]

search_shortcuts:
  - category: Capability tools (scripts/)
    body: >
      spring_project_scaffolder.py NAME --type {microservice|monolith|reactive}
      --db {postgresql|mysql|mongodb|h2} [--security {jwt|oauth2|basic}] [--java
      {17|21}] [--group-id ...] [--output DIR] [--no-docker] [--no-ci] [--json]
      — full project skeleton. entity_generator.py NAME --fields
      "name:Type[:modifiers],..." [--relations "field:RelType,..."] [--package
      ...] [--auditable] [--soft-delete] [--output DIR] [--json] — entity +
      repository + service + controller + DTO + MapStruct mapper.
      api_endpoint_generator.py RESOURCE [--methods GET,POST,PUT,PATCH,DELETE]
      [--paginated] [--package ...] [--output FILE] [--json] — standalone REST
      controller. security_config_generator.py --type {jwt|oauth2} [--roles
      A,B] [--issuer-uri URL] [--package ...] [--output DIR] [--json] — Spring
      Security config. dependency_analyzer.py {pom.xml|build.gradle}
      [--check-security] [--output FILE] [--json] — CVE + outdated scan, exit
      2/1 on critical/high. performance_profiler.py --analyze-queries DIR
      [--output FILE] [--json] — static JPA/query scan + JVM tips, exit 2/1.
      Every script supports --help and --json.
  - category: Spring Boot patterns — references/spring-boot-best-practices.md
    body: >
      Load when scaffolding or reviewing a Spring Boot app. Covers layered
      package structure, profile-based application.yml (dev/prod) and
      ${VAR:default} secrets, REST controller structure, the HTTP status-code
      table, RFC 7807 ProblemDetail error format, Jakarta request validation and
      custom validators, the @RestControllerAdvice global exception handler,
      unit (Mockito) and integration (MockMvc + Testcontainers) testing, actuator
      / health-indicator / logging production setup, and a security checklist
      (HTTPS, CORS, CSRF, input validation, SQL-injection prevention, rate
      limiting, externalized secrets, dependency scanning).
  - category: Microservices & Spring Cloud — references/microservices-patterns.md
    body: >
      Load for microservice decomposition and Spring Cloud wiring. Covers DDD
      bounded contexts and decomposition strategies, Eureka service discovery,
      Spring Cloud Gateway routing, Config Server, synchronous OpenFeign clients
      with fallbacks, async RabbitMQ/Kafka events, Resilience4j circuit
      breaker/retry/timelimiter/bulkhead, Micrometer+Zipkin distributed tracing,
      choreography and orchestration sagas, event sourcing, CQRS, and
      blue-green/canary deployment.
  - category: JPA/Hibernate data layer — references/jpa-hibernate-guide.md
    body: >
      Load when designing entities/repositories or fixing query performance.
      Covers entity design (@Version optimistic locking, audit fields),
      One-to-Many/Many-to-One/Many-to-Many mappings with bidirectional helpers,
      repository patterns, Specifications for dynamic queries, the three N+1
      fixes (@EntityGraph, fetch join, @BatchSize/default_batch_fetch_size),
      interface and DTO projections, first/second-level + query caching,
      transaction management (propagation, isolation, readOnly), proper
      indexing, and the common-pitfalls list.
  - category: Spring Security — references/spring-security-reference.md
    body: >
      Load when implementing auth. Covers the JWT SecurityFilterChain,
      JwtTokenProvider (access/refresh tokens, claims, validation),
      OncePerRequestFilter auth filter, OAuth2 resource-server config + issuer/
      jwk-set-uri yaml, RBAC (Role/User entities implementing UserDetails),
      method security (@PreAuthorize/@PostAuthorize/@PostFilter with SpEL and
      custom @bean security expressions), @WithMockUser security tests, and a
      security best-practices checklist (bcrypt 12+, short-lived tokens, refresh,
      rate limiting, secure headers, secret rotation).
  - category: JVM & performance tuning — references/java-performance-tuning.md
    body: >
      Load for JVM/runtime tuning. Covers heap settings (-Xms=-Xmx), GC choice
      (G1GC default, ZGC/Shenandoah for low latency), unified GC logging,
      HikariCP pool sizing (formula and 10-20 default), Hibernate batch/fetch/
      query-plan-cache settings, N+1 prevention, batch processing with
      flush/clear, Spring Cache with Caffeine/Redis, async processing and Java 21
      virtual threads, response compression, Micrometer metrics + JFR profiling,
      and a performance anti-patterns list.

scenarios:
  - need: Stand up a new inventory microservice on Spring Boot 3.x with PostgreSQL and JWT auth.
    context: classify-need → new project + data layer + auth, with type=microservice, db=postgresql, security=jwt, java=17.
    action: >
      Run scaffold-project (spring_project_scaffolder.py inventory-service --type
      microservice --db postgresql --security jwt), then generate-entity-stack
      for the domain entities (entity_generator.py Inventory --fields
      "id:Long,productId:Long,quantity:Integer,warehouse:String"), then
      harden-and-apply-best-practices using spring-boot-best-practices.md, then
      audit-dependencies on the generated pom.xml.
    outcome: A buildable project with layered architecture, profiles, Docker, CI, JWT security, and a validated entity stack — ready for business logic.
  - need: Add a paginated read-only reporting API to an existing service.
    context: classify-need → API surface only (no new entity). methods=GET, paginated.
    action: Run generate-rest-endpoints (api_endpoint_generator.py reports --methods GET --paginated --package com.example), then add validation/error handling per spring-boot-best-practices.md.
    outcome: A REST controller with Page/Pageable wiring and OpenAPI annotations, consistent with the rest of the codebase.
  - need: Queries are slow and you suspect N+1 problems in the data layer.
    context: classify-need → performance. The service has @OneToMany collections and findAll() repositories.
    action: >
      Run profile-performance (performance_profiler.py --analyze-queries src/),
      read jpa-hibernate-guide.md for the fix, apply @EntityGraph or a fetch
      join and switch EAGER to LAZY, paginate unbounded findAll(), then re-run
      the profiler to confirm.
    outcome: N+1 and unbounded-query findings resolved; the profiler reports no high-severity issues.
  - need: Lock down endpoints with role-based access and verify dependencies are clean.
    context: classify-need → auth + dependency hygiene. roles=ADMIN,USER,MANAGER.
    action: >
      Run generate-security-config (security_config_generator.py --type jwt
      --roles ADMIN,USER,MANAGER), add @PreAuthorize to sensitive service methods
      per spring-security-reference.md, then run audit-dependencies
      --check-security and upgrade anything it flags critical/high.
    outcome: Stateless JWT security with method-level RBAC and a dependency audit that exits 0 (no critical/high CVEs).

anti_patterns:
  - N+1 queries — always use @EntityGraph or fetch joins for relationships; let profile-performance flag them.
  - Missing @Transactional on service methods that modify data (keep read methods readOnly).
  - Blocking calls inside a WebFlux reactive pipeline.
  - Hardcoded configuration or secrets instead of externalized profiles and ${VAR:default}.
  - Missing input validation at the controller layer — validate every untrusted request body with Jakarta annotations.
  - Leaving Open Session in View (open-in-view) enabled in production.
  - EAGER fetch on collections; prefer LAZY with explicit fetching.
  - Unbounded queries — never return whole tables; use Page/Slice pagination.
  - Ignoring a non-zero exit from dependency_analyzer.py — a critical/high CVE is a gate, not advice.
  - toString()/equals() cycles across bidirectional relationship fields.
  - Treating generated scaffolding as finished — it is a starting point to harden, not production code as-is.

integrations:
  - partner: senior-architect
    body: Provides architecture and microservice-decomposition decisions that inform scaffold-project choices (project type, service boundaries); pair with microservices-patterns.md.
  - partner: senior-backend
    body: Shares general API patterns and database design; this skill specializes them into Spring Boot / JPA generated code.
  - partner: senior-devops
    body: Consumes the generated Dockerfile, docker-compose.yml, and GitHub Actions workflow for Kubernetes deployment and CI/CD pipelines.
  - partner: senior-qa
    body: Builds on the generated test scaffolding (Mockito unit tests, MockMvc/Testcontainers integration tests) for QA automation.
  - partner: technical-writer
    body: Uses the SpringDoc/OpenAPI annotations emitted by the generators to produce API documentation.
  - partner: business-analyst-toolkit / product-manager-toolkit
    body: Requirements and user stories define the entity models, fields, and API contracts that drive entity_generator.py and api_endpoint_generator.py.
```

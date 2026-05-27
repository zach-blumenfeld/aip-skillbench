---
name: senior-java
description: World-class Java and Spring Boot development skill for enterprise applications, microservices, and cloud-native systems. Expertise in Spring Framework, Spring Boot 3.x, Spring Cloud, JPA/Hibernate, and reactive programming with WebFlux. Use when starting new Spring Boot projects, scaffolding REST APIs, designing JPA data layers, configuring Spring Security (OAuth2/JWT/RBAC), analyzing Maven/Gradle dependencies, profiling JVM performance, or reviewing Java code quality.
license: MIT
compatibility: Requires Python 3.8+ to run the bundled scaffolding scripts. Targets Java 17/21 LTS with Spring Boot 3.x, Spring Framework 6.x, Spring Cloud, Spring Security, Spring Data JPA, Hibernate, Maven/Gradle, JUnit 5, Mockito, Docker, Kubernetes. Cross-platform (macOS, Linux, Windows).
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.2/assets/aip-schemas/procedure.schema.json
  domain: engineering
  subdomain: java-development
  difficulty: advanced
  version: v1.0.0
  author: Claude Skills Team
  created: "2025-12-16"
  updated: "2025-12-16"
  time-saved: "60%+ on project scaffolding, 40% on security implementation"
  frequency: Daily for enterprise development teams
  related-agents: cs-java-engineer
  related-skills: senior-backend, senior-architect
  orchestrated-by: cs-java-engineer
  tags: java, spring-boot, spring-framework, microservices, jpa, hibernate, spring-cloud, webflux, enterprise, cloud-native, maven, gradle, api, backend
  verified: "true"
  featured: "false"
---

```yaml
purpose: >
  Production-ready Java and Spring Boot development for enterprise applications,
  microservices, and cloud-native systems. Generates scaffolded projects, JPA
  entity stacks, REST endpoints, and Spring Security configurations using six
  bundled Python tools, backed by reference documentation on Spring Boot
  patterns, microservices, JPA/Hibernate, security, and JVM performance. Core
  value: save 60%+ time on project scaffolding while enforcing enterprise-grade
  architecture, security compliance, and performance optimization.

trigger_when:
  - Starting a new Spring Boot project or microservice.
  - User asks to scaffold a Spring Boot application, REST API, or JPA data layer.
  - Designing RESTful endpoints with Spring MVC or WebFlux.
  - Implementing JPA/Hibernate persistence and needing query/fetch optimization.
  - Setting up authentication and authorization (OAuth2, JWT, RBAC, method security).
  - Analyzing Maven/Gradle dependencies for vulnerabilities or upgrade paths.
  - Profiling JVM applications or diagnosing performance bottlenecks (N+1, GC, thread pools).
  - Reviewing Java code for enterprise quality patterns and best practices.

do_not_use_when:
  - Working in a non-Spring Java stack (e.g., plain Jakarta EE, Quarkus, Micronaut)
    where Spring conventions do not apply.
  - The task is a one-off Java snippet, scripting, or pure algorithmic question
    that does not benefit from project-level scaffolding.
  - Frontend or non-JVM language work — defer to senior-frontend or other skills.

scope_and_approval: >
  The bundled scripts under scripts/ generate files and project trees on disk.
  Treat any scaffolder, generator, or config-writer invocation as a write action:
  confirm the target directory, project name, and overwrite behavior with the
  user before running. Dependency analysis and performance profiling are
  read-only and may be run without explicit approval. Never commit generated
  output, modify CI/CD pipelines, or push container images without confirmation.

steps:
  - name: classify-task
    description: >
      Identify which workflow applies — new project scaffolding, REST API
      development, JPA/Hibernate optimization, Spring Security implementation,
      dependency analysis, or performance profiling. Pick exactly one primary
      workflow; multiple may chain sequentially.
    one_of:
      - new-spring-boot-microservice
      - rest-api-development
      - jpa-hibernate-optimization
      - spring-security-implementation
      - dependency-analysis
      - performance-profiling
  - name: gather-inputs
    description: >
      Collect inputs the chosen workflow needs — service name, project type
      (microservice / monolith / reactive), database (PostgreSQL / MySQL /
      MongoDB / H2), security method (JWT / OAuth2), entity fields and
      relationships, endpoint methods, role list, or profiling target. Ask the
      user for anything not derivable from context.
    depends_on: [classify-task]
  - name: consult-references
    description: >
      Load only the reference doc(s) relevant to the chosen workflow from
      references/ — Spring Boot patterns, microservices, JPA/Hibernate,
      security, or performance tuning. Do not preload all references; progressive
      disclosure keeps context lean.
    depends_on: [classify-task]
  - name: run-generator
    description: >
      Invoke the appropriate Python tool under scripts/ with the gathered
      inputs (e.g., spring_project_scaffolder.py, entity_generator.py,
      api_endpoint_generator.py, security_config_generator.py,
      dependency_analyzer.py, performance_profiler.py). Surface the exact
      command for user approval before executing if it writes files.
    depends_on: [gather-inputs, consult-references]
  - name: customize-and-validate
    description: >
      Review generated output, customize application.yml profiles, business
      logic, validation rules, and security policies. Run unit and integration
      tests (./mvnw test, ./mvnw verify). Verify quality bars — code coverage
      80%+ on business logic, zero critical/high vulnerabilities, P99 < 200ms
      for CRUD operations.
    depends_on: [run-generator]
  - name: integrate-and-handoff
    description: >
      Connect to downstream concerns — Docker build, CI/CD pipeline, service
      discovery, distributed tracing, OpenAPI publication. Hand off generated
      artifacts to senior-devops (deployment), senior-qa (test automation), or
      technical-writer (API docs) as appropriate.
    depends_on: [customize-and-validate]

modes:
  - name: new-spring-boot-microservice
    body: |
      Target time: 30–45 minutes.
      1. Scaffold project — `python scripts/spring_project_scaffolder.py <name> --type microservice --db postgresql --security jwt`
         produces Spring Boot 3.x project with layered architecture, Docker, CI/CD.
      2. Configure environment — edit `src/main/resources/application.yml` with
         profiles for dev/staging/prod; configure DB, security, service discovery.
      3. Generate entities — `python scripts/entity_generator.py <Entity> --fields "..."` for each
         domain model, with `--relations` and `--auditable` as needed.
      4. Implement business logic — add service-layer logic and validation.
      5. Add tests — `./mvnw test` (unit), `./mvnw verify` (integration).
      6. Build and deploy — `./mvnw clean package -DskipTests` then `docker build -t <name>:latest .`.
      Reference: references/spring-boot-best-practices.md for complete setup patterns.
  - name: rest-api-development
    body: |
      Target time: 20–30 minutes per endpoint group.
      1. Design API contract — `python scripts/api_endpoint_generator.py <resource> --methods GET,POST,PUT,DELETE --paginated`.
      2. Implement validation — Jakarta validation annotations and custom validators.
      3. Configure error handling — global exception handler emitting RFC 7807 problem details.
      4. Add OpenAPI docs — SpringDoc for automatic API documentation (100% endpoint coverage).
      5. Test endpoints — integration tests with MockMvc (servlet) or WebTestClient (reactive).
      Reference: references/spring-boot-best-practices.md for API design patterns.
  - name: jpa-hibernate-optimization
    body: |
      Target time: 1–2 hours for complex data models.
      1. Analyze queries — `python scripts/performance_profiler.py --analyze-queries src/` to detect N+1.
      2. Optimize fetch strategies — configure lazy/eager loading deliberately.
      3. Add query hints — entity graphs and query hints for complex joins.
      4. Configure caching — Hibernate second-level cache with Hazelcast or Redis.
      5. Implement pagination — Spring Data Slice or Page for large datasets.
      Reference: references/jpa-hibernate-guide.md for optimization patterns.
  - name: spring-security-implementation
    body: |
      Target time: 1–2 hours.
      1. Generate config — `python scripts/security_config_generator.py --type jwt --roles ADMIN,USER,MANAGER`
         or `--type oauth2 --issuer-uri https://auth.example.com`.
      2. Configure OAuth2/JWT — token generation, validation, refresh.
      3. Implement RBAC — role-based access control on endpoints.
      4. Add method security — `@PreAuthorize` / `@PostAuthorize` annotations.
      5. Test security — security integration tests.
      Reference: references/spring-security-reference.md for security patterns.
  - name: dependency-analysis
    body: |
      Read-only.
      - `python scripts/dependency_analyzer.py pom.xml --check-security` — Maven, security focus.
      - `python scripts/dependency_analyzer.py build.gradle --output report.md` — Gradle, markdown report.
      Surfaces vulnerabilities, outdated deps, upgrade paths, dependency tree, license compliance.
  - name: performance-profiling
    body: |
      Read-only.
      - `python scripts/performance_profiler.py --analyze-queries src/` — static analysis for N+1 and patterns.
      - `python scripts/performance_profiler.py --profile http://localhost:8080/actuator` — profile a running app.
      - `python scripts/performance_profiler.py src/ --output performance-report.md` — generate optimization report.
      Reference: references/java-performance-tuning.md for JVM and GC tuning.

decisions:
  - signal: User asks for a new Spring Boot project but has not specified type.
    action: >
      Ask whether they want microservice (Spring Cloud-ready), monolith (layered
      single-deploy), or reactive (WebFlux + non-blocking). Default to
      microservice if building a new service in a distributed system.
  - signal: User chose microservice but did not specify a database.
    action: >
      Default to PostgreSQL unless the use case is document-heavy (suggest
      MongoDB) or local-only (suggest H2). Confirm before scaffolding.
  - signal: Existing JPA code exhibits N+1 query patterns.
    action: >
      Recommend entity graphs or `JOIN FETCH` queries; do not blanket-switch
      lazy to eager. Run `performance_profiler.py --analyze-queries` to confirm
      scope before changing fetch types.
  - signal: User asks for security but has not stated auth method.
    action: >
      Ask JWT vs OAuth2 vs SAML. JWT is the default for stateless microservices;
      OAuth2 resource server when integrating with an existing identity provider.
  - signal: Dependency analyzer reports critical/high CVEs.
    action: >
      Surface every critical/high finding, propose minimum-version upgrades,
      and recommend running the test suite after upgrade. Do not auto-upgrade
      without explicit user approval.
  - signal: User is on Java < 17.
    action: >
      Recommend upgrading to Java 17 or 21 LTS before scaffolding — Spring Boot
      3.x requires Java 17 minimum. Surface the upgrade as a prerequisite.
  - signal: Reactive (WebFlux) project requested but team has no reactive experience.
    action: >
      Flag the operational and debugging complexity of reactive pipelines.
      Recommend MVC + virtual threads (Java 21) as an alternative for most
      throughput-bound use cases.

search_shortcuts:
  - category: Bundled Python Tools (scripts/)
    body: |
      - `spring_project_scaffolder.py` — Spring Boot 3.x project trees with layered
        architecture, Docker, CI/CD. Args: `--type microservice|monolith|reactive`,
        `--db postgresql|mysql|mongodb|h2`, `--security jwt|oauth2`. Lombok + MapStruct.
      - `entity_generator.py` — full entity stack: JPA entity, Spring Data repository,
        service layer, REST controller, DTO, MapStruct mapper. Args: `--fields "name:Type,..."`,
        `--relations "field:OneToMany,..."`, `--auditable`.
      - `api_endpoint_generator.py` — REST endpoints with validation, OpenAPI annotations,
        pagination, error handling. Args: `--methods GET,POST,PUT,DELETE`, `--paginated`.
      - `security_config_generator.py` — Spring Security config (filter chain, CORS, CSRF,
        method security). Args: `--type jwt|oauth2`, `--roles ROLE1,ROLE2`, `--issuer-uri ...`.
      - `dependency_analyzer.py` — Maven/Gradle vulnerability scan, outdated detection,
        upgrade paths, license compliance. Args: `pom.xml|build.gradle`,
        `--check-security`, `--output report.md`.
      - `performance_profiler.py` — N+1 detection, memory/GC analysis, thread/connection
        pool recommendations, JVM flag guidance. Args: `--analyze-queries <src>`,
        `--profile <actuator-url>`, `--output <report>`.
      Run any tool with `--help` for full flag listing.
  - category: Reference Documentation (references/)
    body: |
      Load on demand — progressive disclosure keeps context lean.
      - `spring-boot-best-practices.md` — project structure, layered architecture,
        config profiles, API design, error handling, testing strategy, actuator,
        production readiness.
      - `microservices-patterns.md` — service decomposition, Spring Cloud
        (Config, Gateway, Discovery), inter-service comms (REST/gRPC/messaging),
        distributed tracing, circuit breakers, resilience.
      - `jpa-hibernate-guide.md` — entity design, repository patterns, custom queries,
        fetch optimization, N+1 prevention, first/second-level caching, transactions.
      - `spring-security-reference.md` — JWT/OAuth2/SAML, RBAC/ABAC, filter chain,
        method security annotations, security testing.
      - `java-performance-tuning.md` — JVM tuning, GC, connection pools, caching,
        async + virtual threads, profiling tools.
  - category: External Documentation
    body: |
      - Spring Boot Reference: https://docs.spring.io/spring-boot/docs/current/reference/html/
      - Domain CLAUDE.md: `../CLAUDE.md` (parent skill domain guide)

integrations:
  - partner: senior-architect
    body: >
      Receives architecture decisions (service boundaries, data ownership, sync vs
      async) that inform scaffolding choices — project type, database, messaging.
      Invoke senior-architect first for any greenfield distributed system.
  - partner: senior-backend
    body: >
      Sibling skill for general API patterns, database design, and backend
      conventions. Compose when the work spans non-Spring backend concerns.
  - partner: senior-devops
    body: >
      Receives generated Dockerfile and CI/CD pipeline output. Hand off for
      Kubernetes deployment, environment promotion, and observability stack
      integration.
  - partner: senior-qa
    body: >
      Receives generated test scaffolding. Hand off for QA automation,
      contract tests, and end-to-end coverage.
  - partner: senior-security
    body: >
      Pair for security audits and penetration testing once
      spring-security-implementation completes. Especially when handling PII or
      regulated data.
  - partner: senior-frontend
    body: >
      Downstream consumer of OpenAPI specs for typed client generation. Workflow
      pattern: senior-java → senior-frontend → senior-qa for full-stack features.
  - partner: technical-writer
    body: >
      OpenAPI specs generated by api_endpoint_generator.py feed API documentation
      pipelines.
  - partner: business-analyst-toolkit
    body: >
      Upstream source of requirements that define entity models and API contracts.
  - partner: product-manager-toolkit
    body: >
      Upstream source of user stories that guide feature implementation.
  - partner: cs-java-engineer
    body: >
      Orchestrating agent. This skill is invoked by cs-java-engineer; coordinate
      multi-skill workflows through that agent.

scenarios:
  - need: Stand up an order microservice with PostgreSQL persistence.
    action: >
      Run `python scripts/spring_project_scaffolder.py order-service --type
      microservice --db postgresql`.
    outcome: >
      Complete Spring Boot 3.x project with layered architecture, Docker setup,
      and GitHub Actions CI/CD pipeline ready for `mvnw clean package`.
  - need: Generate the full entity stack for a User domain object.
    action: >
      Run `python scripts/entity_generator.py User --fields
      "id:Long,email:String,name:String,createdAt:LocalDateTime"`.
    outcome: >
      JPA entity with Lombok, Spring Data repository, service with transaction
      management, REST controller, DTO, and MapStruct mapper — all generated and
      wired.
  - need: Inventory microservice with JWT security and two domain entities.
    context: >
      Greenfield service in a microservices estate; PostgreSQL is the team
      default; JWT is the existing platform auth method.
    action: >
      Scaffold with `--type microservice --db postgresql --security jwt`, then
      generate Inventory and InventoryMovement entities with explicit
      `--relations` flags, then add service-layer business logic, run
      `./mvnw verify`, and `docker build`.
    outcome: >
      Production-ready service in 30–45 minutes versus several hours of manual
      setup.
  - need: Eliminate slow page loads traced to JPA N+1 patterns.
    action: >
      Run `performance_profiler.py --analyze-queries src/`, then add entity
      graphs or `JOIN FETCH` queries to the flagged repositories, then re-run
      the profiler to confirm.
    outcome: >
      Reduced query count per request; P99 latency moves under the 200ms target.

anti_patterns:
  - Allowing N+1 queries — always use entity graphs or fetch joins for relationships.
  - Omitting `@Transactional` on service methods that modify data.
  - Using blocking calls inside WebFlux reactive pipelines.
  - Hardcoding configuration values instead of externalizing them with profiles.
  - Skipping input validation at the controller layer.
  - Leaving Open Session in View (OSIV) enabled in production.
  - Auto-upgrading dependencies on critical/high CVE without running tests first.
  - Preloading every reference doc upfront instead of loading on demand.
  - Switching JPA fetch types blanket lazy→eager to "fix" N+1 — prefer entity graphs.
  - Scaffolding without confirming target directory and overwrite behavior with the user.
```

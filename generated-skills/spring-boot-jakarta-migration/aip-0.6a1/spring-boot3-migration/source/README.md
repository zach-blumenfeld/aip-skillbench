# spring-boot3-migration: provenance and compilation notes

## Provenance

This skill was compiled from five curated Agent Skills. They are copied verbatim into this folder:

| Folder | Original skill | Covers |
|--------|----------------|--------|
| `spring-boot-migration/SKILL.md` | spring-boot-migration | pom changes (parent 3.2.0, java.version 21, JAXB/activation removal, jjwt 0.9.1 to 0.12.3 modular), OpenRewrite, verification, checklist, migration order |
| `jakarta-namespace/SKILL.md` | jakarta-namespace | javax to jakarta package table, JDK packages that stay javax, sed batch commands, entity requirement, pitfalls |
| `hibernate-upgrade/SKILL.md` | hibernate-upgrade | Hibernate 5 to 6: IDs, dialects, stricter JPQL/HQL, `update from`, distinct, Criteria removal, `@Type`/`@TypeDef`, properties, N+1 monitoring |
| `restclient-migration/SKILL.md` | restclient-migration | RestTemplate to RestClient for GET, POST, exchange, DELETE, configured bean, status handlers, ParameterizedTypeReference, WebClient note |
| `spring-security-6/SKILL.md` | spring-security-6 | WebSecurityConfigurerAdapter to SecurityFilterChain, `@EnableMethodSecurity`, lambda DSL, requestMatchers, entry point, headers, AuthenticationManager, pitfalls |

The sources had no scripts, references or assets beyond their `SKILL.md` files.

Task context used for design and testing (not copied into the skill): the task statement, which migrates a user-management microservice at `/workspace` from Java 8 / Boot 2.7 to Java 21 / Boot 3.2 and then requires `mvn clean compile` and `mvn test` to pass. The task container is `ubuntu:24.04` with SDKMAN Temurin 8 and 21 (default 21) and Maven 3.9.6. It has **no Python**.

## Intent

One procedure takes any Maven Spring Boot 2.x service to Boot 3.2.x / Java 21:

1. Deterministic rewrites by script.
2. Hand rewrites by the agent, only where the scan says they are needed.
3. A Maven-plus-residual-pattern gate, with a fix loop when the gate fails.

## Component-kind choices

| Step | Kind | Why |
|------|------|-----|
| `apply-mechanical` | execution | Version bumps, dependency removal and replacement, javax-to-jakarta for an explicit package list, annotation and matcher renames, `update from`, dialect names and the persistence.xml namespace are all fixed rules (lookup tables and regexes). Scripting them makes them complete and idempotent, including test sources, fully qualified names and resources. The same script inventories what is left, so routers can branch on facts instead of agent judgement. |
| `route-security`, `route-rest-client`, `route-legacy-apis` | router | Branch on script booleans. Each hand rewrite runs only if the scan found work for it. |
| `rewrite-security` | client_task | Turning an adapter class into a `SecurityFilterChain` bean is code generation that has to keep every rule. A regex cannot do it safely; the source itself says it "cannot be automated with sed". |
| `migrate-restclient` | client_task | Translating each call while keeping signatures and error semantics is code generation. |
| `fix-legacy-apis` | client_task | Criteria to JPA Criteria, `@Type` to converters, the jjwt 0.12 API and pom replacements (springfox) are code generation. |
| `verify` | execution | The task's two quality commands plus the sources' "should return NO results" greps are deterministic checks. |
| `route-build` | router | Branches on `migration_complete`. |
| `fix-build` | client_task | Diagnosing and fixing an arbitrary compile or test failure is open-ended. The agent loops with Maven itself. |

No `decision` step: every branch point is decided by a fact the scripts compute. No judgement with a fixed answer space was left.

**Runtime choice:** the task container has no Python, so the scripts are bash plus core Perl regexes. `perl-base` is Essential in Ubuntu, and only Perl core is used, with no modules. Interpreter: `bash >= 3.2`. Tools: `perl`, `grep`, `find`, `cksum`, `mktemp`, `java`, `mvn`. They work with GNU (container) and BSD (macOS) userlands: no `sed -i`, no bash 4 features. One script file with two modes (`apply`, `verify`) shares the pattern definitions. `MAVEN_ARGS` is honoured by Maven 3.9 (used locally for `-Dmaven.repo.local`).

## Where each source item lives

- **spring-boot-migration:**
  - Parent and Java bumps, JAXB and activation removal, the jakarta XML binding fallback, jjwt modular with runtime scopes: `apply-mechanical` (script).
  - Quick-check and verify greps, version checks, compile and test: `verify`.
  - Why remove JAXB: `anti_patterns`.
  - Checklist and migration order: the step order of the graph (pom, namespace, security, HTTP clients, tests).
  - Full text: `references/boot3-pom-and-jakarta.md`.
- **jakarta-namespace:**
  - Mapping table and JDK exclusions: `EE_RE` in the script, plus `anti_patterns`.
  - Batch sed and wildcards: script. Wildcards in `javax.annotation.*` are flagged, not rewritten, because they mix JDK and EE types.
  - Entity requirement and verification greps: `verify`.
  - Pitfalls: test files (the script covers every `.java`), persistence.xml (script), third-party libraries (`pom_review`), mixed namespaces (`verify`).
  - Full text: `references/boot3-pom-and-jakarta.md`.
- **hibernate-upgrade:**
  - `update from`, dialects and the artifact rename: script.
  - Criteria, `@Type`/`@TypeDef`, ID generation, stricter JPQL, native booleans, enum and java.time, distinct: scan findings plus the `fix-legacy-apis` template.
  - Full text and added gotchas: `references/hibernate-6.md`.
- **restclient-migration:**
  - Every pattern: the `migrate-restclient` template plus `references/restclient-migration.md`.
  - WebClient: `do_not_use_when`.
- **spring-security-6:**
  - Renames (`@EnableMethodSecurity`, antMatchers/mvcMatchers, authorizeRequests): script.
  - Adapter removal, lambda DSL, AuthenticationManager, entry point, headers, UserDetailsService auto-detection, `@Configuration`: the `rewrite-security` template, scan findings and `verify`.
  - Full text and gotchas: `references/spring-security-6.md`.

## Deliberate drops and deviations

| Source item | Decision | Rationale |
|-------------|----------|-----------|
| OpenRewrite plugin and recipes (spring-boot-migration, jakarta-namespace) | Not a procedure step; kept in `references/boot3-pom-and-jakarta.md` | It needs the plugin and recipe artifacts downloaded, rewrites far beyond the task, and its output is non-deterministic across recipe versions. The script covers the same mechanical scope deterministically. |
| "First upgrade to latest 2.7.x" (migration order step 1) | Dropped | The procedure goes straight to 3.2.x and gates on compile and test. An intermediate release adds a full build cycle without changing the result. |
| `sed -i` commands (all sources) | Replaced by the script's perl edits | Same rewrites, but idempotent, portable (BSD and GNU) and recorded per file. The originals stay in the references. |
| `regexMatchers(` to `requestMatchers(` sed (spring-security-6) | Deviation: not automated | `requestMatchers(String)` takes path patterns, so the rename silently changes semantics. The scan flags it, and the template and reference give the `RegexRequestMatcher` conversion. |
| Affected-annotation lists (jakarta-namespace) | Redundant | Covered by package-level rewriting. Kept in the reference. |
| Actuator endpoint paths note (spring-boot-migration) | Reference only | Advisory. The security rewrite keeps `/actuator/health` rules verbatim. |
| Fetch strategies, properties, `timezone.default_storage`, N+1 statistics and slow-query logging (hibernate-upgrade) | Reference only, not applied | Optional tuning. Turning on statistics or logging changes app behaviour and is not part of a compatibility migration. |
| `@WithMockUser` test example (spring-security-6) | Reference only | Existing tests must not be rewritten. |
| "Sources" link lists | Dropped | Background. |
| Multiple-servlet `requestMatchers` failure (added gotcha) | Kept as a conditional fallback | Tested on Boot 3.2.0 / Security 6.2: plain string matchers start fine with the H2 console enabled, so the skill keeps plain strings and uses `antMatcher(...)` only if that error appears. |

Additions beyond the sources, all generalisations for other instances of this task:

- explicit javax EE artifacts and `org.hibernate:hibernate-core` re-coordinated
- `hibernate-entitymanager` removed
- Lombok older than 1.18.30 left to Boot
- `maven.compiler.*` and compiler-plugin source/target
- `java.version` added when missing
- persistence.xml namespace and `javax.persistence.*` keys
- versioned dialect renames
- springfox, Spring Cloud and pinned-Spring review items
- jjwt 0.12 API reference
- Spring 6 compile-failure catalogue (`HttpStatusCode`, removed adapters, etc.)
- RestClient gotchas (`@Value` in constructor, terminal call)

## Functional test (local, JDK 21.0.12 + Maven 3.9.6)

- **Run 1, the real task workspace:**
  - Path: apply, then security `true`, rest-client `true`, legacy `false`, then verify, then build `true`, then end.
  - Result: `mvn clean compile` passed and `mvn test` ran 6 tests with 0 failures, with no residual issues.
  - The migrated app also starts with its default profile (H2 console enabled).
- **Run 2, a variant:**
  - The variant already has a lambda-style SecurityFilterChain, no RestTemplate, a jjwt 0.9 token provider, a Hibernate `@Type(type="yes_no")`, an HQL `update from`, and an `HttpStatus = getStatusCode()` compile break the scan does not detect.
  - Path: apply, then security `false`, rest-client `false`, legacy `true`, then verify, then build `false`, then fix-build, then end.
  - Result after the fix: 6 tests with 0 failures.
- **Edge-case project:** JDK `javax` packages are kept, EE artifacts are re-coordinated, the Lombok version is dropped, springfox is flagged, and wildcard `javax.annotation.*` is flagged.
- Bugs found and fixed during testing:
  - The compile-error filter dropped `org.springframework.http...` lines.
  - Perl interpolated `$p` plus text in the dependency re-coordination.
  - H2Dialect was falsely flagged as a versioned dialect.
  - `@org.hibernate.annotations.Type(type=` was missed.

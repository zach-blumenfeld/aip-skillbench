---
name: spring-boot-3-migration
description: Migrate a Maven Spring Boot 2.7 / Java 8 service to Spring Boot 3.2 / Java 21 end to end - pom and dependency upgrades (JAXB removal, jjwt 0.12), javax -> jakarta namespace, Hibernate 6, Spring Security 6 (WebSecurityConfigurerAdapter -> SecurityFilterChain, @EnableMethodSecurity, requestMatchers, lambda DSL), RestTemplate -> RestClient, then gate on `mvn clean compile` and `mvn test`. Use for any Spring Boot 2 to 3 upgrade, Jakarta EE namespace migration, or build errors after one.
compatibility: bash >= 4, GNU or BSD coreutils, grep -E, sed, awk (mawk is enough); java >= 17 and Maven 3.9 for the build gate (SDKMAN installs are auto-detected). No python, no extra packages; Maven needs network access to download Boot 3 artifacts.
---

# Spring Boot 2 → 3 Migration

## Trigger When

- A task says to upgrade Spring Boot 2.x → 3.x and/or Java 8/11 → 17/21.
- A project has `javax.persistence`/`javax.validation`/`javax.servlet` imports, `WebSecurityConfigurerAdapter`,
  `@EnableGlobalMethodSecurity`, `antMatchers`, `RestTemplate`, `jaxb-api`, or `jjwt` 0.9.x and must build on Boot 3.
- `mvn clean compile` / `mvn test` fails after a Boot 3 bump (missing `javax.*`, Security DSL, HQL parse errors).
- Applying any one of: Jakarta namespace migration, Hibernate 5 → 6, Spring Security 5 → 6, RestTemplate → RestClient.

## Purpose

Takes a legacy Spring Boot 2.7 Maven service to Boot 3.2 / Java 21 with behavior preserved and the build
green. Two scripts do everything deterministic: an inventory/gate (`check.sh`) and an idempotent rewriter
(`migrate.sh`: pom versions and dependencies, a whitelist-based javax → jakarta rewrite that leaves JDK
`javax.*` alone, annotation/matcher renames, HQL and property fixes). The agent does only the rewrites
that need code judgment: security configuration, HTTP clients, jjwt and Hibernate code, each checked
against the original before the build gate.

## Prerequisites

Run everything from this skill's folder, passing the project root (the folder with `pom.xml`, e.g.
`/workspace`) as `<project>`. Before the first script, check `bash --version` (≥ 4), `awk`, `sed`, `grep`,
and for the build gate `java -version` (≥ 17) and `mvn -v`. Name everything missing. If `java` is 8 but
SDKMAN has a 17+ JDK, `check.sh --build` switches `JAVA_HOME` itself. Never edit tests to make them pass.

## Workflow

- [ ] 1. Inventory — `bash scripts/check.sh <project>`
- [ ] 2. Mechanical rewrite — `bash scripts/migrate.sh <project>`, then `bash scripts/check.sh <project>`
- [ ] 3. Client tasks for every `client_task.*=yes` in the SUMMARY (A–D below)
- [ ] 4. Decision `semantic_review`
- [ ] 5. Build gate — `bash scripts/check.sh <project> --build`; on failure, decision `build_failure`, fix, repeat
- [ ] 6. Report

### 1. Inventory (execution)

`bash scripts/check.sh <project>` prints `LEVEL [task] file:line: message` lines, then a SUMMARY
(`findings.<task>=N`, `client_task.security_rewrite|restclient_rewrite|jjwt_code|hibernate_code=yes|no`,
test counts). Exit 1 means FAIL findings exist (expected before migrating). Note the test count: it must
not drop. It scans comments and Javadoc too — stale mentions of old APIs count as findings.
Snapshot the original for step 4: if `<project>` is not a clean git checkout, `cp -a <project> /tmp/pre-migration`.

### 2. Mechanical rewrite (execution)

`bash scripts/migrate.sh <project>` (options: `--boot-version 3.2.0` default, `--java-version 21`,
`--jjwt-version 0.12.3`, `--dry-run`). It prints every file it changed with a diff excerpt, and is
idempotent (a second run reports 0 changes). It sets the Boot parent/BOM version and Java level, removes
JAXB/activation artifacts, replaces `jjwt` with `jjwt-api` + runtime `jjwt-impl`/`jjwt-jackson`, moves
javax API artifacts to jakarta coordinates, rewrites Java EE `javax.*` → `jakarta.*` in sources, XML
descriptors and properties, `@EnableGlobalMethodSecurity` → `@EnableMethodSecurity`, `.antMatchers(`/
`.mvcMatchers(` → `.requestMatchers(`, `.authorizeRequests(` → `.authorizeHttpRequests(`, HQL
`update from X` → `update X`, renamed dialects and Boot 3 property keys. It adds `jakarta.xml.bind-api` +
`jaxb-runtime` only if code still uses `jakarta.xml.bind`.
Re-run `bash scripts/check.sh <project>`; what remains is the client-task list.
Gradle project (no `pom.xml`): the script exits 2; apply the same changes by hand from
`references/pom-and-namespace.md`.

### 3. Client tasks

Do each task whose SUMMARY flag is `yes`; skip the rest. Keep each class's public API, bean names,
endpoint rules, fallbacks and log lines; rewrite comments that describe the old API.

**A. Security rewrite** (`client_task.security_rewrite=yes`). Read `references/spring-security-6.md` first.
Replace each `WebSecurityConfigurerAdapter` subclass with a `@Configuration @EnableWebSecurity` class
exposing `@Bean SecurityFilterChain` (lambda DSL, `return http.build()`), keep the `PasswordEncoder` bean,
replace `authenticationManagerBean()` with an `AuthenticationConfiguration`-based `AuthenticationManager`
bean, delete `configure(AuthenticationManagerBuilder)` (the `UserDetailsService` bean is auto-detected),
and convert every chained call (`.csrf().disable()`, `.and()`, `.headers().frameOptions().disable()`,
`.httpBasic()`) to its lambda form. Copy every matcher with the same arguments in the same order;
`anyRequest()` stays last. Keep `securedEnabled`/`jsr250Enabled` on `@EnableMethodSecurity` when
`@Secured`/`@RolesAllowed` are used.

**B. RestClient rewrite** (`client_task.restclient_rewrite=yes`). Read `references/restclient.md` first.
Replace every `RestTemplate` (and `RestTemplateBuilder` bean) with `RestClient`, keeping the wiring shape:
`new RestTemplate()` → `RestClient.create()`; a builder-made bean → a `RestClient` bean from the
auto-configured `RestClient.Builder` (`rootUri` → `baseUrl`, timeouts via a request factory). Map each
call per the table there: URI templates for path/query values, headers on the request spec,
`ParameterizedTypeReference<Map<String, Object>>` for generic bodies, `toBodilessEntity()` for
POST/DELETE without a body. Keep null checks, `try/catch` blocks and their fallback values exactly.

**C. jjwt code** (`client_task.jjwt_code=yes`). Use the 0.9 → 0.12 table in
`references/pom-and-namespace.md` §3: `SecretKey` via `Keys.hmacShaKeyFor(...)` (≥ 32 bytes), builder
`subject()/issuedAt()/expiration()`, `signWith(key)`, parser
`Jwts.parser().verifyWith(key).build().parseSignedClaims(t).getPayload()`. Replace `DatatypeConverter`
with `java.util.Base64`, decoding the secret exactly as before. If nothing else uses `jakarta.xml.bind`,
remove the JAXB dependencies migrate.sh added (check.sh warns).

**D. Hibernate code** (`client_task.hibernate_code=yes`). Use `references/hibernate-6.md`: `@Type(type=)`/
`@TypeDef` → `@JdbcTypeCode(SqlTypes.X)` or `@Type(MyType.class)`; legacy `Criteria` → JPA
`CriteriaBuilder`; drop `distinct` on fetch joins; `GenerationType.AUTO` → `IDENTITY` when the schema
relies on auto-increment.

### 4. Decision: semantic_review

Input: each rewritten file next to its original (`git diff`, or `diff -ru /tmp/pre-migration <project>`). Answer all questions in one pass; a false `true` is the costly mistake, so reconsider any close
call that leans `true` and fix the code until the answer is clearly `true`.

```yaml
security_rules_preserved:
  type: noul
  instructions: Does every SecurityFilterChain keep the original's rules? Answer true if no security config was rewritten.
  criteria:
    true: Same matchers (method + pattern) in the same order with the same permitAll/authenticated/hasRole, same csrf, session policy, entry point, headers, httpBasic/formLogin, and the same beans (PasswordEncoder, AuthenticationManager, UserDetailsService) are still exposed.
    false: Any rule, order, access level, filter option or previously exposed bean is missing, added or changed.
http_calls_preserved:
  type: noul
  instructions: Does every migrated RestClient call keep the original request and failure behavior? Answer true if no RestTemplate code existed.
  criteria:
    true: Same HTTP method, URL (base + path + query values), headers, body and response type per call; same try/catch scope and fallback values; null-body handling kept.
    false: Any call changes method, URL, headers, body, error handling or return value on failure/null.
tests_untouched:
  type: noul
  instructions: Are test sources and test resources unchanged apart from the javax -> jakarta imports migrate.sh made (and wiring-only changes forced by removed APIs)?
  criteria:
    true: No assertion, expected value or test was removed, weakened, skipped or @Disabled.
    false: Any test was deleted, disabled or had its expectations changed.
```

Any `false` → fix the code (not the tests), then answer again.

### 5. Build gate (execution) and fix loop

`bash scripts/check.sh <project> --build` re-runs every static check, then `mvn -B clean compile` (with
deprecation warnings shown) and `mvn -B test`. It prints `PASS [build]` lines and the surefire totals, or
`FAIL [build]` with the `[ERROR]`/`Caused by` lines and the log path (`$TMPDIR/sb3-check/*.log`). Done when
exit is 0, there are no FAIL findings, and the test count is at least the inventory count. Resolve WARN
findings too (deprecation warnings count as part of "fix deprecated security methods").

On failure, answer this decision on the error lines and log excerpt, load the matching reference, fix and re-run:

```yaml
build_failure:
  type: choice
  instructions: What is the root cause of the first failing error in the check.sh --build output?
  criteria:
    environment: Artifacts cannot be downloaded (Could not resolve / UnknownHost / offline), or wrong JDK/Maven - no code error shown.
    dependency: Missing/conflicting artifact or class from a library (package does not exist for a third-party lib, NoClassDefFoundError, jjwt/JAXB classes) (fix with references/pom-and-namespace.md)
    namespace: A javax.* symbol is missing or jakarta/javax types mismatch -> references/pom-and-namespace.md §4.
    security: Security config does not compile or context fails in security beans, or tests get 401/403 unexpectedly (fix with references/spring-security-6.md)
    restclient: RestClient/RestTemplate code fails to compile or HTTP-client beans fail (fix with references/restclient.md)
    hibernate: Query parse/validation, mapping, type or DDL errors at startup (fix with references/hibernate-6.md)
    test_logic: A test assertion fails while the context starts - production behavior changed; compare with the original code.
    other: None of the above.
```

`environment` is not fixed by editing code: report it (Maven needs network for Boot 3 artifacts). Reconsider
`test_logic` vs `security`/`hibernate` when a test fails with a stack trace from those layers.

### 6. Report

Summarize: versions (Boot, Java, jjwt), files changed by migrate.sh, each client task done, the
`semantic_review` answers, final `check.sh --build` result with test totals, and any WARN left with reason.

## Gotchas

- JDK packages stay `javax.*`: `javax.sql`, `javax.crypto`, `javax.net`, `javax.naming`, `javax.transaction.xa`,
  `javax.annotation.processing`, JSR-305 `javax.annotation.Nullable`. migrate.sh uses a whitelist for this
  reason; never run a blanket `s/javax/jakarta/`.
- `@EnableWebSecurity` no longer includes `@Configuration`; add it.
- `@EnableMethodSecurity` turns on `@PreAuthorize` by default; `@Secured` needs `securedEnabled = true`.
- Graders grep comments too: Javadoc saying "uses RestTemplate" or "WebSecurityConfigurerAdapter" fails
  the checks even when the code is migrated.
- `@Value` fields are not set inside constructors: keep `baseUrl` concatenation per call when the
  service builds its own `RestClient`.
- On Boot 3.2 the H2 console plus String `requestMatchers` patterns boot fine; only Boot 3.0/3.1 needs
  `AntPathRequestMatcher.antMatcher(...)` (check.sh flags it per version).
- Without `spring-boot-starter-parent`, add `<parameters>true</parameters>` to the compiler plugin or
  `@PathVariable`/`#param` SpEL break.
- The base image's Maven cache holds Boot 2.7 artifacts only; the first Boot 3 build downloads several
  hundred MB.

# spring-boot-3-migration — provenance and compile log

## Provenance

Compiled 2026-10-08 into one AIP procedure from five curated Agent Skills that each describe one
part of the same Spring Boot 2 → 3 workflow. The originals are copied verbatim:

| Source | Covers |
|---|---|
| `spring-boot-migration/SKILL.md` | pom: parent 3.2.0, Java 17/21, JAXB/activation removal, jjwt 0.9.1 → 0.12.3 modular, H2 dialect, actuator, sed commands, OpenRewrite, verification, checklist, migration order |
| `jakarta-namespace/SKILL.md` | javax → jakarta package table, JDK exceptions, affected annotations, sed batch commands, entity requirement, verification, OpenRewrite, pitfalls |
| `spring-security-6/SKILL.md` | WebSecurityConfigurerAdapter → SecurityFilterChain, @EnableMethodSecurity, lambda DSL, requestMatchers, exception handling, headers, UserDetailsService, pitfalls, verification |
| `restclient-migration/SKILL.md` | RestTemplate → RestClient for GET/POST/exchange/DELETE, configuration bean, status handlers, ParameterizedTypeReference, WebClient alternative |
| `hibernate-upgrade/SKILL.md` | Hibernate 6: namespace, ID generation, dialect, JPQL/native queries, type mappings, fetch, removed @Type/@TypeDef/Criteria, update-from, distinct, N+1, properties, troubleshooting, monitoring |

Environment facts used (from the task's `environment/`, not copied): the Dockerfile (Ubuntu
24.04, SDKMAN with Java 8.0.392-tem and 21.0.2-tem — 21 default — Maven 3.9.6, project at
`/workspace`, `mvn dependency:go-offline` run under Java 8 for the **2.7** tree only) and the
sample project (`userservice`: Boot 2.7.18, Java 1.8, jjwt 0.9.1 + jaxb-api 2.3.1, javax
persistence/validation/servlet, an adapter-based SecurityConfig with `@PreAuthorize` users,
a RestTemplate `ExternalApiService`, H2). The scripts were tested against a copy of it.

## Graph and step-kind choices

```
scan-project (execution) → apply-rewrites (execution) → refactor-code (client_task)
  → verify-static (execution) → static-gate (router on verify_passed)
       false → refactor-code            true → build-and-test (client_task)
  → build-outcome (decision: passed / code_errors / environment_blocked) → outcome-gate (router)
       code_errors → refactor-code       passed | environment_blocked → end
```

The order follows the sources' "Recommended Migration Order": build file and Java version →
remove incompatible deps → Boot parent → namespaces → security → HTTP clients → tests.

- **scan-project — execution.** Finding every place that needs work is grep logic over files
  (the sources' "Find"/"Check" commands). `scripts/sb3lib.py` encodes each source check as a rule
  with area, severity and the source's fix text, plus the positive checks ("@EnableMethodSecurity
  must exist when @PreAuthorize is used", "entities must import jakarta.persistence",
  "SecurityFilterChain present").
- **apply-rewrites — execution.** Every rewrite the sources give as `sed` is deterministic, so a
  script does it (Python instead of `sed -i`, which differs between GNU/BSD and cannot remove
  multi-line pom blocks): parent/BOM/property version, java.version + compiler properties and
  plugin config, removal of jaxb-api/jaxb-impl/jaxb-core/activation, jjwt → jjwt-api/impl/jackson,
  javax → jakarta for the package table, EnableGlobalMethodSecurity → EnableMethodSecurity,
  antMatchers/mvcMatchers → requestMatchers, authorizeRequests → authorizeHttpRequests,
  "update from" → "update". It is idempotent and re-scans afterwards. OpenRewrite (the sources'
  alternative) was not chosen as the default because the container's Maven cache only holds the
  2.7 tree; it stays in the references as an option.
- **refactor-code — client_task.** The adapter → SecurityFilterChain refactor ("cannot be
  automated with sed"), RestTemplate → RestClient, legacy Criteria, `@Type`/`@TypeDef` and jjwt
  API changes are code generation; the agent does them with per-area references loaded on demand.
- **verify-static — execution.** The sources' verification greps (must-be-absent and
  must-be-present) are scripted; `verify_passed` is a boolean a router can branch on.
- **static-gate / outcome-gate — routers** on script and decision outputs; loops send the agent
  back with fresh `remaining_issues` / `build_report`.
- **build-and-test — client_task.** Running `mvn clean compile` / `mvn test` and fixing small
  errors needs the agent's shell and judgment; the template pins Java 21 via SDKMAN.
- **build-outcome — decision.** Telling code failures from environment failures (no network for
  Boot 3 artifacts) is a judgment over a log with a fixed answer space; a choice question with a
  0.7 threshold makes it explicit instead of free-form.

## Deliberate deviations from the sources (and why)

- `regexMatchers(` is **not** rewritten to `requestMatchers(` with the same string (source sed
  does). `requestMatchers(String)` takes ant/mvc patterns, so the regex would silently change
  meaning; it is flagged with the `RegexRequestMatcher.regexMatcher(...)` fix instead.
- javax → jakarta rewriting covers fully qualified names and `.properties`/`.yml`/`.xml` keys,
  not only `import` lines, and excludes `javax.transaction.xa` (JDK) and non-EE
  `javax.annotation.*` (JSR-305, `processing`). pom.xml is excluded so groupIds aren't corrupted.
- jakarta XML Bind dependencies are added only when the code actually uses XML binding
  (source: "only add these if you actually need XML binding").
- Comments/Javadoc naming removed APIs are flagged as blocking, because the sources'
  verification greps match comments too.

## Additions beyond the sources (domain knowledge needed to finish the task)

jjwt 0.12 API changes (parser builder, `Keys.hmacShaKeyFor`, 256-bit minimum, `TextCodec` gone);
`access(String)` → `WebExpressionAuthorizationManager`; versioned Hibernate dialects removed;
third-party javax artifact swaps (servlet-api, validation-api, springfox → springdoc);
`spring-boot-properties-migrator`; container build specifics (SDKMAN init, Java 21, offline
2.7-only cache); the `@Value` field-injection null trap when building RestClient in a
constructor; manual-package list (javax.inject etc.) needing a dependency swap.

## Completeness map (source item → where it lives)

| Source item | Location in skill |
|---|---|
| Boot parent 2.7.x → 3.2.0 | `sb3lib.rewrite_pom` (+ BOM/property forms); rule `build.boot-version`; `references/boot-3-build.md` |
| Java 17/21 requirement | `rewrite_pom` java bump (<17 → 21); rule `build.java-version` |
| Remove jaxb-api, jaxb-impl, jaxb-core, activation, javax.activation-api; why | `assets/config.json` `remove_dependencies` (with why); rule `build.old-jaxb-activation`; boot-3-build.md |
| Jakarta XML bind if needed | config `jakarta_xml_bind_dependencies`; `rewrite_pom` step 4 |
| Quick check / verify removal greps | rules + `verify.py`; boot-3-build.md Verification |
| jjwt 0.9.1 → 0.12.3 modular (scopes) | `rewrite_pom` step 3; rule `build.legacy-jjwt` |
| Common issue: javax compile errors | jakarta rules; refactor-task step 4 |
| H2 dialect | rule `config.dialect` (advisory); hibernate-6.md, boot-3-build.md |
| Actuator endpoints changed | rule `config.actuator`; boot-3-build.md; security template keeps actuator matchers |
| sed migration commands (pom, javax, security, hibernate) | implemented in scripts; verbatim fallback in each reference |
| OpenRewrite plugin/recipes (Boot 3.2 and Jakarta) + what it does | boot-3-build.md, jakarta-namespace.md |
| Verification: Boot/Java version, old deps, compile, test | `verify.py` static_checks; build-and-test step |
| Migration checklist & recommended order | graph order; boot-3-build.md |
| Package mapping table (9 rows) | config `javax_auto_packages` / `javax_annotation_auto_classes`; jakarta-namespace.md |
| javax.sql/javax.crypto stay (JDK) | regex excludes them; anti_patterns; jakarta-namespace.md |
| Affected annotations lists | jakarta-namespace.md |
| Wildcard imports | handled by regex; `import javax.annotation.*` flagged |
| Entities MUST use jakarta.persistence; incomplete if absent | rule `jakarta.persistence-missing` |
| Pitfalls: tests too, XML configs, third-party, mixed namespaces | scripts walk tests and xml; `config.persistence-xml-namespace`; `build.javax-artifact`; anti_patterns; template rules |
| Security: adapter → SecurityFilterChain; AuthenticationManager; PasswordEncoder | rules `security.*`; refactor-task step 1; security-6.md full example |
| @EnableGlobalMethodSecurity → @EnableMethodSecurity (+ import) | `SOURCE_REWRITES`; rules `security.enable-global-method-security`, `security.method-security-missing` |
| Lambda DSL, URL matching, exception handling, headers, UserDetailsService | rule `security.chained-dsl`/`and-chaining`; security-6.md change table |
| Security pitfalls 1–5 (@Configuration, lambda, auth manager, auto-detect, defaults) | rule `security.missing-configuration`; security-6.md Pitfalls |
| Servlet namespace in security | jakarta rewrite; security-6.md |
| Testing security (@WithMockUser) | security-6.md |
| Security verification greps | `verify.py`; security-6.md |
| RestClient key differences, GET/POST/exchange/DELETE, config bean, error handling, type refs, full example, WebClient | `restclient.md`; rule `http.resttemplate`; refactor-task step 2; anti_patterns (WebFlux, @Value) |
| Hibernate namespace, ID generation, dialect, JPQL, native, type mappings, fetch | hibernate-6.md; rules `hibernate.id-generation-auto`, `hibernate.temporal`, `config.versioned-dialect` |
| Removed @Type/@TypeDef/legacy generators; example | rules `hibernate.type-annotation`, `hibernate.typedef`; hibernate-6.md |
| Config properties (incl. timezone.default_storage) | hibernate-6.md |
| Testing considerations, troubleshooting errors | hibernate-6.md; build-and-test references |
| Critical: update-from, distinct, Criteria, N+1 | `SOURCE_REWRITES` update-from; rules `hibernate.distinct-join-fetch`, `hibernate.legacy-criteria`; hibernate-6.md |
| Hibernate check/fix commands, performance monitoring | scripts; hibernate-6.md |

## Deliberate-drop log

| Dropped | Rationale |
|---|---|
| Each source's "Overview" paragraph and "Sources" link list (Spring wiki, Baeldung, OpenRewrite docs, Hibernate guide, Thorben Janssen, Quarkus wiki) | Background/attribution, not actionable; the originals remain in `source/`. |
| Spring-boot-migration "Issue 2" before/after showing the same `H2Dialect` line twice | Redundant (no change); kept as the single fact "name unchanged, often auto-detected". |
| Duplicate copies of the SecurityConfig before/after (source shows it twice) and duplicate sed blocks across skills (e.g. EnableGlobalMethodSecurity sed appears twice) | Redundant; one canonical copy kept in `security-6.md`. |
| "Step 1: upgrade to 2.7.x first" as a separate executed step | The rewrite goes straight to 3.2.0 (the task projects are on 2.7); kept as guidance in boot-3-build.md for older projects. |
| Key-differences table cell wording for RestClient | Kept verbatim in restclient.md; not encoded in the graph because it is explanatory. |

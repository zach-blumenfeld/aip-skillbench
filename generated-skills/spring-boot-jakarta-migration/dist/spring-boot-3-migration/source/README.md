# Provenance

Compiled 2026-10-20 from five curated Agent Skills that each covered one slice of the same workflow
(Spring Boot 2.7 / Java 8 → Spring Boot 3.2 / Java 21). Originals are copied verbatim here:

| Source | Covers | Landed in |
|---|---|---|
| `spring-boot-migration/SKILL.md` | parent/Java versions, JAXB removal, jjwt modular, H2 dialect, actuator, OpenRewrite, checklist, order | `scripts/migrate.sh` (pom pass), `scripts/check.sh` ([pom]), `references/pom-and-namespace.md` §1–3, 5–7, SKILL.md workflow |
| `jakarta-namespace/SKILL.md` | javax → jakarta mapping, JDK exceptions, affected annotations, sed batches, verification, OpenRewrite, pitfalls | `scripts/migrate.sh` (source pass, whitelist), `scripts/check.sh` ([namespace]), `references/pom-and-namespace.md` §4, 6, 7, SKILL.md Gotchas |
| `hibernate-upgrade/SKILL.md` | Hibernate 6: IDs, dialects, JPQL/native, types, fetch, removed APIs, HQL `update from`, distinct, Criteria, N+1, monitoring | `scripts/migrate.sh` (HQL + dialect), `scripts/check.sh` ([hibernate]), `references/hibernate-6.md`, client task D |
| `restclient-migration/SKILL.md` | RestTemplate → RestClient: GET/POST/exchange/DELETE, config bean, status handlers, type refs, WebClient | `references/restclient.md`, client task B, `scripts/check.sh` ([restclient]), `semantic_review.http_calls_preserved` |
| `spring-security-6/SKILL.md` | adapter → SecurityFilterChain, @EnableMethodSecurity, lambda DSL, requestMatchers, exception/headers, pitfalls, sed, verification | `scripts/migrate.sh` (renames), `scripts/check.sh` ([security]), `references/spring-security-6.md`, client task A, `semantic_review.security_rules_preserved` |

Task context used for calibration (not copied into the skill): `inputs/instruction.md` (migrate the
`/workspace` user service; gate on `mvn clean compile` and `mvn test`) and `inputs/environment/`
(Ubuntu 24.04 container, SDKMAN Temurin 8 + 21 with 21 default, Maven 3.9.6, mawk, GNU sed, **no python**).
Hence both scripts are bash + POSIX awk/sed/grep only.

# Component-kind choices

| Component | Kind | Why |
|---|---|---|
| 1. Inventory (`check.sh`) | execution | Every finding is a fixed pattern over files (greps, pom fields, conditional rules such as "@Entity ⇒ jakarta.persistence import", "@PreAuthorize ⇒ @EnableMethodSecurity", "@Secured ⇒ securedEnabled"). Same script is the gate in step 5, so before/after use one rule set. |
| 2. Mechanical rewrite (`migrate.sh`) | execution | Version bumps, dependency removal/replacement, package mapping table, annotation and matcher renames, HQL `update from`, dialect/property renames are deterministic lookups. Idempotent so re-runs are safe. |
| 3A. Security rewrite | client_task | Turning an adapter subclass + chained DSL into a SecurityFilterChain bean is code generation over arbitrary structure; sources say "cannot be automated with sed". Reference + checklist + review decision constrain it. |
| 3B. RestClient rewrite | client_task | Each call site differs (headers, bodies, fallbacks, wiring); generated code. |
| 3C. jjwt code | client_task | API-shape rewrite with key-handling judgment (how the secret was decoded). |
| 3D. Hibernate code | client_task | Type/Criteria rewrites depend on the model. |
| 4. `semantic_review` | decision (3 nouls) | Whether rewritten code preserves the original is a judgment with a yes/no answer; false "yes" is the costly error, so close calls leaning yes are reconsidered. |
| 5. Build gate (`check.sh --build`) | execution | `mvn clean compile` / `mvn test` plus result parsing; auto-selects a JDK ≥ 17 from SDKMAN. |
| 5. `build_failure` | decision (choice) | Routing an error to the right reference is a classification over a fixed set; `environment` is separated so the agent does not "fix" network failures in code. |
| 6. Report | client_task | Free-text synthesis. |

Scan and gate were merged into one script (fewer files; identical rules before and after).

# Deliberate drops and deviations

| Source item | Decision | Rationale |
|---|---|---|
| Overview paragraphs, "Key Differences" prose, "Sources" URL lists (all five) | dropped from body | Background/attribution; kept here in the verbatim copies. |
| `sed -i 's/<version>2\.7\.[0-9]*<\/version>/<version>3.2.0<\/version>/g' pom.xml` | replaced | Global sed also rewrites any unrelated dependency pinned at 2.7.x; migrate.sh only touches the starter-parent block, the `spring-boot-dependencies` BOM and `<spring-boot.version>`. |
| `java.version` seds for 1.8 / 8 / 11 only | generalized | migrate.sh rewrites any value below 17, plus `maven.compiler.*` and compiler-plugin settings. |
| Per-package `find … sed 's/import javax\.X/import jakarta.X/'` batches | generalized | One whitelist pass over imports *and* fully qualified names in .java/.kt/.groovy, keeping JDK packages (incl. `javax.transaction.xa`, `javax.annotation.processing`, JSR-305) untouched; source only mapped three `javax.annotation` classes, the whitelist covers the full Jakarta Annotations set. |
| `sed 's/\.regexMatchers(/.requestMatchers(/g'` | not automated | A regex string passed to `requestMatchers(String)` is interpreted as an ant/MVC pattern — silent security change. check.sh fails on `regexMatchers`; the reference gives `RegexRequestMatcher.regexMatcher(...)`. |
| `sed 's/update from /update /g'` over every .java line | narrowed | Applied only when `update from` starts a string literal (any case), so prose like "failed to update from server" is not changed. |
| `spring.jpa.database-platform=H2Dialect` "Before/After" identical snippet | kept as a note | Clarified that the H2Dialect name stays valid and auto-detection makes it optional. |
| OpenRewrite as "recommended" | demoted to alternative | Needs network for recipes and makes broad unreviewed edits; the scripts cover the same ground offline and deterministically. Content kept in `references/pom-and-namespace.md` §6. |

# Additions beyond the sources (verified in the task container)

- Comments/Javadoc are scanned: the task's `SecurityConfig` and `ExternalApiService` Javadoc mention
  `WebSecurityConfigurerAdapter` / `RestTemplate`, which the sources' own "should return NO results" greps would hit.
- H2 console + String `requestMatchers`: verified that Boot 3.2.0 / Security 6.2.0 starts fine with the main
  `application.properties` (H2 console enabled); check.sh fails it only for Boot 3.0/3.1.
- jjwt 0.12 code API table (the `parseClaimsJws` chain no longer compiles on 0.12.3 — verified), DatatypeConverter → Base64,
  `@Secured`/`@RolesAllowed` flags on `@EnableMethodSecurity`, `-parameters` without the starter parent,
  lombok/mysql/hibernate-core coordinate moves, `spring.redis` / `max-http-header-size` / `spring.factories` renames,
  `GenerationType.AUTO` semantics, H2 reserved table names.

# Functional test record

All runs in an image built from `inputs/environment/Dockerfile` (Temurin 21.0.2, Maven 3.9.6):
1. Real task inputs: check (43 FAIL) → migrate (7 files, rerun 0) → client tasks A+B → `check.sh --build`: 0 findings,
   compile OK, no deprecation warnings, tests 6/6. App context also boots with the main (H2-console) properties.
2. Second instance (synthetic orders service, verified 9/9 on Java 8 / Boot 2.7.5 first): jjwt 0.9 code + DatatypeConverter,
   `@XmlRootElement` (JAXB runtime auto-added), `@Secured`, `mvcMatchers`, `.httpBasic()`, `userDetailsServiceBean()`,
   RestTemplateBuilder bean, `javax.sql`/`javax.crypto` (left alone), HQL `update from`, distinct fetch join, lombok 1.18.20,
   mysql-connector-java, `spring.redis.*`, `javax.persistence` property → all client tasks A–D → 0 findings, tests 9/9.
3. Failure branches: un-migrated jjwt code → `FAIL [build]` with the compile error lines; Java 8 on PATH → auto-switch to 21;
   Gradle-only dir and `--boot-version 2.7.0` → exit 2 with message.

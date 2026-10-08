# {meta.name}: manual Spring Boot 3 refactors

Project root: {project_dir}

The mechanical edits are already applied (pom versions, JAXB/activation removal, modular jjwt,
javax -> jakarta for EE packages, EnableGlobalMethodSecurity -> EnableMethodSecurity,
antMatchers/mvcMatchers -> requestMatchers, authorizeRequests -> authorizeHttpRequests,
HQL "update from"). Applied changes:

{changes}

Issues still open (each has id, area, severity, file, line, match, fix):

{remaining_issues}

On a loop back from the build step the state also holds `build_report` (absent on the first
pass): then a previous `mvn` run failed, so fix those compiler/test errors first.

Edit the files under the project root in place. Work area by area; load the matching
reference before touching that area:

1. **security** (`references/security-6.md`): rewrite any class that extends
   WebSecurityConfigurerAdapter into a plain `@Configuration @EnableWebSecurity
   @EnableMethodSecurity(prePostEnabled = true)` class with
   - a `SecurityFilterChain securityFilterChain(HttpSecurity http)` bean in lambda DSL that
     keeps every original rule, matcher, HTTP method, entry point and header setting, in the
     same order, ending with `return http.build();`
   - an `AuthenticationManager authenticationManager(AuthenticationConfiguration)` bean if the
     old class exposed `authenticationManagerBean()`
   - the `PasswordEncoder` bean kept; `configure(AuthenticationManagerBuilder)` and the now
     unused `UserDetailsService` field and adapter/builder imports deleted.
   No `.and()`, no no-arg configurer calls like `.csrf()` or `.headers()`.
2. **http-client** (`references/restclient.md`): replace RestTemplate with RestClient in every
   listed file. Keep method signatures, return values, try/catch fallbacks and logging; use URI
   templates and `ParameterizedTypeReference` for Map/List bodies; null-check bodies; remove
   unused HttpEntity/HttpHeaders/HttpMethod/ResponseEntity imports.
3. **hibernate** (`references/hibernate-6.md`): legacy Criteria -> JPA Criteria;
   `@Type(type=...)`/`@TypeDef` -> `@JdbcTypeCode`/`@Type(Class)`; versioned dialects ->
   unversioned. Advisory items are optional; apply them only when low-risk.
4. **jakarta** (`references/jakarta-namespace.md`): any leftover EE `javax.*`, manual-package
   swaps (import and Maven artifact), persistence.xml namespace. Never touch JDK `javax.*`.
5. **jwt / build** (`references/boot-3-build.md`): jjwt 0.12 API calls; flagged pom items.

Rules:
- Reword comments and Javadoc that still name removed APIs (WebSecurityConfigurerAdapter,
  RestTemplate, EnableGlobalMethodSecurity): verification greps match comments too.
- Do not change behaviour, public APIs, endpoints, tests' expectations, or business logic.
- Migrate test sources too; never delete or disable tests.
- If you judge a blocking issue to be a false positive (e.g. a string literal that only looks
  like an old API), add its `id` to a `waived_issues` list in the state and say why.

Output for the next step: `refactor_notes` (string) — per file, what you changed and why,
plus any waived issue ids with reasons.

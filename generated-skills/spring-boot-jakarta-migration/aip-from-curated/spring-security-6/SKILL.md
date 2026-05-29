---
name: spring-security-6
description: Migrate Spring Security 5 to Spring Security 6 configuration. Use when removing WebSecurityConfigurerAdapter, replacing @EnableGlobalMethodSecurity with @EnableMethodSecurity, converting antMatchers to requestMatchers, or updating to lambda DSL configuration style. Covers SecurityFilterChain beans and authentication manager changes.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a2/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Migrate a Spring Boot 2 / Spring Security 5 codebase to Spring Boot 3 /
  Spring Security 6. The framework removed `WebSecurityConfigurerAdapter`
  and switched to a component-based model: a `@Configuration` class
  exposes a `SecurityFilterChain` `@Bean`, the lambda DSL replaces the
  chained `.and()` DSL, `@EnableGlobalMethodSecurity` is replaced by
  `@EnableMethodSecurity`, and all matcher methods collapse into
  `requestMatchers`. This procedure walks the codebase, applies the
  mechanical text substitutions, refactors the structural pieces that
  cannot be substituted (adapter removal, DSL conversion), updates the
  servlet imports for the Jakarta EE rename, and verifies that no legacy
  patterns remain.

trigger_when:
  - "A class extends `WebSecurityConfigurerAdapter` and the project is on (or moving to) Spring Boot 3."
  - "`@EnableGlobalMethodSecurity` appears anywhere in the codebase."
  - "The build fails on Spring Boot 3 with errors referencing `WebSecurityConfigurerAdapter`, `antMatchers`, `mvcMatchers`, `regexMatchers`, or `authorizeRequests`."
  - "Migrating Spring Boot 2.x → 3.x and security configuration has not been converted yet."
  - "Code uses chained `.csrf().disable().and().sessionManagement()...` style configuration and you are upgrading."
  - "Security tests or filters import `javax.servlet.*`."

do_not_use_when:
  - "Project already targets Spring Boot 3 and a `SecurityFilterChain` bean is already in place — run `verify-migration` only."
  - "Migrating a non-Spring codebase or a Spring MVC project without Spring Security."
  - "The broader Jakarta EE namespace migration (e.g. `javax.persistence`, `javax.validation`) is what's needed — this procedure only covers `javax.servlet.*` because Security configs touch it. Defer the rest to a Jakarta migration skill."

scope_and_approval: >
  The mechanical migration and servlet-import steps rewrite `.java` files
  in place. Run them on a clean working tree (committed or stashed) so
  changes are reviewable via `git diff`. The scan and verify steps are
  read-only. The structural refactor steps (adapter removal, lambda DSL
  conversion) are agent-authored code edits; review them before
  committing.

steps:
  - name: scan-legacy-patterns
    description: >
      Identify every Spring Security 5 legacy pattern in the project.
      Read the JSON output to plan the migration and to confirm which
      structural refactors will be needed.
    script: scripts/scan_legacy_patterns.py
    inputs:
      - name: project-root
        type: string
        description: Absolute or relative path to the project root.
    outputs:
      - name: legacy-report
        type: list[object]
        description: One record per pattern, with `count` and per-file `occurrences`.

  - name: migrate-mechanical
    description: >
      Apply the safe, text-only substitutions across every `.java` file:
      `@EnableGlobalMethodSecurity` → `@EnableMethodSecurity` (annotation
      + import), `antMatchers`/`mvcMatchers`/`regexMatchers` →
      `requestMatchers`, and `authorizeRequests` → `authorizeHttpRequests`.
      Run with `--dry-run` first if the project is large; review the
      printed edit summary; rerun without `--dry-run` to apply.
    script: scripts/migrate_mechanical.py
    depends_on: [scan-legacy-patterns]
    inputs:
      - name: project-root
        type: string
    outputs:
      - name: mechanical-edits
        type: object
        description: JSON with `files_changed` and per-file substitution counts.

  - name: migrate-servlet-imports
    description: >
      Rewrite `javax.servlet.*` imports and fully qualified references
      to `jakarta.servlet.*`. Only the `javax.servlet` namespace is in
      scope here — other Jakarta-renamed namespaces belong to the
      broader Jakarta EE migration.
    script: scripts/migrate_servlet_imports.py
    depends_on: [scan-legacy-patterns]
    inputs:
      - name: project-root
        type: string
    outputs:
      - name: servlet-edits
        type: object

  - name: refactor-adapter-classes
    description: >
      For every class flagged by `scan-legacy-patterns` as extending
      `WebSecurityConfigurerAdapter`, refactor it following
      `references/refactor-templates.md` Template 1: drop the `extends`
      clause, move `configure(HttpSecurity)` body into a
      `SecurityFilterChain @Bean`, replace any
      `authenticationManagerBean()` override with a `@Bean
      AuthenticationManager` that consumes an `AuthenticationConfiguration`,
      and delete any `configure(AuthenticationManagerBuilder)` override
      (`UserDetailsService` is auto-detected). Ensure the class still
      carries `@Configuration` and `@EnableWebSecurity`.
    depends_on: [migrate-mechanical]
    inputs:
      - name: legacy-report
        type: list[object]
    outputs:
      - name: refactored-classes
        type: list[string]
        description: List of file paths refactored.

  - name: convert-lambda-dsl
    description: >
      Inside each `SecurityFilterChain` body, convert any remaining
      chained `.and()` DSL to lambda DSL section-by-section using
      `references/refactor-templates.md` Template 2 (csrf, cors,
      sessionManagement, authorizeHttpRequests, exceptionHandling,
      headers, formLogin, httpBasic, logout, oauth2Login). The final
      statement of the bean must be `return http.build();`. After this
      step the only `.and()` calls remaining should be ones outside the
      security DSL, if any.
    depends_on: [refactor-adapter-classes]
    inputs:
      - name: refactored-classes
        type: list[string]
    outputs:
      - name: dsl-converted-classes
        type: list[string]

  - name: verify-migration
    description: >
      Run the verification script. It fails if any legacy pattern
      remains (WebSecurityConfigurerAdapter, antMatchers, mvcMatchers,
      regexMatchers, authorizeRequests, @EnableGlobalMethodSecurity,
      chained .csrf().disable(), authenticationManagerBean override,
      javax.servlet imports) AND if expected new patterns are missing
      (SecurityFilterChain bean; @EnableMethodSecurity when method-level
      annotations are in use). Iterate on the prior steps until this
      script exits 0.
    script: scripts/verify_migration.py
    depends_on: [convert-lambda-dsl, migrate-servlet-imports]
    inputs:
      - name: project-root
        type: string
    outputs:
      - name: verification-report
        type: object

  - name: compile-and-smoke-test
    description: >
      Run `mvn -DskipTests compile` (or the Gradle equivalent) to confirm
      the security configuration compiles, then run the project's
      security-related tests if any exist (e.g. classes annotated with
      `@SpringBootTest` plus `@WithMockUser` — see Template 5). A
      successful compile is the strongest signal that the structural
      refactor landed correctly; behavioral parity is confirmed by the
      tests.
    depends_on: [verify-migration]
    inputs:
      - name: project-root
        type: string
    outputs:
      - name: build-result
        type: object

scenarios:
  - need: >
      A SecurityConfig class extends WebSecurityConfigurerAdapter,
      overrides configure(HttpSecurity) with chained .csrf().disable()
      DSL, uses .antMatchers("/api/public/**").permitAll(), and is
      annotated @EnableGlobalMethodSecurity(prePostEnabled = true).
    context: >
      `scan-legacy-patterns` reports occurrences of WebSecurityConfigurerAdapter,
      @EnableGlobalMethodSecurity, .antMatchers, .authorizeRequests, and
      the chained .csrf().disable() pattern in this one class.
    action: >
      Run `migrate-mechanical` to convert the annotation and matchers;
      run `migrate-servlet-imports` to update any HttpServletResponse
      import; refactor the class per Template 1 (drop `extends`, expose
      SecurityFilterChain @Bean); convert the DSL per Template 2;
      run `verify-migration`.
    outcome: >
      A single @Configuration class with @EnableWebSecurity,
      @EnableMethodSecurity, a SecurityFilterChain @Bean returning
      http.build(), and (if needed) an AuthenticationManager @Bean
      built from AuthenticationConfiguration. The verification script
      exits 0.

  - need: >
      A small service uses @PreAuthorize on its controller methods but
      has no SecurityFilterChain bean — it relied on Spring Boot 2
      auto-configuration. On Spring Boot 3, method-level security stops
      working silently.
    context: >
      `scan-legacy-patterns` reports zero hits on the legacy DSL but
      method-level annotations exist throughout the controllers, and no
      @EnableMethodSecurity is present.
    action: >
      Add a SecurityConfig class with @Configuration, @EnableWebSecurity,
      and @EnableMethodSecurity, exposing a SecurityFilterChain @Bean
      that permits the project's public paths and requires authentication
      elsewhere. Re-run `verify-migration` — the presence checks should
      now pass.
    outcome: >
      Method-level security is re-activated and verification passes.

anti_patterns:
  - "Removing `extends WebSecurityConfigurerAdapter` but leaving `@Configuration` off the class. The SecurityFilterChain bean never registers and the app starts with default-permissive security."
  - "Keeping the chained DSL after dropping the adapter. `.and()` no longer exists on the new customizers — code won't compile."
  - "Replacing `authenticationManagerBean()` with a `@Bean AuthenticationManager` that calls `new ProviderManager(...)` from scratch. Use `AuthenticationConfiguration.getAuthenticationManager()` so the framework's auto-wired providers (including auto-detected `UserDetailsService`) are reused."
  - "Re-creating the `configure(AuthenticationManagerBuilder)` wiring with a `DaoAuthenticationProvider @Bean`. Spring Security 6 auto-detects `UserDetailsService` beans; explicit wiring is redundant and often masks misconfigurations."
  - "Assuming `@EnableMethodSecurity` enables `@Secured` or `@RolesAllowed`. It enables `@PreAuthorize`/`@PostAuthorize` by default but requires `securedEnabled = true` / `jsr250Enabled = true` for the others."
  - "Migrating only `javax.servlet.*` and declaring the broader Jakarta EE rename done. Other namespaces (`javax.persistence`, `javax.validation`, etc.) are NOT handled by this skill."
  - "Stopping after the absence checks pass. A migration with the SecurityConfig class accidentally deleted also has zero legacy patterns. Run `verify-migration` — it asserts the presence of `SecurityFilterChain` and (when method-level security is used) `@EnableMethodSecurity`."
  - "Forgetting that `mvcMatchers` and `regexMatchers` also collapse into `requestMatchers`, not just `antMatchers`."
```

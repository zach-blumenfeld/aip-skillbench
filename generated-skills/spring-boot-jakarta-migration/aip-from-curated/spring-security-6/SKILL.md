---
name: spring-security-6
description: Migrate Spring Security 5 to Spring Security 6 configuration. Use when removing WebSecurityConfigurerAdapter, replacing @EnableGlobalMethodSecurity with @EnableMethodSecurity, converting antMatchers to requestMatchers, or updating to lambda DSL configuration style. Covers SecurityFilterChain beans and authentication manager changes.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a3
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a3/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Migrate a Java project's Spring Security 5 configuration to Spring Security 6
  (Spring Boot 3). Two classes of change are involved: (a) mechanical textual
  replacements that are safe to apply with sed-style substitution
  (@EnableGlobalMethodSecurity → @EnableMethodSecurity, antMatchers →
  requestMatchers, authorizeRequests → authorizeHttpRequests), and (b)
  structural rewrites that require reasoning over the class body
  (removing WebSecurityConfigurerAdapter and replacing the overridden
  configure() methods with a SecurityFilterChain @Bean; converting the
  chained HttpSecurity DSL to the lambda DSL). Scripts here cover (a) and
  verification; (b) is handled in prose steps the agent reasons through.

trigger_when:
  - Upgrading a Spring Boot 2.x project to Spring Boot 3.x.
  - A class extends WebSecurityConfigurerAdapter and must be refactored.
  - The annotation @EnableGlobalMethodSecurity appears in the codebase.
  - The chained HttpSecurity DSL (e.g., `http.csrf().disable().and()...`) is in use.
  - antMatchers / mvcMatchers / regexMatchers calls appear on the security DSL.
  - authorizeRequests() calls appear on the security DSL.
  - Build fails after a Spring Boot 3 upgrade with errors referencing
    WebSecurityConfigurerAdapter, EnableGlobalMethodSecurity, antMatchers,
    or authorizeRequests.

do_not_use_when:
  - The project is not using Spring Security at all (no spring-security-* deps,
    no security config class).
  - The migration target is the Jakarta EE namespace change (`javax.*` →
    `jakarta.*`). That is a separate concern; use the jakarta migration skill.
  - The project is already on Spring Security 6 and `verify` reports clean.

scope_and_approval: >
  Mechanical replacements modify .java files in place. Run on a clean working
  tree so the diff is reviewable. The `refactor-config-class` and
  `convert-lambda-dsl` steps require judgment — apply edits per security-config
  class, then re-run `verify` before moving on. No network access required.

steps:
  - name: scan-codebase
    description: >
      Inventory every Spring Security 5 pattern in the project. Output is a
      JSON-ish report listing files per deprecated pattern; downstream steps
      use it to decide what work remains.
    script: scripts/scan.sh
    inputs:
      - name: project-root
        type: string
        description: Path to the project root. Defaults to the current directory.
    outputs:
      - name: scan-report
        type: object
        description: >
          Map of deprecated-pattern label → file list and counts. Includes
          WebSecurityConfigurerAdapter extensions, @EnableGlobalMethodSecurity,
          antMatchers/mvcMatchers/regexMatchers, authorizeRequests,
          authenticationManagerBean overrides, and javax.servlet imports.

  - name: apply-mechanical-renames
    description: >
      Apply the textual replacements that are safe to do globally with no
      structural change. Idempotent — re-running on an already-migrated tree
      is a no-op. Does NOT touch WebSecurityConfigurerAdapter classes,
      lambda DSL structure, or javax→jakarta imports; those belong to
      later steps or other skills.
    script: scripts/mechanical_renames.sh
    depends_on: [scan-codebase]
    inputs:
      - name: project-root
        type: string
    outputs:
      - name: files-touched-count
        type: integer
        description: Number of .java files the script ran perl over.

  - name: refactor-config-class
    description: >
      For each class that extends WebSecurityConfigurerAdapter (from the
      scan report), refactor it to a configuration class that defines a
      SecurityFilterChain @Bean. This is a structural rewrite that requires
      reasoning over the class body; do not attempt it with sed.

      Refactor rules per class:
        1. Remove `extends WebSecurityConfigurerAdapter` from the class
           declaration. Ensure `@Configuration` is still present (Spring
           Security 6's @EnableWebSecurity no longer implies it).
        2. Convert the `protected void configure(HttpSecurity http)` override
           to a `@Bean public SecurityFilterChain securityFilterChain(HttpSecurity http)`
           method that returns `http.build()`.
        3. Remove the `protected void configure(AuthenticationManagerBuilder auth)`
           override. The UserDetailsService bean is auto-detected; if the old
           override only wired userDetailsService + passwordEncoder, no
           replacement is needed beyond ensuring both are @Bean / @Service.
        4. Replace any `@Bean public AuthenticationManager authenticationManagerBean()`
           override with a bean that takes an `AuthenticationConfiguration`
           parameter and returns `authConfig.getAuthenticationManager()`.
        5. Drop `@Override` annotations whose superclass methods no longer
           exist after the refactor.

      After editing each file, save and continue to the next. Defer DSL
      lambda conversion to the next step; the goal here is only structural
      class refactor.
    depends_on: [apply-mechanical-renames]
    inputs:
      - name: scan-report
        type: object
    outputs:
      - name: refactored-files
        type: list[string]
        description: Paths of the SecurityConfig classes refactored.

  - name: convert-lambda-dsl
    description: >
      Convert the HttpSecurity DSL from the chained method style to the
      lambda DSL required by Spring Security 6. The change is structural,
      not textual — a blind sed will break parentheses balancing — so
      reason through each `securityFilterChain` method.

      Conversion rules (apply to each affected method):
        - `.csrf().disable()` → `.csrf(csrf -> csrf.disable())`
        - `.cors().and()`     → `.cors(cors -> {})` (or pass a
          ConfigurationSource if one is configured)
        - `.sessionManagement().sessionCreationPolicy(X).and()`
          → `.sessionManagement(session -> session.sessionCreationPolicy(X))`
        - `.authorizeHttpRequests().requestMatchers(...).permitAll()...
            .anyRequest().authenticated().and()`
          → `.authorizeHttpRequests(auth -> auth.requestMatchers(...).permitAll()...
              .anyRequest().authenticated())`
        - `.exceptionHandling().authenticationEntryPoint(X).and()`
          → `.exceptionHandling(ex -> ex.authenticationEntryPoint(X))`
        - `.headers().frameOptions().disable()`
          → `.headers(headers -> headers.frameOptions(frame -> frame.disable()))`

      Drop the trailing `.and()` calls — they no longer chain in lambda DSL.
      Ensure the method still ends with `return http.build();`.
    depends_on: [refactor-config-class]
    inputs:
      - name: refactored-files
        type: list[string]
    outputs:
      - name: lambda-converted-files
        type: list[string]

  - name: verify
    description: >
      Run the verification script. It greps the tree for both the absence
      of every deprecated pattern and the presence of the Spring Security 6
      replacements. Non-zero exit means deprecated patterns remain; loop
      back to the failing pattern's step. If the script reports the
      expected patterns as "absent" but the project has no security
      requirements (e.g., no method-level security), that absence is fine.
    script: scripts/verify.sh
    depends_on: [convert-lambda-dsl]
    inputs:
      - name: project-root
        type: string
    outputs:
      - name: clean
        type: boolean
        description: True iff no deprecated Spring Security 5 patterns remain.

modes:
  - name: full-migration
    body: >
      Default. Run scan → apply-mechanical-renames → refactor-config-class →
      convert-lambda-dsl → verify in order. Use when starting a Spring Boot
      3 upgrade or when verify reports failures across multiple categories.
  - name: mechanical-only
    body: >
      Run scan + apply-mechanical-renames + verify only. Use when the
      project already has SecurityFilterChain @Bean configs and lambda DSL
      but stragglers like antMatchers remain (e.g., after a partial
      hand-migration).
  - name: verify-only
    body: >
      Run only the verify script. Use as a post-migration gate, a CI check,
      or a quick triage when "is this project on Spring Security 6 yet?"
      is the only question.

scenarios:
  - need: >
      A Spring Boot 2 project with a single SecurityConfig class extending
      WebSecurityConfigurerAdapter and the chained DSL.
    context: >
      scan-codebase reports 1 file with WebSecurityConfigurerAdapter, 1 with
      @EnableGlobalMethodSecurity, 4 antMatchers calls, 1 authorizeRequests
      call, and 1 authenticationManagerBean override.
    action: >
      Run full-migration mode. apply-mechanical-renames flips the annotation
      and the matcher calls. refactor-config-class drops the adapter,
      promotes configure(HttpSecurity) to a SecurityFilterChain @Bean, and
      replaces authenticationManagerBean() with the
      AuthenticationConfiguration-based bean. convert-lambda-dsl rewrites
      the chained calls. verify exits 0.
    outcome: >
      Single-class migration in one pass; clean diff suitable for code review.

  - need: >
      Build still fails after a partial hand-migration. Developer already
      created a SecurityFilterChain @Bean but used antMatchers inside it.
    context: >
      scan-codebase reports 0 WebSecurityConfigurerAdapter files but several
      antMatchers / authorizeRequests calls remaining.
    action: >
      Run mechanical-only mode. Mechanical script handles every remaining
      textual replacement; verify confirms clean.
    outcome: >
      Build compiles without touching the structural code the developer
      already wrote.

  - need: >
      CI wants to fail the pipeline if any deprecated Spring Security 5
      pattern reappears.
    context: A green build is the baseline; we want a guardrail going forward.
    action: >
      Run verify-only mode in CI. Exit code 1 fails the pipeline; the
      stdout report lists the offending files.
    outcome: Regression prevention with zero ongoing maintenance.

anti_patterns:
  - Running blind sed across .java files to convert the chained DSL to
    lambda DSL — parentheses and method-chain boundaries do not match a
    simple regex and you will break compilation.
  - Removing the WebSecurityConfigurerAdapter extends clause without
    converting the configure() overrides — the build compiles but security
    is silently disabled.
  - Forgetting that Spring Security 6 no longer implies @Configuration via
    @EnableWebSecurity. If you drop @Configuration thinking it is redundant,
    the SecurityFilterChain @Bean will not be picked up.
  - Bundling the javax→jakarta servlet rename into this skill. That is the
    Jakarta EE migration's responsibility; mixing concerns produces noisy
    diffs that are hard to review.
  - Overriding `authenticationManagerBean()` in the refactored class. That
    method no longer exists on a non-adapter @Configuration class; use the
    AuthenticationConfiguration-based @Bean instead.
  - Assuming `@EnableMethodSecurity` is a drop-in for `@EnableGlobalMethodSecurity`
    in *behaviour*. It enables `@PreAuthorize` / `@PostAuthorize` by default;
    if a project relied on the old defaults being off, this is a behaviour change.
```

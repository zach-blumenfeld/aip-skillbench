# Spring Security 6 Migration Gotchas

Environment-specific facts that defy reasonable assumptions. Load this
file before declaring a migration complete.

## 1. `@Configuration` is no longer implied by `@EnableWebSecurity`

In Spring Security 5, `@EnableWebSecurity` was meta-annotated with
`@Configuration`. In Spring Security 6 it is not. After dropping
`WebSecurityConfigurerAdapter`, make sure the class still carries an
explicit `@Configuration` — otherwise the `SecurityFilterChain @Bean`
will never be registered and the application will start with default
security wide open.

## 2. The chained `.and()` DSL is removed, not just deprecated

Calls like `.csrf().disable().and().sessionManagement()...` won't even
compile against Spring Security 6 — `.and()` no longer exists on the
new lambda-style customizers. Every section must be converted to a
lambda. See `references/refactor-templates.md` Template 2.

## 3. `authenticationManagerBean()` cannot be overridden

The base class is gone. Replace any override of
`authenticationManagerBean()` with a `@Bean AuthenticationManager` that
takes an `AuthenticationConfiguration` and calls
`getAuthenticationManager()` — see Template 1.

## 4. `UserDetailsService` is auto-detected — don't re-wire it

In Spring Security 6 the framework finds your `UserDetailsService` bean
and wires it into the default authentication provider on its own. The
`configure(AuthenticationManagerBuilder)` override is gone for a reason
— do not recreate the wiring with an explicit `DaoAuthenticationProvider
@Bean` unless you genuinely need to override the default password encoder
or user lookup behavior.

## 5. `@EnableMethodSecurity` defaults differ from `@EnableGlobalMethodSecurity`

- `@EnableGlobalMethodSecurity` required `prePostEnabled = true` to turn
  on `@PreAuthorize` / `@PostAuthorize`.
- `@EnableMethodSecurity` enables them **by default**. The
  `prePostEnabled = true` argument is still accepted for explicitness but
  is no longer required.
- `@EnableMethodSecurity` does NOT enable `@Secured` by default — pass
  `securedEnabled = true` if your code uses `@Secured`.
- `@EnableMethodSecurity` does NOT enable JSR-250 (`@RolesAllowed`) by
  default — pass `jsr250Enabled = true` if your code uses it.

## 6. `javax.servlet.*` → `jakarta.servlet.*` is part of this migration

Spring Boot 3 / Spring Security 6 depend on Jakarta EE 9+, which renamed
the `javax.*` namespace to `jakarta.*`. Any security config that touches
`HttpServletRequest`, `HttpServletResponse`, `Filter`, or `FilterChain`
must update its imports. `scripts/migrate_servlet_imports.py` handles the
mechanical rewrite for the `javax.servlet.*` namespace specifically.

**Out of scope for this skill:** other `javax.*` → `jakarta.*` renames
(`javax.persistence`, `javax.validation`, `javax.annotation`, etc.) —
those belong to the broader Spring Boot 3 / Jakarta EE 9 migration.

## 7. `mvcMatchers` and `regexMatchers` also become `requestMatchers`

The original guide highlights `antMatchers → requestMatchers`, but
`mvcMatchers` and `regexMatchers` collapse into `requestMatchers` too.
`scripts/migrate_mechanical.py` handles all three.

## 8. Don't delete `@EnableWebSecurity`

It's still required to bootstrap web security configuration. Only the
*adapter base class* goes away — the `@EnableWebSecurity` annotation
stays on the `@Configuration` class.

## 9. The `/health` actuator and H2 console rules survive

If the pre-migration config exposes `/h2-console/**`, `/actuator/health`,
or similar paths via `permitAll()`, preserve those rules verbatim
(just with `requestMatchers`). Forgetting them is a common silent
regression — the app starts cleanly but operational dashboards or local
H2 dev tools break.

## 10. Verify presence checks, not just absence

A clean grep for legacy patterns is necessary but not sufficient. A
migration where someone deleted the `SecurityConfig` class entirely also
passes the absence check. Run `scripts/verify_migration.py` — it asserts
both `SecurityFilterChain` is present and `@EnableMethodSecurity` is
present when method-level annotations are in use.

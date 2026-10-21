Rewrite the Spring Security configuration of the project at `{workspace}` for Spring Security 6 (Spring Boot 3.2).

The helper script has already renamed `@EnableGlobalMethodSecurity` to `@EnableMethodSecurity`, `antMatchers`/`mvcMatchers` to `requestMatchers`, `authorizeRequests` to `authorizeHttpRequests`, and `javax.servlet` to `jakarta.servlet`. These lines still need hand edits:

{security_findings}

Do this in each affected class:

1. Delete `extends WebSecurityConfigurerAdapter`, both `configure(...)` overrides, `authenticationManagerBean()` and the injected `UserDetailsService` field that only fed `configure(AuthenticationManagerBuilder)`.
2. Add a `@Bean public SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception` that ends with `return http.build();`. Translate every chained call (`csrf().disable()`, `sessionManagement()...and()`, `exceptionHandling()...and()`, `authorizeRequests()...`, `headers().frameOptions().disable()`) to the lambda DSL. Keep every matcher rule, its HTTP method, its order and `anyRequest()` last. Keep the authentication entry point behaviour exactly as it was.
3. If the old class exposed `authenticationManagerBean()`, add `@Bean AuthenticationManager authenticationManager(AuthenticationConfiguration c)` that returns `c.getAuthenticationManager()`.
4. Keep the `PasswordEncoder` bean and every other bean as they are. Keep `@Configuration`, `@EnableWebSecurity` and `@EnableMethodSecurity(prePostEnabled = true)`.
5. Keep plain `requestMatchers("...")` strings. Switch to `AntPathRequestMatcher.antMatcher(...)` only if startup or `contextLoads` fails with "cannot decide whether these patterns are Spring MVC patterns" (Security 6.1.x with a second servlet such as the H2 console).
6. Convert `regexMatchers(...)` to `requestMatchers(RegexRequestMatcher.regexMatcher(...))`, and convert `web.ignoring()` customisations to a `WebSecurityCustomizer` bean.
7. Remove the imports that no longer resolve or are unused.

Load `references/spring-security-6.md` for the full before/after example and gotchas. Do not run Maven yet; the verify step does that.

Answer with `security_changes`: one short paragraph naming the files you changed and what each now contains.

# Spring Security 5 → 6 (Boot 3)

Load this before rewriting any security configuration (client task "Security rewrite"), and when a build
failure is triaged as `security`.

## What changes

| Spring Security 5 / Boot 2 | Spring Security 6 / Boot 3 |
|---|---|
| `class X extends WebSecurityConfigurerAdapter` | plain `@Configuration` class with `@Bean` methods |
| `configure(HttpSecurity http)` override | `@Bean SecurityFilterChain securityFilterChain(HttpSecurity http)` ending in `return http.build();` |
| `configure(AuthenticationManagerBuilder auth)` with `auth.userDetailsService(uds).passwordEncoder(pe)` | delete it: a `UserDetailsService` bean + `PasswordEncoder` bean are auto-detected |
| `@Bean @Override authenticationManagerBean()` | `@Bean AuthenticationManager authenticationManager(AuthenticationConfiguration c) { return c.getAuthenticationManager(); }` |
| `@Bean @Override userDetailsServiceBean()` | plain `@Bean UserDetailsService userDetailsService(...)` |
| `configure(WebSecurity web)` (`web.ignoring()`) | `@Bean WebSecurityCustomizer webSecurityCustomizer()` returning `web -> web.ignoring().requestMatchers(...)` |
| `@EnableGlobalMethodSecurity(prePostEnabled = true)` (REMOVED, will not compile) | `@EnableMethodSecurity(prePostEnabled = true)` (import `...method.configuration.EnableMethodSecurity`) |
| `@EnableGlobalMethodSecurity(securedEnabled = true, jsr250Enabled = true)` | `@EnableMethodSecurity(securedEnabled = true, jsr250Enabled = true)` |
| `.authorizeRequests()` | `.authorizeHttpRequests(auth -> auth ...)` |
| `.antMatchers(...)` / `.mvcMatchers(...)` | `.requestMatchers(...)` (same arguments, incl. `HttpMethod.POST, "/api/users"`) |
| `.regexMatchers("re")` | `.requestMatchers(RegexRequestMatcher.regexMatcher("re"))` — a plain String would be read as an ant pattern |
| `.csrf().disable()` | `.csrf(csrf -> csrf.disable())` |
| `.cors().and()` | `.cors(cors -> cors.configurationSource(corsConfigurationSource()))` or `.cors(Customizer.withDefaults())` |
| `.sessionManagement().sessionCreationPolicy(STATELESS).and()` | `.sessionManagement(session -> session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))` |
| `.exceptionHandling().authenticationEntryPoint(ep).and()` | `.exceptionHandling(ex -> ex.authenticationEntryPoint(ep))` |
| `.headers().frameOptions().disable()` | `.headers(headers -> headers.frameOptions(frame -> frame.disable()))` |
| `.httpBasic()` / `.formLogin()` | `.httpBasic(Customizer.withDefaults())` / `.formLogin(Customizer.withDefaults())` |
| `.and()` chaining | gone: each section is its own lambda |
| `import javax.servlet.http.HttpServletResponse` | `import jakarta.servlet.http.HttpServletResponse` |

## Complete example

Before (Boot 2.x):

```java
@Configuration
@EnableWebSecurity
@EnableGlobalMethodSecurity(prePostEnabled = true)
public class SecurityConfig extends WebSecurityConfigurerAdapter {

    @Autowired
    private UserDetailsService userDetailsService;

    @Bean
    public PasswordEncoder passwordEncoder() { return new BCryptPasswordEncoder(); }

    @Override
    protected void configure(AuthenticationManagerBuilder auth) throws Exception {
        auth.userDetailsService(userDetailsService).passwordEncoder(passwordEncoder());
    }

    @Override
    @Bean
    public AuthenticationManager authenticationManagerBean() throws Exception {
        return super.authenticationManagerBean();
    }

    @Override
    protected void configure(HttpSecurity http) throws Exception {
        http
            .csrf().disable()
            .sessionManagement().sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            .and()
            .exceptionHandling()
                .authenticationEntryPoint((request, response, ex) -> {
                    response.sendError(HttpServletResponse.SC_UNAUTHORIZED, ex.getMessage());
                })
            .and()
            .authorizeRequests()
                .antMatchers(HttpMethod.POST, "/api/users").permitAll()
                .antMatchers("/api/auth/**").permitAll()
                .antMatchers("/h2-console/**").permitAll()
                .antMatchers("/actuator/health").permitAll()
                .anyRequest().authenticated()
            .and()
            .headers().frameOptions().disable();
    }
}
```

After (Boot 3.x):

```java
import org.springframework.security.config.annotation.authentication.configuration.AuthenticationConfiguration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.web.SecurityFilterChain;
import jakarta.servlet.http.HttpServletResponse;

@Configuration
@EnableWebSecurity
@EnableMethodSecurity(prePostEnabled = true)
public class SecurityConfig {

    @Bean
    public PasswordEncoder passwordEncoder() { return new BCryptPasswordEncoder(); }

    @Bean
    public AuthenticationManager authenticationManager(AuthenticationConfiguration authConfig) throws Exception {
        return authConfig.getAuthenticationManager();
    }

    @Bean
    public SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .csrf(csrf -> csrf.disable())
            .sessionManagement(session -> session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .exceptionHandling(ex -> ex
                .authenticationEntryPoint((request, response, authException) ->
                    response.sendError(HttpServletResponse.SC_UNAUTHORIZED, authException.getMessage())))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.POST, "/api/users").permitAll()
                .requestMatchers("/api/auth/**").permitAll()
                .requestMatchers("/h2-console/**").permitAll()
                .requestMatchers("/actuator/health").permitAll()
                .anyRequest().authenticated())
            .headers(headers -> headers.frameOptions(frame -> frame.disable()));
        return http.build();
    }
}
```

The `@Autowired UserDetailsService` field and the `configure(AuthenticationManagerBuilder)` override are
deleted: the `@Service CustomUserDetailsService implements UserDetailsService` bean plus the
`PasswordEncoder` bean are picked up automatically. Keep the `AuthenticationManager` bean whenever the old
config exposed one (something may inject it, e.g. a login controller). Keep the `PasswordEncoder` bean
(services inject it).

## Pitfalls

1. `@EnableWebSecurity` no longer carries `@Configuration`: add `@Configuration` explicitly.
2. Lambda DSL is mandatory in practice: the chained style (`http.csrf().disable().and()...`) is deprecated
   (removal in 7) — convert everything, including `.httpBasic()`/`.formLogin()`.
3. `AuthenticationManager`: use `AuthenticationConfiguration.getAuthenticationManager()`, never
   `super.authenticationManagerBean()`.
4. `UserDetailsService` beans are auto-detected; no `AuthenticationManagerBuilder` wiring.
5. `@EnableMethodSecurity` enables `@PreAuthorize`/`@PostAuthorize` by default (the old annotation did not);
   `@Secured` still needs `securedEnabled = true`, `@RolesAllowed` needs `jsr250Enabled = true`.
6. Preserve rule order exactly: matchers are evaluated top-down; `anyRequest()` must stay last.
7. Boot 3.0/3.1 (Security 6.0/6.1.x) with the H2 console enabled throws at startup on String patterns
   ("cannot decide whether these patterns are Spring MVC patterns or not"); there use
   `requestMatchers(AntPathRequestMatcher.antMatcher("/h2-console/**"))` or `PathRequest.toH2Console()`.
   On Boot 3.2.x (Security 6.2) String patterns boot fine with the H2 console on (verified), so keep them.
8. Comments/Javadoc that still say "WebSecurityConfigurerAdapter" or "needs to be migrated" must be
   rewritten: verification greps match comments too.

## Testing security

Existing `@SpringBootTest` + `@AutoConfigureMockMvc` tests and `@WithMockUser(roles = "ADMIN")` work unchanged
with `spring-security-test`. Do not edit tests to make them pass; fix the configuration.

## Manual verification

```bash
grep -r "WebSecurityConfigurerAdapter\|@EnableGlobalMethodSecurity\|\.antMatchers(\|\.authorizeRequests(" --include="*.java" .   # empty
grep -r "@EnableMethodSecurity\|SecurityFilterChain\|\.requestMatchers(\|\.authorizeHttpRequests(" --include="*.java" .           # present
```
If method-level security annotations are used and `@EnableMethodSecurity` is missing, the migration is incomplete.

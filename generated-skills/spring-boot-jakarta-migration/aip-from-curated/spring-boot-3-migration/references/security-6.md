# Spring Security 5 → 6 (Spring Boot 3)

Spring Security 6 removes `WebSecurityConfigurerAdapter`; configuration is component-based
(`SecurityFilterChain` beans). Lambda DSL is mandatory in practice — the chained
`http.csrf().disable().and()...` style is deprecated and must be converted.

## Complete migration example

### Before (Spring Boot 2.x)

```java
@Configuration
@EnableWebSecurity
@EnableGlobalMethodSecurity(prePostEnabled = true)
public class SecurityConfig extends WebSecurityConfigurerAdapter {

    @Autowired
    private UserDetailsService userDetailsService;

    @Bean
    public PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Override
    protected void configure(AuthenticationManagerBuilder auth) throws Exception {
        auth.userDetailsService(userDetailsService)
            .passwordEncoder(passwordEncoder());
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
            .sessionManagement()
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
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

### After (Spring Boot 3.x)

```java
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.config.annotation.authentication.configuration.AuthenticationConfiguration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableWebSecurity
@EnableMethodSecurity(prePostEnabled = true)
public class SecurityConfig {

    @Bean
    public PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    public AuthenticationManager authenticationManager(
            AuthenticationConfiguration authConfig) throws Exception {
        return authConfig.getAuthenticationManager();
    }

    @Bean
    public SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .csrf(csrf -> csrf.disable())
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .exceptionHandling(ex -> ex
                .authenticationEntryPoint((request, response, authException) -> {
                    response.sendError(HttpServletResponse.SC_UNAUTHORIZED,
                        authException.getMessage());
                })
            )
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.POST, "/api/users").permitAll()
                .requestMatchers("/api/auth/**").permitAll()
                .requestMatchers("/h2-console/**").permitAll()
                .requestMatchers("/actuator/health").permitAll()
                .anyRequest().authenticated()
            )
            .headers(headers -> headers
                .frameOptions(frame -> frame.disable())
            );

        return http.build();
    }
}
```

Keep every rule, matcher, HTTP method and order from the original; only the shape changes.
Drop the `@Autowired UserDetailsService` field once `configure(AuthenticationManagerBuilder)`
is gone (it becomes unused).

## Change-by-change

| Spring Security 5 | Spring Security 6 |
|---|---|
| `extends WebSecurityConfigurerAdapter` + `configure(HttpSecurity)` | `@Bean SecurityFilterChain securityFilterChain(HttpSecurity http)` ending `return http.build();` |
| `configure(AuthenticationManagerBuilder)` with `userDetailsService(...).passwordEncoder(...)` | delete; `UserDetailsService` and `PasswordEncoder` beans are auto-detected |
| `@Bean @Override authenticationManagerBean()` | `@Bean AuthenticationManager authenticationManager(AuthenticationConfiguration c) { return c.getAuthenticationManager(); }` |
| `@EnableGlobalMethodSecurity(prePostEnabled = true)` (import `...method.configuration.EnableGlobalMethodSecurity`) | `@EnableMethodSecurity(prePostEnabled = true)` (import `...method.configuration.EnableMethodSecurity`) — the old annotation **will not compile** in Boot 3 |
| `.authorizeRequests()` | `.authorizeHttpRequests(auth -> auth ...)` |
| `.antMatchers(...)`, `.mvcMatchers(...)` | `.requestMatchers(...)` (same args, incl. `HttpMethod.POST, "/api/users"`) |
| `.regexMatchers("re")` | `.requestMatchers(RegexRequestMatcher.regexMatcher("re"))` |
| `.csrf().disable()` | `.csrf(csrf -> csrf.disable())` |
| `.cors().and()` | `.cors(cors -> cors.configurationSource(corsConfigurationSource()))` (or `Customizer.withDefaults()`) |
| `.sessionManagement().sessionCreationPolicy(X).and()` | `.sessionManagement(session -> session.sessionCreationPolicy(X))` |
| `.exceptionHandling().authenticationEntryPoint(h).and()` | `.exceptionHandling(ex -> ex.authenticationEntryPoint(h))` |
| `.headers().frameOptions().disable()` | `.headers(headers -> headers.frameOptions(frame -> frame.disable()))` |
| `.httpBasic()` / `.formLogin()` | `.httpBasic(Customizer.withDefaults())` / `.formLogin(Customizer.withDefaults())` |
| `.access("hasRole('A') and ...")` | `.access(new WebExpressionAuthorizationManager("..."))` or `hasRole`/`hasAnyRole` |
| `import javax.servlet.http.HttpServletResponse;` | `import jakarta.servlet.http.HttpServletResponse;` |

`UserDetailsService` implementations (`@Service class CustomUserDetailsService implements
UserDetailsService`) need no change — the bean is auto-detected.

## Pitfalls

1. **`@Configuration` is now required separately** — before Security 6 it was part of
   `@EnableWebSecurity`. Add it explicitly.
2. **Lambda DSL is mandatory** — convert every chained configurer; no `.and()`.
3. **AuthenticationManager injection changed** — use `AuthenticationConfiguration.getAuthenticationManager()`.
4. **UserDetailsService auto-detection** — no explicit `AuthenticationManagerBuilder` wiring.
5. **Method security defaults** — `@EnableMethodSecurity` enables `@PreAuthorize`/`@PostAuthorize`
   by default (unlike the old annotation). Custom SpEL beans such as `@userSecurity.isOwner(#id)`
   keep working.
6. The class can no longer be cut by `sed` — refactor the adapter by hand.
7. Comments/Javadoc that still say `WebSecurityConfigurerAdapter` or `EnableGlobalMethodSecurity`
   fail grep-based verification; reword them.

## Testing security

```java
@SpringBootTest
@AutoConfigureMockMvc
class SecurityTests {
    @Test
    @WithMockUser(roles = "ADMIN")
    void adminEndpoint_withAdminUser_shouldSucceed() { /* ... */ }
}
```

## Manual commands (fallback when scripts cannot run; GNU sed)

```bash
grep -r "extends WebSecurityConfigurerAdapter" --include="*.java" .   # refactor by hand
find . -name "*.java" -type f -exec sed -i 's/@EnableGlobalMethodSecurity/@EnableMethodSecurity/g' {} +
find . -name "*.java" -type f -exec sed -i 's/import org.springframework.security.config.annotation.method.configuration.EnableGlobalMethodSecurity/import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity/g' {} +
find . -name "*.java" -type f -exec sed -i 's/\.antMatchers(/.requestMatchers(/g' {} +
find . -name "*.java" -type f -exec sed -i 's/\.mvcMatchers(/.requestMatchers(/g' {} +
find . -name "*.java" -type f -exec sed -i 's/\.authorizeRequests(/.authorizeHttpRequests(/g' {} +
```

## Verification

```bash
# Should return NO results
grep -r "WebSecurityConfigurerAdapter" --include="*.java" .
grep -r "@EnableGlobalMethodSecurity" --include="*.java" .
grep -r "\.antMatchers(" --include="*.java" .
grep -r "\.authorizeRequests(" --include="*.java" .
# Should return results
grep -r "@EnableMethodSecurity" --include="*.java" .
grep -r "SecurityFilterChain" --include="*.java" .
grep -r "\.requestMatchers(" --include="*.java" .
grep -r "\.authorizeHttpRequests(" --include="*.java" .
```

If `@EnableMethodSecurity` is absent but `@PreAuthorize`/`@PostAuthorize` are used, the
migration is incomplete.

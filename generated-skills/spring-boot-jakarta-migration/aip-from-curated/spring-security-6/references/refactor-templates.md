# Spring Security 6 Refactor Templates

Load this file when refactoring `WebSecurityConfigurerAdapter` subclasses
or converting chained-DSL configuration to lambda DSL. Both are structural
changes that cannot be applied with text substitution.

---

## Template 1 — Replace `WebSecurityConfigurerAdapter`

### Before (Spring Security 5 / Spring Boot 2)

```java
@Configuration
@EnableWebSecurity
@EnableGlobalMethodSecurity(prePostEnabled = true)
public class SecurityConfig extends WebSecurityConfigurerAdapter {

    @Autowired
    private UserDetailsService userDetailsService;

    @Override
    protected void configure(AuthenticationManagerBuilder auth) throws Exception {
        auth.userDetailsService(userDetailsService)
            .passwordEncoder(passwordEncoder());
    }

    @Override
    protected void configure(HttpSecurity http) throws Exception {
        http
            .csrf().disable()
            .sessionManagement()
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            .and()
            .authorizeRequests()
                .antMatchers("/api/public/**").permitAll()
                .anyRequest().authenticated();
    }

    @Bean
    @Override
    public AuthenticationManager authenticationManagerBean() throws Exception {
        return super.authenticationManagerBean();
    }
}
```

### After (Spring Security 6 / Spring Boot 3)

```java
@Configuration
@EnableWebSecurity
@EnableMethodSecurity(prePostEnabled = true)
public class SecurityConfig {

    @Bean
    public SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .csrf(csrf -> csrf.disable())
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public/**").permitAll()
                .anyRequest().authenticated()
            );
        return http.build();
    }

    @Bean
    public AuthenticationManager authenticationManager(
            AuthenticationConfiguration authConfig) throws Exception {
        return authConfig.getAuthenticationManager();
    }

    @Bean
    public PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }
}
```

### What changed structurally

1. Removed `extends WebSecurityConfigurerAdapter` — the class is now a
   plain `@Configuration`.
2. `protected void configure(HttpSecurity)` became a `@Bean
   SecurityFilterChain securityFilterChain(HttpSecurity http)` that
   returns `http.build()`.
3. `protected void configure(AuthenticationManagerBuilder)` is gone.
   `UserDetailsService` beans are auto-detected; explicit wiring is no
   longer required.
4. `authenticationManagerBean()` override is replaced with a
   `@Bean AuthenticationManager` that takes an
   `AuthenticationConfiguration` and calls `getAuthenticationManager()`.
5. `@EnableGlobalMethodSecurity` → `@EnableMethodSecurity` (handled by
   `scripts/migrate_mechanical.py`).
6. All chained DSL converted to lambda DSL (see Template 2).
7. `antMatchers` → `requestMatchers`, `authorizeRequests` →
   `authorizeHttpRequests` (handled by `scripts/migrate_mechanical.py`).

---

## Template 2 — Chained DSL → Lambda DSL

Spring Security 6 deprecates `.and()`-chained configuration. Convert each
section to a lambda.

### CSRF

```java
// Before
.csrf().disable()

// After
.csrf(csrf -> csrf.disable())
```

### CORS

```java
// Before
.cors().and()

// After
.cors(Customizer.withDefaults())
// or, with a custom source:
.cors(cors -> cors.configurationSource(corsConfigurationSource()))
```

### Session Management

```java
// Before
.sessionManagement()
    .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
.and()

// After
.sessionManagement(session ->
    session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
```

### Authorization (with matcher migration)

```java
// Before
.authorizeRequests()
    .antMatchers("/public/**").permitAll()
    .antMatchers(HttpMethod.POST, "/api/users").permitAll()
    .anyRequest().authenticated()
.and()

// After
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/public/**").permitAll()
    .requestMatchers(HttpMethod.POST, "/api/users").permitAll()
    .anyRequest().authenticated()
)
```

### Exception Handling

```java
// Before
.exceptionHandling()
    .authenticationEntryPoint((request, response, ex) -> {
        response.sendError(HttpServletResponse.SC_UNAUTHORIZED);
    })
.and()

// After
.exceptionHandling(ex -> ex
    .authenticationEntryPoint((request, response, authException) -> {
        response.sendError(HttpServletResponse.SC_UNAUTHORIZED,
            authException.getMessage());
    })
)
```

### Headers / Frame Options

```java
// Before
.headers().frameOptions().disable()

// After
.headers(headers -> headers
    .frameOptions(frame -> frame.disable())
)
```

### Mechanical conversion rules

When converting chained → lambda by hand:

1. Each section method (`csrf`, `cors`, `sessionManagement`,
   `authorizeHttpRequests`, `exceptionHandling`, `headers`, `formLogin`,
   `httpBasic`, `logout`, `oauth2Login`, etc.) takes a lambda whose
   parameter is the section's customizer.
2. Everything between the section method and the following `.and()` (or
   end of chain) moves inside the lambda.
3. Drop the trailing `.and()` — lambda DSL chains directly off `http`.
4. After all sections are converted, the final statement of the
   `SecurityFilterChain` bean is `return http.build();`.

---

## Template 3 — Servlet imports (Jakarta EE rename)

```java
// Before
import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpServletResponse;
import javax.servlet.Filter;
import javax.servlet.FilterChain;

// After
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.servlet.Filter;
import jakarta.servlet.FilterChain;
```

Handled by `scripts/migrate_servlet_imports.py`. Note: this script ONLY
rewrites the `javax.servlet.*` namespace. Other Jakarta-renamed
namespaces (`javax.persistence`, `javax.validation`, `javax.annotation`,
`javax.mail`, etc.) are out of scope for the Spring Security migration
and belong to the broader Jakarta EE migration.

---

## Template 4 — `UserDetailsService` after migration

In Spring Security 6 the framework auto-detects a `UserDetailsService`
bean and wires it into the default `AuthenticationProvider`. No explicit
wiring is required.

```java
@Service
public class CustomUserDetailsService implements UserDetailsService {

    @Override
    public UserDetails loadUserByUsername(String username) {
        // implementation
    }
}
```

Delete any `configure(AuthenticationManagerBuilder)` overrides during
the `WebSecurityConfigurerAdapter` refactor — the explicit wiring they
performed is now automatic.

---

## Template 5 — Security tests

`@WithMockUser`, `@SpringBootTest`, and `@AutoConfigureMockMvc` are
unchanged across the migration:

```java
@SpringBootTest
@AutoConfigureMockMvc
class SecurityTests {

    @Test
    @WithMockUser(roles = "ADMIN")
    void adminEndpoint_withAdminUser_shouldSucceed() {
        // test implementation
    }
}
```

If a test class imports `javax.servlet.*` for filter assertions, run
`scripts/migrate_servlet_imports.py` against the test source tree as
well.

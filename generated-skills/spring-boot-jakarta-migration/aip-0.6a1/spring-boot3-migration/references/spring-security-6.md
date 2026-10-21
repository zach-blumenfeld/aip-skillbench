# Spring Security 6 Migration Skill

## Overview

Spring Security 6 (included in Spring Boot 3) removes the deprecated `WebSecurityConfigurerAdapter` and introduces a component-based configuration approach using `SecurityFilterChain` beans.

## Key Changes

### 1. Remove WebSecurityConfigurerAdapter

The biggest change is moving from class extension to bean configuration.

#### Before (Spring Security 5 / Spring Boot 2)

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

#### After (Spring Security 6 / Spring Boot 3)

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

### 2. Method Security Annotation Change (CRITICAL)

**This is a required change.** The `@EnableGlobalMethodSecurity` annotation is **removed** in Spring Security 6 and must be replaced with `@EnableMethodSecurity`.

```java
// BEFORE (Spring Security 5 / Spring Boot 2) - WILL NOT COMPILE in Spring Boot 3
@EnableGlobalMethodSecurity(prePostEnabled = true)

// AFTER (Spring Security 6 / Spring Boot 3) - REQUIRED
@EnableMethodSecurity(prePostEnabled = true)
```

#### Import Change

```java
// BEFORE
import org.springframework.security.config.annotation.method.configuration.EnableGlobalMethodSecurity;

// AFTER
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
```

#### Quick Migration Command

```bash
# Replace the annotation in all Java files
find . -name "*.java" -type f -exec sed -i 's/@EnableGlobalMethodSecurity/@EnableMethodSecurity/g' {} +

# Also update the import statement
find . -name "*.java" -type f -exec sed -i 's/EnableGlobalMethodSecurity/EnableMethodSecurity/g' {} +
```

#### Verify @EnableMethodSecurity Is Present

After migration, confirm the new annotation exists:

```bash
# This should return results showing your security config class
grep -r "@EnableMethodSecurity" --include="*.java" .
```

If this returns no results but you're using method-level security (`@PreAuthorize`, `@PostAuthorize`, etc.), the migration is incomplete.

### 3. Lambda DSL Configuration

Spring Security 6 uses lambda-based configuration:

```java
// Before (chained methods)
http
    .csrf().disable()
    .cors().and()
    .sessionManagement().sessionCreationPolicy(SessionCreationPolicy.STATELESS)
    .and()
    .authorizeRequests()
        .antMatchers("/public/**").permitAll()
        .anyRequest().authenticated();

// After (lambda DSL)
http
    .csrf(csrf -> csrf.disable())
    .cors(cors -> cors.configurationSource(corsConfigurationSource()))
    .sessionManagement(session ->
        session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/public/**").permitAll()
        .anyRequest().authenticated()
    );
```

### 4. URL Matching Changes

`antMatchers()` is replaced with `requestMatchers()`:

```java
// Before
.antMatchers("/api/**").authenticated()
.antMatchers(HttpMethod.POST, "/api/users").permitAll()

// After
.requestMatchers("/api/**").authenticated()
.requestMatchers(HttpMethod.POST, "/api/users").permitAll()
```

### 5. Exception Handling

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

### 6. Headers Configuration

```java
// Before
.headers().frameOptions().disable()

// After
.headers(headers -> headers
    .frameOptions(frame -> frame.disable())
)
```

### 7. UserDetailsService Configuration

```java
// The UserDetailsService bean is auto-detected
// No need to explicitly configure in AuthenticationManagerBuilder

@Service
public class CustomUserDetailsService implements UserDetailsService {

    @Override
    public UserDetails loadUserByUsername(String username) {
        // Implementation
    }
}
```

## Complete Migration Example

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

## Servlet Namespace Change

Don't forget the servlet import change:

```java
// Before
import javax.servlet.http.HttpServletResponse;

// After
import jakarta.servlet.http.HttpServletResponse;
```

## Testing Security

Update security test annotations if needed:

```java
@SpringBootTest
@AutoConfigureMockMvc
class SecurityTests {

    @Test
    @WithMockUser(roles = "ADMIN")
    void adminEndpoint_withAdminUser_shouldSucceed() {
        // Test implementation
    }
}
```

## Migration Commands Summary

### Step 1: Remove WebSecurityConfigurerAdapter

```bash
# Find classes extending WebSecurityConfigurerAdapter
grep -r "extends WebSecurityConfigurerAdapter" --include="*.java" .

# The class must be refactored - cannot be automated with sed
```

### Step 2: Replace Method Security Annotation

```bash
# Replace @EnableGlobalMethodSecurity with @EnableMethodSecurity
find . -name "*.java" -type f -exec sed -i 's/@EnableGlobalMethodSecurity/@EnableMethodSecurity/g' {} +

# Update import
find . -name "*.java" -type f -exec sed -i 's/import org.springframework.security.config.annotation.method.configuration.EnableGlobalMethodSecurity/import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity/g' {} +
```

### Step 3: Replace antMatchers with requestMatchers

```bash
# Replace antMatchers
find . -name "*.java" -type f -exec sed -i 's/\.antMatchers(/.requestMatchers(/g' {} +

# Replace mvcMatchers
find . -name "*.java" -type f -exec sed -i 's/\.mvcMatchers(/.requestMatchers(/g' {} +

# Replace regexMatchers
find . -name "*.java" -type f -exec sed -i 's/\.regexMatchers(/.requestMatchers(/g' {} +
```

### Step 4: Replace authorizeRequests with authorizeHttpRequests

```bash
find . -name "*.java" -type f -exec sed -i 's/\.authorizeRequests(/.authorizeHttpRequests(/g' {} +
```

## Verification Commands

### Verify No Deprecated Patterns Remain

```bash
# Should return NO results
grep -r "WebSecurityConfigurerAdapter" --include="*.java" .
grep -r "@EnableGlobalMethodSecurity" --include="*.java" .
grep -r "\.antMatchers(" --include="*.java" .
grep -r "\.authorizeRequests(" --include="*.java" .
```

### Verify New Patterns Are Present

```bash
# Should return results
grep -r "@EnableMethodSecurity" --include="*.java" .
grep -r "SecurityFilterChain" --include="*.java" .
grep -r "\.requestMatchers(" --include="*.java" .
grep -r "\.authorizeHttpRequests(" --include="*.java" .
```

## Common Migration Pitfalls

1. **@Configuration is now required separately** - Before Spring Security 6, `@Configuration` was part of `@EnableWebSecurity`. Now you must add it explicitly.

2. **Lambda DSL is mandatory** - The old chained method style (`http.csrf().disable().and()...`) is deprecated and must be converted to lambda style.

3. **AuthenticationManager injection changed** - Use `AuthenticationConfiguration.getAuthenticationManager()` instead of overriding `authenticationManagerBean()`.

4. **UserDetailsService auto-detection** - Spring Security 6 automatically detects `UserDetailsService` beans; no need for explicit configuration.

5. **Method security default changes** - `@EnableMethodSecurity` enables `@PreAuthorize` and `@PostAuthorize` by default (unlike the old annotation).

## Sources

- [Baeldung - Migrate from Spring Security 5 to 6](https://www.baeldung.com/spring-security-migrate-5-to-6)
- [Baeldung - Upgrading Deprecated WebSecurityConfigurerAdapter](https://www.baeldung.com/spring-deprecated-websecurityconfigureradapter)
- [Spring Security 6 Reference](https://docs.spring.io/spring-security/reference/)

## Gotchas (added when compiling this skill)

- **`requestMatchers(String...)` with more than one servlet.** Plain string matchers are the default and work on Spring Boot 3.2 / Security 6.2. This was verified with the H2 console servlet enabled: the app starts. Some Security 6.1.x releases instead throw `This method cannot decide whether these patterns are Spring MVC patterns or not` at startup when a second servlet (for example the H2 console) is registered. Test profiles often disable the console, so `mvn test` can stay green while the app cannot start. Only if you see that message, wrap the patterns explicitly:

  ```java
  import static org.springframework.security.web.util.matcher.AntPathRequestMatcher.antMatcher;

  .requestMatchers(antMatcher(HttpMethod.POST, "/api/users")).permitAll()
  .requestMatchers(antMatcher("/h2-console/**")).permitAll()
  ```
- **`regexMatchers(...)` is not a rename.** `requestMatchers(String)` treats its argument as a path pattern, not a regex. Convert with `requestMatchers(RegexRequestMatcher.regexMatcher("^/api/v[0-9]+/.*"))` (`org.springframework.security.web.util.matcher.RegexRequestMatcher`). The helper script deliberately leaves `regexMatchers` for you.
- **Keep every rule, in order.** The first matching rule wins; copy each `antMatchers`/`permitAll`/`hasRole` line into the lambda in the same order, keep `anyRequest()` last.
- **Delete, don't adapt, the adapter overrides.** Remove `extends WebSecurityConfigurerAdapter`, both `configure(...)` overrides, `authenticationManagerBean()`, and the `@Autowired UserDetailsService` field that only fed `configure(AuthenticationManagerBuilder)`. With exactly one `UserDetailsService` bean and one `PasswordEncoder` bean, Spring Security builds the `DaoAuthenticationProvider` itself. Expose an `AuthenticationManager` bean from `AuthenticationConfiguration` if anything injects one (the old `authenticationManagerBean()` was a public bean).
- **Keep the `PasswordEncoder` bean where it was.** Services such as `UserService` inject it; moving or renaming it breaks wiring.
- `csrf(AbstractHttpConfigurer::disable)` and `headers(h -> h.frameOptions(HeadersConfigurer.FrameOptionsConfig::disable))` are the idiomatic method-reference forms; `csrf(csrf -> csrf.disable())` is equally fine. Chained no-arg forms (`csrf()`, `headers()`, `.and()`) are deprecated in 6.1+ and removed in 7, and the verify step reports them.
- Remove imports that no longer resolve or are now unused (`WebSecurityConfigurerAdapter`, `AuthenticationManagerBuilder`, `Autowired`, `UserDetailsService`); `javax.servlet.http.HttpServletResponse` is now `jakarta.servlet.http.HttpServletResponse`.

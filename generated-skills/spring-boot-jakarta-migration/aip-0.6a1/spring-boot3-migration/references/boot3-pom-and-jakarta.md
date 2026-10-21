# Spring Boot 2 to 3 Migration Skill

## Overview

This skill provides guidance for migrating Spring Boot applications from version 2.x to 3.x, which is one of the most significant upgrades in Spring Boot history due to the Java EE to Jakarta EE transition.

## Key Migration Steps

### 1. Update Spring Boot Version

Change the parent POM version:

```xml
<!-- Before: Spring Boot 2.7.x -->
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>2.7.18</version>
</parent>

<!-- After: Spring Boot 3.2.x -->
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.2.0</version>
</parent>
```

### 2. Update Java Version

Spring Boot 3 requires Java 17 or later:

```xml
<properties>
    <!-- Before -->
    <java.version>1.8</java.version>

    <!-- After -->
    <java.version>21</java.version>
</properties>
```

### 3. Remove Deprecated Dependencies (CRITICAL: JAXB API)

**You MUST remove the old `javax.xml.bind:jaxb-api` dependency.** This is a Java EE dependency that was commonly added for Java 9+ compatibility in Spring Boot 2.x projects, but it conflicts with Jakarta EE in Spring Boot 3.

#### Dependencies to REMOVE from pom.xml

```xml
<!-- REMOVE ALL OF THESE - they are incompatible with Spring Boot 3 -->

<!-- Old JAXB API - MUST BE REMOVED -->
<dependency>
    <groupId>javax.xml.bind</groupId>
    <artifactId>jaxb-api</artifactId>
</dependency>

<!-- Old JAXB Implementation - MUST BE REMOVED -->
<dependency>
    <groupId>com.sun.xml.bind</groupId>
    <artifactId>jaxb-impl</artifactId>
</dependency>

<dependency>
    <groupId>com.sun.xml.bind</groupId>
    <artifactId>jaxb-core</artifactId>
</dependency>

<!-- Old Java Activation - MUST BE REMOVED -->
<dependency>
    <groupId>javax.activation</groupId>
    <artifactId>activation</artifactId>
</dependency>

<dependency>
    <groupId>javax.activation</groupId>
    <artifactId>javax.activation-api</artifactId>
</dependency>
```

#### Why Remove These?

1. **Namespace Conflict**: `javax.xml.bind` uses the old Java EE namespace, which conflicts with Jakarta EE's `jakarta.xml.bind`
2. **Spring Boot 3 Includes Jakarta XML Bind**: If you need XML binding, Spring Boot 3 transitively includes the Jakarta versions
3. **Build Failures**: Having both `javax.xml.bind` and `jakarta.xml.bind` on the classpath causes ClassNotFoundException and other runtime errors

#### If You Need XML Binding in Spring Boot 3

Use the Jakarta versions instead:

```xml
<!-- Only add these if you actually need XML binding -->
<dependency>
    <groupId>jakarta.xml.bind</groupId>
    <artifactId>jakarta.xml.bind-api</artifactId>
</dependency>
<dependency>
    <groupId>org.glassfish.jaxb</groupId>
    <artifactId>jaxb-runtime</artifactId>
</dependency>
```

#### Quick Check for Old JAXB Dependencies

```bash
# Check if old JAXB is in your pom.xml
grep -E "javax\.xml\.bind|jaxb-api" pom.xml

# If this returns any results, you need to remove those dependencies
```

#### Verify Removal

After removing, confirm no old JAXB references remain:

```bash
# This should return NO results
grep -E "<artifactId>jaxb-api</artifactId>" pom.xml
grep -E "javax\.xml\.bind" pom.xml
```

### 4. Update JWT Library

The old `jjwt` library needs to be replaced with the newer modular version:

```xml
<!-- Before -->
<dependency>
    <groupId>io.jsonwebtoken</groupId>
    <artifactId>jjwt</artifactId>
    <version>0.9.1</version>
</dependency>

<!-- After -->
<dependency>
    <groupId>io.jsonwebtoken</groupId>
    <artifactId>jjwt-api</artifactId>
    <version>0.12.3</version>
</dependency>
<dependency>
    <groupId>io.jsonwebtoken</groupId>
    <artifactId>jjwt-impl</artifactId>
    <version>0.12.3</version>
    <scope>runtime</scope>
</dependency>
<dependency>
    <groupId>io.jsonwebtoken</groupId>
    <artifactId>jjwt-jackson</artifactId>
    <version>0.12.3</version>
    <scope>runtime</scope>
</dependency>
```

## Common Issues

### Issue 1: Compilation Errors After Upgrade

After changing the Spring Boot version, you'll see many compilation errors related to `javax.*` imports. These need to be changed to `jakarta.*` (see Jakarta Namespace skill).

### Issue 2: H2 Database Dialect

The H2 dialect class name changed:

```properties
# Before
spring.jpa.database-platform=org.hibernate.dialect.H2Dialect

# After
spring.jpa.database-platform=org.hibernate.dialect.H2Dialect
# Note: In Hibernate 6, this is often auto-detected and may not need explicit configuration
```

### Issue 3: Actuator Endpoints

Actuator endpoint paths have changed. Review your security configuration if you're exposing actuator endpoints.

## Migration Commands

### Update pom.xml with sed

```bash
# Update Spring Boot parent version
sed -i 's/<version>2\.7\.[0-9]*<\/version>/<version>3.2.0<\/version>/g' pom.xml

# Update Java version
sed -i 's/<java.version>1\.8<\/java.version>/<java.version>21<\/java.version>/g' pom.xml
sed -i 's/<java.version>8<\/java.version>/<java.version>21<\/java.version>/g' pom.xml
sed -i 's/<java.version>11<\/java.version>/<java.version>21<\/java.version>/g' pom.xml

# Remove old JAXB dependency (multi-line removal is complex - manual removal recommended)
```

### Remove Deprecated Dependencies

```bash
# Check for old JAXB dependencies
grep -n "jaxb-api\|javax\.xml\.bind" pom.xml

# These must be manually removed from pom.xml:
# - javax.xml.bind:jaxb-api
# - com.sun.xml.bind:jaxb-impl
# - com.sun.xml.bind:jaxb-core
```

## Using OpenRewrite for Automated Migration

OpenRewrite is the recommended tool for large-scale migrations:

### Add OpenRewrite Plugin to pom.xml

```xml
<plugin>
    <groupId>org.openrewrite.maven</groupId>
    <artifactId>rewrite-maven-plugin</artifactId>
    <version>5.42.0</version>
    <configuration>
        <activeRecipes>
            <recipe>org.openrewrite.java.spring.boot3.UpgradeSpringBoot_3_2</recipe>
        </activeRecipes>
    </configuration>
    <dependencies>
        <dependency>
            <groupId>org.openrewrite.recipe</groupId>
            <artifactId>rewrite-spring</artifactId>
            <version>5.21.0</version>
        </dependency>
    </dependencies>
</plugin>
```

### Run OpenRewrite Migration

```bash
mvn rewrite:run
```

This will automatically:
- Update Spring Boot version
- Migrate `javax.*` to `jakarta.*` imports
- Update deprecated Spring Security patterns
- Fix property name changes

## Verification Steps

### Check Spring Boot Version

```bash
# Should show 3.x version
grep -A2 "spring-boot-starter-parent" pom.xml | grep version
```

### Check Java Version

```bash
# Should show 17 or 21
grep "java.version" pom.xml
```

### Check for Old Dependencies

```bash
# All should return NO results
grep "jaxb-api" pom.xml
grep "javax\.xml\.bind" pom.xml
grep "<version>0\.9\.1</version>" pom.xml  # Old jjwt version
```

### Compile and Test

```bash
# Compile the project
mvn clean compile

# Run tests
mvn test
```

## Migration Checklist

- [ ] Update `spring-boot-starter-parent` version to 3.2.x
- [ ] Update `java.version` to 17 or 21
- [ ] Remove `javax.xml.bind:jaxb-api` and related JAXB dependencies
- [ ] Remove old `io.jsonwebtoken:jjwt` if present, replace with modular jjwt
- [ ] Run `mvn clean compile` to identify remaining issues
- [ ] Fix all `javax.*` to `jakarta.*` imports
- [ ] Update Spring Security configuration (see Spring Security 6 skill)
- [ ] Replace RestTemplate with RestClient (see RestClient Migration skill)
- [ ] Run tests to verify functionality

## Recommended Migration Order

1. **First**: Upgrade to Spring Boot 2.7.x (latest 2.x) if not already
2. **Second**: Update Java version to 17 or 21
3. **Third**: Remove incompatible dependencies (JAXB, old JWT)
4. **Fourth**: Update Spring Boot parent to 3.2.x
5. **Fifth**: Fix namespace imports (javax → jakarta)
6. **Sixth**: Update Spring Security configuration
7. **Seventh**: Update HTTP clients (RestTemplate → RestClient)
8. **Finally**: Run full test suite

## Sources

- [Spring Boot 3.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.0-Migration-Guide)
- [OpenRewrite Spring Boot 3 Migration](https://docs.openrewrite.org/running-recipes/popular-recipe-guides/migrate-to-spring-3)
- [Baeldung - Migrate to Spring Boot 3](https://www.baeldung.com/spring-boot-3-migration)

---

# Jakarta EE Namespace Migration Skill

## Overview

Spring Boot 3.0 has upgraded from Java EE to Jakarta EE APIs for all dependencies. This is one of the most significant breaking changes and requires updating all `javax.*` package imports to `jakarta.*`.

**Important:** Packages such as `javax.sql.*` and `javax.crypto.*` will NOT change to `jakarta.*` as they are part of the Java 17+ JDK itself, not part of Java EE.

## Required Package Mappings

| Before (Java EE) | After (Jakarta EE) |
|------------------|-------------------|
| `javax.persistence.*` | `jakarta.persistence.*` |
| `javax.validation.*` | `jakarta.validation.*` |
| `javax.servlet.*` | `jakarta.servlet.*` |
| `javax.annotation.*` | `jakarta.annotation.*` |
| `javax.transaction.*` | `jakarta.transaction.*` |
| `javax.ws.rs.*` | `jakarta.ws.rs.*` |
| `javax.mail.*` | `jakarta.mail.*` |
| `javax.jms.*` | `jakarta.jms.*` |
| `javax.xml.bind.*` | `jakarta.xml.bind.*` |

## Affected Annotations and Classes

### Persistence (JPA)
- `@Entity`, `@Table`, `@Column`
- `@Id`, `@GeneratedValue`
- `@ManyToOne`, `@OneToMany`, `@ManyToMany`, `@OneToOne`
- `@JoinColumn`, `@JoinTable`
- `@PrePersist`, `@PreUpdate`, `@PostLoad`
- `@Enumerated`, `@Temporal`
- `EntityManager`, `EntityManagerFactory`
- `EntityNotFoundException`

### Validation
- `@Valid`
- `@NotNull`, `@NotBlank`, `@NotEmpty`
- `@Size`, `@Min`, `@Max`
- `@Email`, `@Pattern`
- `@Positive`, `@Negative`
- `@Past`, `@Future`

### Servlet
- `HttpServletRequest`, `HttpServletResponse`
- `ServletException`
- `Filter`, `FilterChain`
- `HttpSession`, `Cookie`

## Migration Commands

### Step 1: Find All javax Imports That Need Migration

```bash
# List all files with javax imports that need migration (excludes JDK packages)
grep -r "import javax\." --include="*.java" . | grep -v "javax.sql" | grep -v "javax.crypto" | grep -v "javax.net"
```

### Step 2: Batch Replace All Namespaces

```bash
# Replace javax.persistence with jakarta.persistence
find . -name "*.java" -type f -exec sed -i 's/import javax\.persistence/import jakarta.persistence/g' {} +

# Replace javax.validation with jakarta.validation
find . -name "*.java" -type f -exec sed -i 's/import javax\.validation/import jakarta.validation/g' {} +

# Replace javax.servlet with jakarta.servlet
find . -name "*.java" -type f -exec sed -i 's/import javax\.servlet/import jakarta.servlet/g' {} +

# Replace javax.annotation (common ones used in Spring)
find . -name "*.java" -type f -exec sed -i 's/import javax\.annotation\.PostConstruct/import jakarta.annotation.PostConstruct/g' {} +
find . -name "*.java" -type f -exec sed -i 's/import javax\.annotation\.PreDestroy/import jakarta.annotation.PreDestroy/g' {} +
find . -name "*.java" -type f -exec sed -i 's/import javax\.annotation\.Resource/import jakarta.annotation.Resource/g' {} +

# Replace javax.transaction with jakarta.transaction
find . -name "*.java" -type f -exec sed -i 's/import javax\.transaction/import jakarta.transaction/g' {} +
```

### Step 3: Handle Wildcard Imports

```bash
# Replace wildcard imports
find . -name "*.java" -type f -exec sed -i 's/import javax\.persistence\.\*/import jakarta.persistence.*/g' {} +
find . -name "*.java" -type f -exec sed -i 's/import javax\.validation\.\*/import jakarta.validation.*/g' {} +
find . -name "*.java" -type f -exec sed -i 's/import javax\.servlet\.\*/import jakarta.servlet.*/g' {} +
```

## Critical: Entity Classes Must Use jakarta.persistence

After migration, **every JPA entity class MUST have jakarta.persistence imports**. This is a hard requirement for Spring Boot 3.

### Example Entity Migration

```java
// BEFORE (Spring Boot 2.x) - WILL NOT COMPILE in Spring Boot 3
import javax.persistence.Entity;
import javax.persistence.Table;
import javax.persistence.Id;
import javax.persistence.GeneratedValue;
import javax.persistence.GenerationType;

@Entity
@Table(name = "users")
public class User {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;
}

// AFTER (Spring Boot 3.x) - REQUIRED
import jakarta.persistence.Entity;
import jakarta.persistence.Table;
import jakarta.persistence.Id;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;

@Entity
@Table(name = "users")
public class User {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;
}
```

### Example Validation Migration

```java
// BEFORE
import javax.validation.constraints.Email;
import javax.validation.constraints.NotBlank;
import javax.validation.Valid;

// AFTER
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.Valid;
```

### Example Servlet Migration

```java
// BEFORE
import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpServletResponse;

// AFTER
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
```

## Verification

### Verify No Old javax Imports Remain

```bash
# These commands should return NO results after migration
grep -r "import javax\.persistence" --include="*.java" .
grep -r "import javax\.validation" --include="*.java" .
grep -r "import javax\.servlet" --include="*.java" .

# Combined check for all Java EE packages
grep -r "import javax\." --include="*.java" . | grep -E "(persistence|validation|servlet|transaction|annotation\.(PostConstruct|PreDestroy|Resource))"
```

### Verify jakarta Imports Are Present

```bash
# These MUST return results showing your migrated classes
grep -r "import jakarta\.persistence" --include="*.java" .
grep -r "import jakarta\.validation" --include="*.java" .
```

**If the jakarta.persistence grep returns no results but you have JPA entities, the migration is incomplete and will fail.**

## Using OpenRewrite for Automated Migration

OpenRewrite can automate the entire namespace migration:

```xml
<!-- Add to pom.xml plugins section -->
<plugin>
    <groupId>org.openrewrite.maven</groupId>
    <artifactId>rewrite-maven-plugin</artifactId>
    <version>5.42.0</version>
    <configuration>
        <activeRecipes>
            <recipe>org.openrewrite.java.migrate.jakarta.JavaxMigrationToJakarta</recipe>
        </activeRecipes>
    </configuration>
    <dependencies>
        <dependency>
            <groupId>org.openrewrite.recipe</groupId>
            <artifactId>rewrite-migrate-java</artifactId>
            <version>2.26.0</version>
        </dependency>
    </dependencies>
</plugin>
```

Then run:
```bash
mvn rewrite:run
```

## Common Pitfalls

1. **Don't change javax.sql or javax.crypto** - These are JDK packages, not Java EE
2. **Check test files too** - Test classes also need migration
3. **Update XML configurations** - If using persistence.xml, update namespaces there too
4. **Third-party libraries** - Ensure all dependencies have Jakarta EE compatible versions
5. **Mixed namespaces cause runtime errors** - All must be migrated together

## Sources

- [Spring Boot 3.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.0-Migration-Guide)
- [Baeldung - Migrate to Spring Boot 3](https://www.baeldung.com/spring-boot-3-migration)
- [OpenRewrite Jakarta Migration](https://docs.openrewrite.org/running-recipes/popular-recipe-guides/migrate-to-spring-3)

---

# Compile/test failures after the upgrade: common causes (added when compiling this skill)

- **Wrong JDK.** `mvn` must run on JDK 17+ (target 21). In the task container `JAVA_HOME` is Java 21; if `java -version` shows 1.8, run `source /root/.sdkman/bin/sdkman-init.sh && sdk use java 21.0.2-tem`. Error signature: `release version 21 not supported` or `invalid target release`.
- **`HttpStatus` vs `HttpStatusCode`.** `ResponseEntity.getStatusCode()`, `ClientHttpResponse.getStatusCode()` and `ResponseStatusException.getStatusCode()` return `HttpStatusCode`. Assigning them to `HttpStatus` fails to compile: compare `.value()` or use `HttpStatus.valueOf(code.value())`. `getStatusCodeValue()` and `getRawStatusCode()` are deprecated: use `getStatusCode().value()`. `ResponseStatusException.getStatus()` is gone: use `getStatusCode()`.
- **Removed Spring 5 adapters.** `WebMvcConfigurerAdapter` becomes `implements WebMvcConfigurer`; `HandlerInterceptorAdapter` becomes `implements HandlerInterceptor`.
- **`@ConstructorBinding`** moved to `org.springframework.boot.context.properties.bind.ConstructorBinding` and is unnecessary on a single-constructor `@ConfigurationProperties` class.
- **Auto-configuration registration.** `META-INF/spring.factories` `EnableAutoConfiguration` entries move to `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`.
- **Trailing-slash matching is off** in Spring 6. `/api/users/` no longer matches `@GetMapping("/api/users")`, so fix tests or clients that relied on it.
- **Renamed properties.** For example `spring.redis.*` became `spring.data.redis.*`. Adding `org.springframework.boot:spring-boot-properties-migrator` (runtime scope) temporarily prints every renamed key at startup; remove it afterwards.
- **Lombok on JDK 21** needs 1.18.30+. Let Boot 3.2 manage the version.
- **Bean wiring failures in `contextLoads`.** Read the first `Caused by:` in the test log. Typical causes are a removed `authenticationManagerBean()` that something still injects, a circular dependency between a security config and a service, or JPQL that Hibernate 6 rejects.
- Fix the root cause in source. Never delete, `@Disabled` or weaken existing tests to get a green build.

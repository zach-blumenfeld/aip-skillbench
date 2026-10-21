# pom.xml, dependencies, jjwt and the javax → jakarta namespace

Load this when `scripts/check.sh` reports `[pom]`, `[namespace]`, `[jjwt]` or `[config]` findings that
`scripts/migrate.sh` did not clear, when the project is Gradle (apply the same changes by hand), or when
a compile error points at a dependency or an import.

## 1. Versions

```xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.2.0</version>          <!-- was 2.7.x -->
</parent>
<properties>
    <java.version>21</java.version>   <!-- was 1.8 / 8 / 11; Boot 3 needs 17+ -->
</properties>
```

- Projects that import `spring-boot-dependencies` as a BOM or set `<spring-boot.version>` need the same bump.
- `maven.compiler.source/target/release` and `maven-compiler-plugin` `<source>/<target>/<release>` must
  follow `java.version` (migrate.sh rewrites any value below 17).
- Not using `spring-boot-starter-parent`? Add `<parameters>true</parameters>` to `maven-compiler-plugin`:
  Spring 6.1 no longer reads parameter names from debug info, so `@PathVariable Long id` without a name and
  `@PreAuthorize("... #id")` break without `-parameters`. The starter parent already sets it.
- Recommended order if doing it by hand: (1) be on latest 2.7.x, (2) Java 17/21, (3) remove JAXB/old JWT,
  (4) parent 3.2.x, (5) javax → jakarta, (6) Spring Security 6, (7) RestTemplate → RestClient, (8) full tests.

## 2. Dependencies to remove (CRITICAL: JAXB)

Remove every one of these. They are Java EE (`javax.*`) artifacts commonly added for Java 9+ in Boot 2
projects; with Boot 3 they clash with Jakarta EE (`javax.xml.bind` vs `jakarta.xml.bind` on one classpath
gives ClassNotFoundException and other runtime errors).

| groupId | artifactId |
|---|---|
| `javax.xml.bind` | `jaxb-api` |
| `com.sun.xml.bind` | `jaxb-impl`, `jaxb-core` |
| `javax.activation` | `activation`, `javax.activation-api` |

Only if the code really uses XML binding (`@XmlRootElement`, `JAXBContext`…), add the Jakarta versions
(versions come from Boot's BOM; migrate.sh adds them automatically when code imports `jakarta.xml.bind`):

```xml
<dependency>
    <groupId>jakarta.xml.bind</groupId>
    <artifactId>jakarta.xml.bind-api</artifactId>
</dependency>
<dependency>
    <groupId>org.glassfish.jaxb</groupId>
    <artifactId>jaxb-runtime</artifactId>
</dependency>
```

`javax.xml.bind.DatatypeConverter` used only for Base64 → replace with `java.util.Base64`
(`Base64.getDecoder().decode(s)` / `Base64.getEncoder().encodeToString(b)`) instead of keeping JAXB.

Other coordinate moves migrate.sh applies: `javax.servlet:javax.servlet-api` → `jakarta.servlet:jakarta.servlet-api`,
`javax.validation:validation-api` → `jakarta.validation:jakarta.validation-api`, `javax.persistence-api` →
`jakarta.persistence:jakarta.persistence-api`, `javax.annotation-api` → `jakarta.annotation:jakarta.annotation-api`,
`javax.inject` → `jakarta.inject:jakarta.inject-api`, `javax.transaction-api` → `jakarta.transaction:jakarta.transaction-api`,
`mysql:mysql-connector-java` → `com.mysql:mysql-connector-j`, `org.hibernate:hibernate-core` → `org.hibernate.orm:hibernate-core`
(all without explicit versions), and drops an explicit `lombok` version (old Lombok fails on Java 21).
Flagged for manual replacement: `io.springfox` → `org.springdoc:springdoc-openapi-starter-webmvc-ui` 2.x;
`com.vladmihalcea:hibernate-types-*` → `io.hypersistence:hypersistence-utils-hibernate-63`.
Third-party libraries in general must have Jakarta-compatible versions.

## 3. jjwt 0.9.1 → modular 0.12.3

```xml
<!-- Before -->
<dependency><groupId>io.jsonwebtoken</groupId><artifactId>jjwt</artifactId><version>0.9.1</version></dependency>
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

Code that uses jjwt must move to the 0.12 API (the old parser chain no longer compiles:
`parseClaimsJws` is not on `JwtParserBuilder`):

| 0.9.x | 0.12.x |
|---|---|
| `Jwts.parser().setSigningKey(k).parseClaimsJws(t).getBody()` | `Jwts.parser().verifyWith(secretKey).build().parseSignedClaims(t).getPayload()` |
| `.signWith(SignatureAlgorithm.HS256, bytesOrString)` | `.signWith(Keys.hmacShaKeyFor(bytes))` (algorithm inferred from key size) |
| `.setSubject/.setIssuedAt/.setExpiration/.setClaims/.setIssuer/.setId` | `.subject/.issuedAt/.expiration/.claims/.issuer/.id` |
| `byte[]`/`String` secret | `javax.crypto.SecretKey` (`io.jsonwebtoken.security.Keys`) |

HS256 keys must be at least 256 bits (32 bytes): `Keys.hmacShaKeyFor` throws `WeakKeyException` otherwise.
Decode the configured secret the same way the old code did (Base64 vs raw `getBytes(UTF_8)`) so existing
tokens/tests keep working. `ExpiredJwtException`, `JwtException`, `Claims` keep their names.

## 4. javax → jakarta packages

Spring Boot 3 moved from Java EE to Jakarta EE. Every Java EE `javax.*` reference (imports, fully qualified
names, test classes, XML descriptors, property keys) must become `jakarta.*`; mixed namespaces fail at runtime,
so migrate everything together.

| Before (Java EE) | After (Jakarta EE) |
|---|---|
| `javax.persistence.*` | `jakarta.persistence.*` |
| `javax.validation.*` | `jakarta.validation.*` |
| `javax.servlet.*` | `jakarta.servlet.*` |
| `javax.annotation.*` (PostConstruct, PreDestroy, Resource, Priority, security.*) | `jakarta.annotation.*` |
| `javax.transaction.*` (not `javax.transaction.xa`) | `jakarta.transaction.*` |
| `javax.ws.rs.*` | `jakarta.ws.rs.*` |
| `javax.mail.*` | `jakarta.mail.*` |
| `javax.jms.*` | `jakarta.jms.*` |
| `javax.xml.bind.*` | `jakarta.xml.bind.*` |
| also `javax.websocket`, `javax.inject`, `javax.activation`, `javax.ejb`, `javax.faces`, `javax.el`, `javax.json` | `jakarta.*` |

Do NOT change JDK packages: `javax.sql.*`, `javax.crypto.*`, `javax.net.*`, `javax.naming.*`,
`javax.management.*`, `javax.security.auth.*`, `javax.xml.parsers/transform/xpath`, `javax.transaction.xa`,
`javax.annotation.processing`, and JSR-305 `javax.annotation.Nullable/Nonnull` (findbugs).

Affected annotations/classes, for spotting misses in compile errors:
- Persistence: `@Entity @Table @Column @Id @GeneratedValue @ManyToOne @OneToMany @ManyToMany @OneToOne
  @JoinColumn @JoinTable @PrePersist @PreUpdate @PostLoad @Enumerated @Temporal`, `EntityManager`,
  `EntityManagerFactory`, `EntityNotFoundException`.
- Validation: `@Valid @NotNull @NotBlank @NotEmpty @Size @Min @Max @Email @Pattern @Positive @Negative @Past @Future`.
- Servlet: `HttpServletRequest`, `HttpServletResponse`, `ServletException`, `Filter`, `FilterChain`, `HttpSession`, `Cookie`.

Every JPA `@Entity` class must import `jakarta.persistence` — check.sh fails otherwise.

```java
// BEFORE (will not compile on Boot 3)          // AFTER
import javax.persistence.Entity;                 import jakarta.persistence.Entity;
import javax.validation.constraints.NotBlank;    import jakarta.validation.constraints.NotBlank;
import javax.servlet.http.HttpServletRequest;    import jakarta.servlet.http.HttpServletRequest;
```

Also: `persistence.xml`/`orm.xml` namespaces → `https://jakarta.ee/xml/ns/persistence` version 3.0, and
property keys such as `spring.jpa.properties.javax.persistence.*` → `jakarta.persistence.*` (both handled
by migrate.sh).

## 5. Boot 3 property / config renames (migrate.sh handles the .properties forms)

- `spring.redis.*` → `spring.data.redis.*`; `server.max-http-header-size` → `server.max-http-request-header-size`.
  In YAML these are nested keys: move them by hand.
- `META-INF/spring.factories` `EnableAutoConfiguration` entries → `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`.
- Actuator endpoint paths changed: review security rules that expose actuator endpoints.
- `spring.jpa.database-platform=org.hibernate.dialect.H2Dialect` stays valid (Hibernate 6 usually auto-detects it).

## 6. Automated alternative: OpenRewrite

Useful for large codebases; needs network to download recipes. migrate.sh is the default here.

```xml
<plugin>
    <groupId>org.openrewrite.maven</groupId>
    <artifactId>rewrite-maven-plugin</artifactId>
    <version>5.42.0</version>
    <configuration>
        <activeRecipes>
            <recipe>org.openrewrite.java.spring.boot3.UpgradeSpringBoot_3_2</recipe>
            <!-- namespace only: org.openrewrite.java.migrate.jakarta.JavaxMigrationToJakarta
                 (artifact org.openrewrite.recipe:rewrite-migrate-java:2.26.0) -->
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

Run `mvn rewrite:run`; it updates the Boot version, migrates javax → jakarta, updates deprecated Spring
Security patterns and fixes property names. Remove the plugin afterwards and still run `scripts/check.sh`.

## 7. Manual verification greps (what check.sh automates)

```bash
grep -E "javax\.xml\.bind|jaxb-api" pom.xml                       # must be empty
grep "<version>0\.9\.1</version>" pom.xml                         # old jjwt, must be empty
grep -A2 "spring-boot-starter-parent" pom.xml | grep version      # 3.2.x
grep "java.version" pom.xml                                       # 17 or 21
grep -r "import javax\." --include="*.java" . | grep -v "javax.sql" | grep -v "javax.crypto" | grep -v "javax.net"   # must be empty
grep -r "import jakarta\.persistence" --include="*.java" .        # must list every entity
grep -r "import jakarta\.validation" --include="*.java" .
```

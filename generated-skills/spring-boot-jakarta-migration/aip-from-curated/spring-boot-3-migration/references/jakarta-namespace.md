# javax.* → jakarta.* (Jakarta EE 9+/10, Spring Boot 3)

Spring Boot 3 moved every Java EE API to Jakarta EE. All Java EE `javax.*` imports and fully
qualified names must become `jakarta.*`, together, in main **and test** sources. Mixed
namespaces cause runtime errors.

## Package mappings

| Before (Java EE) | After (Jakarta EE) |
|---|---|
| `javax.persistence.*` | `jakarta.persistence.*` |
| `javax.validation.*` | `jakarta.validation.*` |
| `javax.servlet.*` | `jakarta.servlet.*` |
| `javax.annotation.*` (PostConstruct, PreDestroy, Resource, Priority, security.*) | `jakarta.annotation.*` |
| `javax.transaction.*` | `jakarta.transaction.*` |
| `javax.ws.rs.*` | `jakarta.ws.rs.*` |
| `javax.mail.*` | `jakarta.mail.*` |
| `javax.jms.*` | `jakarta.jms.*` |
| `javax.xml.bind.*` | `jakarta.xml.bind.*` |

**Do not change JDK packages** — they are part of Java 17+ itself: `javax.sql.*`,
`javax.crypto.*`, `javax.net.*`, `javax.transaction.xa.*`, `javax.security.auth|cert|sasl`,
`javax.naming.*`, `javax.management.*`, `javax.xml.parsers|transform|xpath|stream|validation`,
`javax.annotation.processing.*`, `javax.swing`, `javax.imageio`, ... Third-party
`javax.annotation.Nonnull/Nullable` (JSR-305) also stays.

Other EE packages (`javax.inject`, `javax.websocket`, `javax.ejb`, `javax.enterprise`,
`javax.json`, `javax.xml.ws`, `javax.xml.soap`, `javax.activation`, `javax.el`, ...) need both
the import change and a swap of the Maven artifact to its Jakarta equivalent.

## Affected annotations and classes

- **Persistence (JPA):** `@Entity`, `@Table`, `@Column`, `@Id`, `@GeneratedValue`,
  `@ManyToOne`, `@OneToMany`, `@ManyToMany`, `@OneToOne`, `@JoinColumn`, `@JoinTable`,
  `@PrePersist`, `@PreUpdate`, `@PostLoad`, `@Enumerated`, `@Temporal`, `EntityManager`,
  `EntityManagerFactory`, `EntityNotFoundException`.
- **Validation:** `@Valid`, `@NotNull`, `@NotBlank`, `@NotEmpty`, `@Size`, `@Min`, `@Max`,
  `@Email`, `@Pattern`, `@Positive`, `@Negative`, `@Past`, `@Future`.
- **Servlet:** `HttpServletRequest`, `HttpServletResponse`, `ServletException`, `Filter`,
  `FilterChain`, `HttpSession`, `Cookie`.

```java
// BEFORE — will not compile on Spring Boot 3
import javax.persistence.Entity;
import javax.validation.constraints.NotBlank;
import javax.servlet.http.HttpServletRequest;
// AFTER — required
import jakarta.persistence.Entity;
import jakarta.validation.constraints.NotBlank;
import jakarta.servlet.http.HttpServletRequest;
```

**Every JPA entity class MUST import `jakarta.persistence`.** If `grep -r "import
jakarta\.persistence"` finds nothing but the project has entities, the migration is incomplete.

## Pitfalls

1. Don't change `javax.sql` or `javax.crypto` (JDK, not Java EE).
2. Check test files too.
3. Update XML configuration: `persistence.xml`/`orm.xml` to the Jakarta namespace
   (`https://jakarta.ee/xml/ns/persistence`, `version="3.0"`) and `javax.persistence.*`
   property names to `jakarta.persistence.*`.
4. Third-party libraries must have Jakarta-compatible versions.
5. Mixed namespaces cause runtime errors — migrate everything together.

## Manual commands (fallback when scripts cannot run; GNU sed in the container)

```bash
# find what needs migrating (excludes JDK packages)
grep -r "import javax\." --include="*.java" . | grep -v "javax.sql" | grep -v "javax.crypto" | grep -v "javax.net"

find . -name "*.java" -type f -exec sed -i 's/import javax\.persistence/import jakarta.persistence/g' {} +
find . -name "*.java" -type f -exec sed -i 's/import javax\.validation/import jakarta.validation/g' {} +
find . -name "*.java" -type f -exec sed -i 's/import javax\.servlet/import jakarta.servlet/g' {} +
find . -name "*.java" -type f -exec sed -i 's/import javax\.annotation\.PostConstruct/import jakarta.annotation.PostConstruct/g' {} +
find . -name "*.java" -type f -exec sed -i 's/import javax\.annotation\.PreDestroy/import jakarta.annotation.PreDestroy/g' {} +
find . -name "*.java" -type f -exec sed -i 's/import javax\.annotation\.Resource/import jakarta.annotation.Resource/g' {} +
find . -name "*.java" -type f -exec sed -i 's/import javax\.transaction/import jakarta.transaction/g' {} +
# wildcard imports
find . -name "*.java" -type f -exec sed -i 's/import javax\.persistence\.\*/import jakarta.persistence.*/g' {} +
find . -name "*.java" -type f -exec sed -i 's/import javax\.validation\.\*/import jakarta.validation.*/g' {} +
find . -name "*.java" -type f -exec sed -i 's/import javax\.servlet\.\*/import jakarta.servlet.*/g' {} +
```

## Verification

```bash
# must return NO results
grep -r "import javax\.persistence" --include="*.java" .
grep -r "import javax\.validation" --include="*.java" .
grep -r "import javax\.servlet" --include="*.java" .
grep -r "import javax\." --include="*.java" . | grep -E "(persistence|validation|servlet|transaction|annotation\.(PostConstruct|PreDestroy|Resource))"
# MUST return results when the project has entities / validation
grep -r "import jakarta\.persistence" --include="*.java" .
grep -r "import jakarta\.validation" --include="*.java" .
```

## OpenRewrite alternative

Only when the container can download plugins (network). Same result as the scripted rewrite:

```xml
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

then `mvn rewrite:run`. Remove the plugin afterwards.

# Jakarta EE namespace mappings

Load when classifying an inventoried `javax.*` import, when extending the
migration script to a package it doesn't yet cover, or when reviewing what an
annotation belongs to.

## Migration mappings (javax.* → jakarta.*)

| Before (Java EE)        | After (Jakarta EE)        | Migrated by `scripts/migrate_javax_to_jakarta.sh` |
|-------------------------|---------------------------|---------------------------------------------------|
| `javax.persistence.*`   | `jakarta.persistence.*`   | yes                                               |
| `javax.validation.*`    | `jakarta.validation.*`    | yes                                               |
| `javax.servlet.*`       | `jakarta.servlet.*`       | yes                                               |
| `javax.annotation.*`    | `jakarta.annotation.*`    | yes (covers `PostConstruct`, `PreDestroy`, `Resource`, and all other subpackages) |
| `javax.transaction.*`   | `jakarta.transaction.*`   | yes                                               |
| `javax.ws.rs.*`         | `jakarta.ws.rs.*`         | yes                                               |
| `javax.mail.*`          | `jakarta.mail.*`          | yes                                               |
| `javax.jms.*`           | `jakarta.jms.*`           | yes                                               |
| `javax.xml.bind.*`      | `jakarta.xml.bind.*`      | yes (JAXB only — other `javax.xml.*` subpackages stay)        |
| `javax.inject.*`        | `jakarta.inject.*`        | yes                                               |
| `javax.enterprise.*`    | `jakarta.enterprise.*`    | yes                                               |
| `javax.ejb.*`           | `jakarta.ejb.*`           | yes                                               |
| `javax.json.*`          | `jakarta.json.*`          | yes                                               |
| `javax.batch.*`         | `jakarta.batch.*`         | yes                                               |

## Stays on javax (JDK packages — do NOT migrate)

These belong to the Java SE platform, not Java EE. The inventory script skips
them and the migration script does not touch them.

- `javax.sql.*` (e.g., `DataSource`)
- `javax.crypto.*`
- `javax.net.*`
- `javax.security.*` (e.g., `javax.security.cert`)
- `javax.naming.*`
- `javax.management.*`
- `javax.xml.parsers.*`, `javax.xml.transform.*`, `javax.xml.stream.*`,
  `javax.xml.xpath.*`, `javax.xml.datatype.*`, `javax.xml.namespace.*`,
  `javax.xml.validation.*`, `javax.xml.catalog.*` (everything under
  `javax.xml.*` **except** `javax.xml.bind`)

## Affected annotations and classes (which group an annotation belongs to)

### Persistence (`jakarta.persistence`)

- `@Entity`, `@Table`, `@Column`
- `@Id`, `@GeneratedValue`, `GenerationType`
- `@ManyToOne`, `@OneToMany`, `@ManyToMany`, `@OneToOne`
- `@JoinColumn`, `@JoinTable`
- `@PrePersist`, `@PreUpdate`, `@PostLoad`
- `@Enumerated`, `@Temporal`
- `EntityManager`, `EntityManagerFactory`
- `EntityNotFoundException`

### Bean Validation (`jakarta.validation`)

- `@Valid`
- `@NotNull`, `@NotBlank`, `@NotEmpty`
- `@Size`, `@Min`, `@Max`
- `@Email`, `@Pattern`
- `@Positive`, `@Negative`
- `@Past`, `@Future`

### Servlet (`jakarta.servlet`)

- `HttpServletRequest`, `HttpServletResponse`
- `ServletException`
- `Filter`, `FilterChain`
- `HttpSession`, `Cookie`

### Common annotations (`jakarta.annotation`)

- `@PostConstruct`, `@PreDestroy`, `@Resource`

## Worked before/after examples

### Entity class — every JPA `@Entity` MUST be on jakarta.persistence in Spring Boot 3

```java
// BEFORE — Spring Boot 2.x; will not compile in Spring Boot 3
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

// AFTER — Spring Boot 3.x
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

### Validation

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

### Servlet

```java
// BEFORE
import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpServletResponse;

// AFTER
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
```

## Non-Java surfaces that the scripts do NOT cover

The scripts only rewrite `import` lines in `*.java` files. These surfaces still
need manual edits:

- `persistence.xml` — the `<persistence>` root element's `xmlns` must change
  from `http://xmlns.jcp.org/xml/ns/persistence` to
  `https://jakarta.ee/xml/ns/persistence`, and `version` to `3.0` or higher.
- `web.xml`, `beans.xml`, `faces-config.xml` — same xmlns family swap to the
  `https://jakarta.ee/xml/ns/...` URIs.
- Fully-qualified type references inside `.java` files (e.g.
  `javax.persistence.EntityManager em` written out as a fully-qualified type
  in a method signature instead of imported). Rare; fix manually with Edit.
- Spring `application.properties` / `application.yml` keys referencing
  `javax.persistence.*` JPA property names (e.g.,
  `javax.persistence.schema-generation.database.action`) need to become
  `jakarta.persistence.schema-generation.database.action`.

## OpenRewrite alternative

For an automated end-to-end migration including dependency manifests, add the
`rewrite-maven-plugin` to `pom.xml` and run `mvn rewrite:run`. Use this when the
scripted approach is too narrow (e.g., the project also needs Jakarta-version
dependency bumps the scripts don't perform):

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

```bash
mvn rewrite:run
```

OpenRewrite covers both `import` statements and XML/properties references — but
requires Maven, a plugin install, and network access to fetch the recipe
artifacts.

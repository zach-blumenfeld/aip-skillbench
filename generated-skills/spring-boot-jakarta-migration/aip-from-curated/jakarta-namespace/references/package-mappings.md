# Jakarta EE Package Mappings Reference

Load this when you need the full lookup table — which `javax.*` packages move to `jakarta.*`, which stay, and which annotations/classes belong to each package.

## Migrated packages (Java EE → Jakarta EE)

| Before (Java EE)       | After (Jakarta EE)       |
|------------------------|--------------------------|
| `javax.persistence.*`  | `jakarta.persistence.*`  |
| `javax.validation.*`   | `jakarta.validation.*`   |
| `javax.servlet.*`      | `jakarta.servlet.*`      |
| `javax.annotation.*`   | `jakarta.annotation.*`   |
| `javax.transaction.*`  | `jakarta.transaction.*`  |
| `javax.ws.rs.*`        | `jakarta.ws.rs.*`        |
| `javax.mail.*`         | `jakarta.mail.*`         |
| `javax.jms.*`          | `jakarta.jms.*`          |
| `javax.xml.bind.*`     | `jakarta.xml.bind.*`     |

## DO NOT migrate (JDK packages, not Java EE)

These remain on `javax.*` because they ship with the JDK itself:

- `javax.sql.*`
- `javax.crypto.*`
- `javax.net.*` (e.g. `javax.net.ssl.*`)

## Affected annotations and classes by package

### `jakarta.persistence` (JPA)
- `@Entity`, `@Table`, `@Column`
- `@Id`, `@GeneratedValue`
- `@ManyToOne`, `@OneToMany`, `@ManyToMany`, `@OneToOne`
- `@JoinColumn`, `@JoinTable`
- `@PrePersist`, `@PreUpdate`, `@PostLoad`
- `@Enumerated`, `@Temporal`
- `EntityManager`, `EntityManagerFactory`
- `EntityNotFoundException`

### `jakarta.validation`
- `@Valid`
- `@NotNull`, `@NotBlank`, `@NotEmpty`
- `@Size`, `@Min`, `@Max`
- `@Email`, `@Pattern`
- `@Positive`, `@Negative`
- `@Past`, `@Future`

### `jakarta.servlet`
- `HttpServletRequest`, `HttpServletResponse`
- `ServletException`
- `Filter`, `FilterChain`
- `HttpSession`, `Cookie`

### `jakarta.annotation` (commonly used in Spring code)
- `@PostConstruct`
- `@PreDestroy`
- `@Resource`

## Worked examples

### Entity (JPA) — required for Spring Boot 3 to compile

```java
// BEFORE (Spring Boot 2.x) — will NOT compile in Spring Boot 3
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

// AFTER (Spring Boot 3.x) — REQUIRED
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

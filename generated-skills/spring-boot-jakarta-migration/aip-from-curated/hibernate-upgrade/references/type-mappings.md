# Type Mapping Migrations Reference

Load this when rewriting `@Type` / `@TypeDef` annotations or when reviewing entity field types after a Hibernate 6 upgrade.

## `@TypeDef` + `@Type(type = "...")` → `@JdbcTypeCode`

`@TypeDef` is removed. The string-form `@Type(type = "name")` is also removed. The replacement depends on what the original custom type encoded.

### JSON columns

```java
// BEFORE (Hibernate 5 with custom type registration)
@TypeDef(name = "json", typeClass = JsonType.class)
public class User { ... }

@Type(type = "json")
private JsonNode metadata;

// AFTER (Hibernate 6) — built-in JSON support, no third-party type
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

@JdbcTypeCode(SqlTypes.JSON)
private JsonNode metadata;
```

`SqlTypes.JSON` is the canonical choice; the underlying database column type is database-specific but inferred.

### Arbitrary custom types

When the custom type isn't JSON, use the class-form `@Type`:

```java
// BEFORE
@TypeDef(name = "encrypted", typeClass = EncryptedStringType.class)
@Type(type = "encrypted")
private String ssn;

// AFTER
@Type(EncryptedStringType.class)
private String ssn;
```

The custom type class itself may need updates — `org.hibernate.usertype.UserType` interface methods changed in Hibernate 6. Consult the migration guide for the type's library.

## Enums — make storage explicit

Hibernate 6 still defaults to ordinal storage for enums, which is fragile. Always be explicit:

```java
@Enumerated(EnumType.STRING)
@Column(nullable = false)
private Role role;
```

This is not a Hibernate 6 *requirement*, but it is the right time to fix any implicit `@Enumerated` usage.

## Date / Time — prefer `java.time`

```java
@Column(name = "created_at")
private LocalDateTime createdAt;   // preferred over java.util.Date
```

Hibernate 6's default timezone handling (see `references/configuration.md`) only works correctly with `java.time` types.

## ID Generation — prefer standard JPA

Hibernate 6 changed default generation behavior for `GenerationType.AUTO`. Pin to a specific strategy to avoid surprises:

```java
// IDENTITY — most database-portable choice
@Id
@GeneratedValue(strategy = GenerationType.IDENTITY)
private Long id;

// SEQUENCE — preferred for Postgres/Oracle when you control the sequence
@Id
@GeneratedValue(strategy = GenerationType.SEQUENCE, generator = "user_seq")
@SequenceGenerator(name = "user_seq", sequenceName = "user_sequence", allocationSize = 1)
private Long id;
```

Avoid `@GenericGenerator` with string strategy names — those Hibernate-specific generators are deprecated and may behave differently under Hibernate 6.

## Fetch Strategies — be explicit

Default fetch behavior is broadly similar, but explicit annotations make the intent clear and immune to default changes:

```java
@ManyToOne(fetch = FetchType.LAZY)
@JoinColumn(name = "department_id")
private Department department;

@OneToMany(mappedBy = "user", fetch = FetchType.LAZY)
private List<Order> orders;
```

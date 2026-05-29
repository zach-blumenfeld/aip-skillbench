# Hibernate 5 → 6 migration reference

Load when an `apply_mechanical_fixes` rewrite is insufficient and the agent
needs the concrete before/after for a class of change.

## Legacy Criteria API → JPA Criteria

Hibernate 6 removed `org.hibernate.Criteria`. Every use must move to the JPA
`CriteriaBuilder` API. The mechanical rewrite cannot do this; the call shape
changes.

```java
// BEFORE — Hibernate 5 legacy Criteria
Criteria criteria = session.createCriteria(User.class);
criteria.add(Restrictions.eq("active", true));
List<User> users = criteria.list();

// AFTER — JPA Criteria
CriteriaBuilder cb = entityManager.getCriteriaBuilder();
CriteriaQuery<User> cq = cb.createQuery(User.class);
Root<User> root = cq.from(User.class);
cq.where(cb.equal(root.get("active"), true));
List<User> users = entityManager.createQuery(cq).getResultList();
```

Restrictions translation cheat-sheet:

| Hibernate 5 `Restrictions.*` | JPA Criteria equivalent           |
|------------------------------|-----------------------------------|
| `eq(p, v)`                   | `cb.equal(root.get(p), v)`        |
| `ne(p, v)`                   | `cb.notEqual(root.get(p), v)`     |
| `gt(p, v)` / `lt(p, v)`      | `cb.greaterThan` / `cb.lessThan`  |
| `like(p, v)`                 | `cb.like(root.get(p), v)`         |
| `isNull(p)`                  | `cb.isNull(root.get(p))`          |
| `and(a, b)` / `or(a, b)`     | `cb.and(...)` / `cb.or(...)`      |
| `in(p, [...])`               | `root.get(p).in(...)`             |

If the session is reached via `entityManager.unwrap(Session.class)`, prefer
holding the `EntityManager` directly going forward.

## Custom type mappings

Hibernate 6 deprecated `@TypeDef` and `@Type(type = "...")` in favour of
`@JdbcTypeCode` (built-in JDBC type codes) or `@Type(value = ...)` taking a
class reference.

### JSON columns

```java
// BEFORE
@TypeDef(name = "json", typeClass = JsonType.class)
@Type(type = "json")
private JsonNode metadata;

// AFTER (no third-party type needed for JSON)
@JdbcTypeCode(SqlTypes.JSON)
private JsonNode metadata;
```

### Other custom types

If the type was backed by a class implementing `UserType`, switch the annotation
from `@Type(type = "fqcn")` to `@Type(MyCustomType.class)` and drop the matching
`@TypeDef` registration. If the type is now covered by a built-in JDBC type
(JSON, XML, UUID, etc.), prefer `@JdbcTypeCode(SqlTypes.<X>)`.

## JPQL / HQL audit

Hibernate 6 tightened the HQL parser. Inspect every `@Query` annotation
(JPQL/HQL only — native queries follow different rules) for:

1. **Bulk updates** — must not include the optional `from` keyword. The
   `apply_mechanical_fixes` script handles the common case, but custom DSLs
   that build strings at runtime may bypass it. Grep for `update from` after
   running the script.
2. **`select distinct ... join fetch`** — Hibernate 6 de-duplicates root
   entities from join-fetched collections automatically. `distinct` is now
   redundant and triggers a SQL `DISTINCT` you probably don't want.
3. **Implicit joins** — be explicit with `JOIN` and entity aliases.
4. **Treat / type narrowing** — `type(e) = MyEntity` syntax is now strict.

Run the build after each query edit; the H6 parser surfaces errors at startup.

## Dialect configuration

Hibernate 6 auto-detects dialect from the JDBC URL in most cases. Remove the
explicit `spring.jpa.database-platform` (or
`spring.jpa.properties.hibernate.dialect`) unless you need a non-default
behaviour (e.g. forcing PostgreSQL function quoting on a CockroachDB URL).

If you keep it, double-check the dialect class still exists — several `*95`,
`*10`, etc. version-suffixed dialects were removed in favour of unversioned
classes that detect the server version at runtime.

## ID generation

Hibernate 6 honours JPA's strategy contract more strictly. The two safe choices:

```java
// IDENTITY — leaves identity allocation to the database column.
@Id
@GeneratedValue(strategy = GenerationType.IDENTITY)
private Long id;

// SEQUENCE — explicit generator. Required on Oracle/Postgres if you want
// portable batch-friendly inserts.
@Id
@GeneratedValue(strategy = GenerationType.SEQUENCE, generator = "user_seq")
@SequenceGenerator(name = "user_seq", sequenceName = "user_sequence", allocationSize = 1)
private Long id;
```

Avoid `GenerationType.AUTO` on cross-database codebases — H6 now resolves it
differently per dialect.

## Type-mapping defaults to nail down

- **Enums** — annotate with `@Enumerated(EnumType.STRING)` everywhere.
  The H6 default `ORDINAL` mapping is fragile across schema changes.
- **Dates/times** — use `java.time.LocalDateTime` / `LocalDate` /
  `OffsetDateTime`; avoid `java.util.Date` and `java.sql.Timestamp`.
- **Timezones** — add
  `spring.jpa.properties.hibernate.timezone.default_storage=NORMALIZE` to make
  `OffsetDateTime` round-trip consistently. (The observability patch script
  adds this for you.)

## Troubleshooting common errors

| Error message                                      | Likely cause                                                  | Where to look |
|----------------------------------------------------|---------------------------------------------------------------|---------------|
| `Unknown entity: <FQCN>`                           | Package rename broke entity scanning, or `@Entity` missing.   | Check `@EntityScan` / `javax.persistence` leftovers. |
| `Could not determine recommended JdbcType for ...` | Removed `@Type`/`@TypeDef` with no replacement.               | Replace with `@JdbcTypeCode` or `@Type(Class)`.       |
| `org.hibernate.query.SyntaxException`              | Stricter JPQL parser rejected old syntax.                     | Look for `update from`, implicit joins, missing aliases. |
| `org.hibernate.MappingException: Could not instantiate id generator` | Custom legacy ID generator removed.        | Switch to standard `GenerationType.SEQUENCE`/`IDENTITY`. |
| `Dialect class not found`                          | Removed versioned dialect class.                              | Drop the explicit dialect or use the unversioned class. |

## N+1 monitoring

Hibernate 6 sometimes plans differently for lazy collections; queries that were
single-statement in H5 may fan out. After turning on the observability props
(see the patch script), exercise the hot paths and watch
`org.hibernate.stat` output for `EntityFetchCount` exceeding `EntityLoadCount`
on the same entity — that's the N+1 signature.

Mitigations, in order of preference:

1. Add a targeted `@EntityGraph` to the repository method.
2. Switch the affected `@OneToMany` / `@ManyToOne` to use a `JOIN FETCH` query.
3. Configure `@BatchSize` on the collection or entity.

## Sources

- [Hibernate 6.0 Migration Guide](https://docs.jboss.org/hibernate/orm/6.0/migration-guide/migration-guide.html)
- [Thorben Janssen — Migrating to Hibernate 6](https://thorben-janssen.com/migrating-to-hibernate-6/)
- [Quarkus Migration Guide 3.0 — Hibernate ORM 5 → 6](https://github.com/quarkusio/quarkus/wiki/Migration-Guide-3.0:-Hibernate-ORM-5-to-6-migration)

# Hibernate 5 → 6 (Boot 3 ships Hibernate 6.x)

Load this when `scripts/check.sh` reports `[hibernate]` findings, or a build/test failure is triaged as
`hibernate` (query parse errors, "Unknown entity", "Could not determine type", schema/ID problems).

## Mechanical (done by scripts/migrate.sh)

- `javax.persistence.*` → `jakarta.persistence.*`; `org.hibernate.annotations.*` keeps its package.
- HQL `update from User u set ...` → `update User u set ...` (Hibernate 6 rejects the optional `from`).
- Versioned dialect classes → unversioned (`MySQL8Dialect` → `MySQLDialect`, `PostgreSQL10Dialect` →
  `PostgreSQLDialect`, …). `org.hibernate.dialect.H2Dialect`, `PostgreSQLDialect`, `MySQLDialect` are valid.
  Hibernate 6 auto-detects the dialect from the JDBC URL, so `spring.jpa.database-platform` can usually be
  removed; keeping a valid one is harmless (only a startup warning).

## Code changes (client task)

| Hibernate 5 | Hibernate 6 |
|---|---|
| `@TypeDef(name = "json", typeClass = JsonType.class)` + `@Type(type = "json") private JsonNode metadata;` | `@JdbcTypeCode(SqlTypes.JSON) private JsonNode metadata;` (`@TypeDef` removed; custom types via `@Type(MyType.class)`) |
| `@Type(type = "...")` | `@JdbcTypeCode(SqlTypes.X)` or `@Type(CustomUserType.class)` |
| `session.createCriteria(User.class)` + `Restrictions.eq("active", true)` + `criteria.list()` | JPA Criteria (below) — the legacy `org.hibernate.Criteria` API is gone |
| legacy/custom ID generators | standard JPA `@GeneratedValue` |
| `select distinct u from User u join fetch u.roles` | `select u from User u join fetch u.roles` (duplicates are filtered automatically; distinct is optional) |

```java
CriteriaBuilder cb = entityManager.getCriteriaBuilder();
CriteriaQuery<User> cq = cb.createQuery(User.class);
Root<User> root = cq.from(User.class);
cq.where(cb.equal(root.get("active"), true));
List<User> users = entityManager.createQuery(cq).getResultList();
```

## IDs, types, fetching

- ID generation defaults changed: `GenerationType.AUTO` now means a sequence. For auto-increment schemas use
  `@GeneratedValue(strategy = GenerationType.IDENTITY)`; for sequences be explicit:
  `@GeneratedValue(strategy = GenerationType.SEQUENCE, generator = "user_seq")` +
  `@SequenceGenerator(name = "user_seq", sequenceName = "user_sequence", allocationSize = 1)`.
- Enums: be explicit — `@Enumerated(EnumType.STRING) @Column(nullable = false) private Role role;`
- Dates: prefer `java.time` (`LocalDateTime createdAt`) over `java.util.Date`.
- Fetching: defaults are similar but be explicit — `@ManyToOne(fetch = FetchType.LAZY) @JoinColumn(...)`,
  `@OneToMany(mappedBy = "user", fetch = FetchType.LAZY)`.

## Queries

- JPQL/HQL validation is stricter: always alias entities (`SELECT u FROM User u WHERE u.active = true`),
  prefer explicit joins (`SELECT u FROM User u JOIN u.roles r WHERE r.name = :roleName`).
- Native queries work the same but check projections and literals: `WHERE active = 1` → `WHERE active = true`
  where the column is boolean.
- Some queries that parsed in Hibernate 5 fail in 6 — the error is reported at startup when Spring Data
  validates `@Query` methods, so a context-load test catches it.

## Properties

```properties
spring.jpa.hibernate.ddl-auto=create-drop      # unchanged
spring.jpa.show-sql=true                       # unchanged
spring.jpa.properties.hibernate.format_sql=true        # review
spring.jpa.properties.hibernate.use_sql_comments=true  # review
spring.jpa.properties.hibernate.timezone.default_storage=NORMALIZE   # new in Hibernate 6
```

## Troubleshooting

- "Unknown entity" → entity scanning/package; also check the class imports `jakarta.persistence.Entity`.
- "Could not determine type" → type mappings/annotations (`@Type`, enum, JSON).
- "Query syntax error" / `SemanticException` → stricter HQL (aliases, `update from`, implicit joins).
- H2 2.x reserved words: an entity mapped to table `user`/`order`/`value` fails DDL; the mapping
  must name a non-reserved table (`@Table(name = "users")`) or set
  `spring.jpa.properties.hibernate.globally_quoted_identifiers=true`.
- Hibernate 6 is stricter about entity mappings and may generate different SQL (N+1 behavior can change):
  when performance matters, monitor with

```properties
spring.jpa.properties.hibernate.generate_statistics=true
logging.level.org.hibernate.stat=debug
logging.level.org.hibernate.SQL=debug
spring.jpa.properties.hibernate.session.events.log.LOG_QUERIES_SLOWER_THAN_MS=100   # 6.2+
```

## Manual greps (check.sh automates these)

```bash
grep -r "session.createCriteria\|org.hibernate.Criteria" --include="*.java" .
grep -r "@Type(type\s*=" --include="*.java" .
grep -r "@TypeDef" --include="*.java" .
grep -r "update from" --include="*.java" .
```

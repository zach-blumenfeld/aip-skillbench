# Hibernate 5 → 6 (Spring Boot 3)

Spring Boot 3 ships Hibernate 6 on Jakarta Persistence (`jakarta.persistence.*`;
`org.hibernate.annotations.*` keeps its package).

## Critical breaking changes

1. **Stricter HQL/JPQL parsing** — drop the optional `from` in bulk updates:
   ```java
   @Query("update from User u set u.active = false where u.id = :id")   // H5 only
   @Query("update User u set u.active = false where u.id = :id")        // H6
   ```
   Be explicit about entity aliases (`SELECT u FROM User u WHERE u.active = true`) and use
   explicit joins (`SELECT u FROM User u JOIN u.roles r WHERE r.name = :roleName`) instead of
   implicit ones.
2. **DISTINCT is no longer needed with join fetch** — duplicates are filtered automatically:
   `select distinct u from User u join fetch u.roles` → `select u from User u join fetch u.roles`.
3. **Legacy Criteria API removed** (`org.hibernate.Criteria`, `session.createCriteria`,
   `Restrictions`). Use JPA Criteria:
   ```java
   // Before
   Criteria criteria = session.createCriteria(User.class);
   criteria.add(Restrictions.eq("active", true));
   List<User> users = criteria.list();
   // After
   CriteriaBuilder cb = entityManager.getCriteriaBuilder();
   CriteriaQuery<User> cq = cb.createQuery(User.class);
   Root<User> root = cq.from(User.class);
   cq.where(cb.equal(root.get("active"), true));
   List<User> users = entityManager.createQuery(cq).getResultList();
   ```
4. **`@Type(type = "...")` and `@TypeDef` removed** — use `@JdbcTypeCode` or `@Type(MyType.class)`:
   ```java
   // Before
   @TypeDef(name = "json", typeClass = JsonType.class)
   @Type(type = "json")
   private JsonNode metadata;
   // After
   @JdbcTypeCode(SqlTypes.JSON)
   private JsonNode metadata;
   ```
   Legacy ID generators are removed too — use standard JPA generation.
5. **N+1 behaviour may change** — Hibernate 6 can generate different SQL for lazy collections.
   Monitor:
   ```properties
   spring.jpa.properties.hibernate.generate_statistics=true
   logging.level.org.hibernate.stat=debug
   logging.level.org.hibernate.SQL=debug
   ```

## ID generation

The default (`AUTO`) strategy changed. Prefer explicit strategies:

```java
@Id
@GeneratedValue(strategy = GenerationType.IDENTITY)
private Long id;

// or sequences (preferred for some databases)
@Id
@GeneratedValue(strategy = GenerationType.SEQUENCE, generator = "user_seq")
@SequenceGenerator(name = "user_seq", sequenceName = "user_sequence", allocationSize = 1)
private Long id;
```

## Dialect

Hibernate 6 auto-detects the dialect from the JDBC URL; `spring.jpa.database-platform` can
usually be removed (only specify for specific behaviour). `org.hibernate.dialect.H2Dialect`,
`PostgreSQLDialect`, `MySQLDialect` keep their names; versioned ones (`MySQL57Dialect`,
`PostgreSQL95Dialect`, ...) are gone — use the unversioned class. Leaving
`org.hibernate.dialect.H2Dialect` in place is harmless (a deprecation warning at most).

## Native queries

Work the same, but be careful with projections; use real booleans where the column is boolean:
`SELECT * FROM users WHERE active = true` (not `= 1`).

## Type mappings and fetching

```java
@Enumerated(EnumType.STRING)          // explicit enum mapping
@Column(nullable = false)
private Role role;

@Column(name = "created_at")
private LocalDateTime createdAt;      // prefer java.time over java.util.Date (+ @Temporal)

@ManyToOne(fetch = FetchType.LAZY)    // be explicit about fetch types
@JoinColumn(name = "department_id")
private Department department;

@OneToMany(mappedBy = "user", fetch = FetchType.LAZY)
private List<Order> orders;
```

## Configuration properties

```properties
# unchanged
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.show-sql=true
# review
spring.jpa.properties.hibernate.format_sql=true
spring.jpa.properties.hibernate.use_sql_comments=true
# new in Hibernate 6
spring.jpa.properties.hibernate.timezone.default_storage=NORMALIZE
# slow-query log (Hibernate 6.2+)
spring.jpa.properties.hibernate.session.events.log.LOG_QUERIES_SLOWER_THAN_MS=100
```

`javax.persistence.*` property keys become `jakarta.persistence.*`.

## Testing considerations and troubleshooting

- Entity validation is stricter; some queries that worked in H5 fail to parse in H6; execution
  plans may differ — run the test suite and watch performance.
- **"Unknown entity"** → check entity scanning / that entities import `jakarta.persistence`.
- **"Could not determine type"** → check type mappings and annotations (`@Type`, `@JdbcTypeCode`).
- **"Query syntax error"** → review JPQL against the stricter H6 rules above.

## Manual commands (fallback; GNU sed)

```bash
grep -r "session.createCriteria\|org.hibernate.Criteria" --include="*.java" .
grep -r "@Type(type\s*=" --include="*.java" .
grep -r "@TypeDef" --include="*.java" .
grep -r "update from" --include="*.java" .
find . -name "*.java" -type f -exec sed -i 's/update from /update /g' {} +
```

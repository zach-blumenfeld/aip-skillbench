# Hibernate 5 → 6 Breaking Changes Reference

Load this when you need the full set of breaking changes, the rewrite patterns for each, and worked before/after examples. The skill body sketches when each applies; this file carries the detail.

## 1. HQL/JPQL Parsing Is Stricter

Hibernate 6 swapped in a standards-compliant ANTLR-based parser. Queries that "happened to work" in Hibernate 5 are rejected.

### 1a. Drop the optional `from` in update queries

```java
// BEFORE (Hibernate 5) — non-standard leniency
@Query("update from User u set u.active = false where u.id = :id")

// AFTER (Hibernate 6)
@Query("update User u set u.active = false where u.id = :id")
```

This is mechanical and safe; `scripts/fix_update_from.sh` performs the rewrite.

### 1b. Be explicit about entity aliases

```java
@Query("SELECT u FROM User u WHERE u.active = true")
List<User> findActiveUsers();
```

### 1c. Prefer explicit joins over implicit ones

```java
// AFTER (Hibernate 6) — explicit join
@Query("SELECT u FROM User u JOIN u.roles r WHERE r.name = :roleName")
List<User> findByRoleName(@Param("roleName") String roleName);
```

Implicit-path joins still parse but are less predictable under the new parser.

## 2. `distinct` Is No Longer Needed for Collection Fetches

Hibernate 6 deduplicates parent rows automatically when a `join fetch` would have produced cartesian duplicates. Leaving `distinct` in is harmless but obscures intent.

```java
// BEFORE (Hibernate 5)
@Query("select distinct u from User u join fetch u.roles")

// AFTER (Hibernate 6) — distinct removed
@Query("select u from User u join fetch u.roles")
```

If you previously relied on `distinct` to suppress duplicates from `join fetch`, drop it. If `distinct` was meaningful (genuine unique-result semantics, not duplicate suppression), leave it.

## 3. Legacy `org.hibernate.Criteria` API Is Removed

The deprecated Hibernate-specific Criteria API is gone. All code must use the JPA Criteria API.

```java
// BEFORE (Hibernate 5 — legacy Criteria)
Criteria criteria = session.createCriteria(User.class);
criteria.add(Restrictions.eq("active", true));
List<User> users = criteria.list();

// AFTER (Hibernate 6 — JPA Criteria)
CriteriaBuilder cb = entityManager.getCriteriaBuilder();
CriteriaQuery<User> cq = cb.createQuery(User.class);
Root<User> root = cq.from(User.class);
cq.where(cb.equal(root.get("active"), true));
List<User> users = entityManager.createQuery(cq).getResultList();
```

This is a **structural** rewrite, not a mechanical one — each call site must be revisited. The discovery script lists every hit; rewrite by hand.

Mapping cheatsheet:

| Hibernate 5 (legacy)                             | Hibernate 6 (JPA Criteria)                                  |
|--------------------------------------------------|-------------------------------------------------------------|
| `session.createCriteria(User.class)`             | `cb.createQuery(User.class)` + `cq.from(User.class)`        |
| `Restrictions.eq("field", value)`                | `cb.equal(root.get("field"), value)`                        |
| `Restrictions.like("field", pattern)`            | `cb.like(root.get("field"), pattern)`                       |
| `Restrictions.gt/lt/ge/le("field", value)`       | `cb.greaterThan/lessThan/greaterThanOrEqualTo/...`          |
| `Restrictions.in("field", values)`               | `root.get("field").in(values)`                              |
| `Restrictions.and(a, b)` / `Restrictions.or(...)`| `cb.and(a, b)` / `cb.or(...)`                                |
| `criteria.list()`                                | `entityManager.createQuery(cq).getResultList()`             |

## 4. N+1 Query Behavior May Differ

Hibernate 6 changed how lazy-loaded collections are batched. Some N+1 patterns surface differently or in different places than under Hibernate 5. Enable statistics during the migration window and watch for regressions:

```properties
spring.jpa.properties.hibernate.generate_statistics=true
logging.level.org.hibernate.stat=debug
logging.level.org.hibernate.SQL=debug
```

Where a regression appears, the standard remedies still apply:

- `@EntityGraph` on the repository method to force eager loading for that path.
- `join fetch` in the JPQL.
- `@BatchSize(size = N)` on the collection.

## 5. Removed Hibernate-Specific Annotations

| Removed (Hibernate 5)                | Use Instead (Hibernate 6)                              |
|--------------------------------------|--------------------------------------------------------|
| `@TypeDef(name = "...", typeClass = ...)` | Direct `@Type(value = MyType.class)` or `@JdbcTypeCode(SqlTypes.X)` |
| `@Type(type = "...")` (string form)  | `@Type(value = Class.class)` or `@JdbcTypeCode(...)`   |
| Legacy `@GenericGenerator` strategies| Standard JPA `@GeneratedValue` strategies              |

See `references/type-mappings.md` for the type-annotation migration in detail.

# Configuration & Monitoring Reference

Load this when reviewing `application.properties` / `application.yml` during a Hibernate 5 → 6 upgrade, or when enabling monitoring to catch query/perf regressions.

## Dialect Configuration

Hibernate 6 auto-detects the dialect from the JDBC URL in most cases. In a Spring Boot 3 project, you can usually delete:

```properties
# Often unnecessary in Hibernate 6 — let it auto-detect
spring.jpa.database-platform=org.hibernate.dialect.H2Dialect
```

Specify only when you need to pin a specific dialect (e.g., a non-standard database, a vendor variant). Common dialect classes that remain valid:

```properties
spring.jpa.database-platform=org.hibernate.dialect.H2Dialect
spring.jpa.database-platform=org.hibernate.dialect.PostgreSQLDialect
spring.jpa.database-platform=org.hibernate.dialect.MySQLDialect
```

Some Hibernate-5-era dialect classes (versioned variants like `MySQL57Dialect`, `PostgreSQL95Dialect`) were removed or renamed. If the build fails with `ClassNotFoundException` on a dialect class, drop the override and let auto-detection take over, or pick the unversioned class above.

## Properties That Stay the Same

```properties
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.show-sql=true
spring.jpa.properties.hibernate.format_sql=true
spring.jpa.properties.hibernate.use_sql_comments=true
```

## New in Hibernate 6 — Timezone Handling

Hibernate 6 introduced explicit timezone-storage semantics. The default `NORMALIZE` is usually what you want when storing `OffsetDateTime` / `ZonedDateTime`:

```properties
spring.jpa.properties.hibernate.timezone.default_storage=NORMALIZE
```

Other values: `NATIVE` (database-native timezone column), `COLUMN` (companion column for offset), `NORMALIZE_UTC` (store as UTC).

## Monitoring During Migration

Turn on statistics and SQL logging during the upgrade window so query regressions and N+1 changes are visible:

```properties
spring.jpa.properties.hibernate.generate_statistics=true
logging.level.org.hibernate.stat=debug
logging.level.org.hibernate.SQL=debug
```

For Hibernate 6.2+, also enable the slow-query log:

```properties
spring.jpa.properties.hibernate.session.events.log.LOG_QUERIES_SLOWER_THAN_MS=100
```

Turn the statistics and debug logging off for production after the migration has stabilized — they have meaningful overhead.

## Common Errors and What They Mean

| Error                              | Likely cause                                                              |
|------------------------------------|---------------------------------------------------------------------------|
| `Unknown entity: <name>`           | Entity scanning not configured, or the entity is still on `javax.persistence`. |
| `Could not determine type`         | `@Type(type="...")` string form or missing `@JdbcTypeCode` on a complex column. |
| `Query syntax error` near `update` | `update from <Entity>` — drop the `from`. See breaking-changes.md §1a.    |
| `Query syntax error` other         | Hibernate 6's stricter parser; check explicit aliases and joins.          |
| `NoClassDefFoundError` on dialect  | A removed/renamed dialect class — delete the override or use the unversioned name. |

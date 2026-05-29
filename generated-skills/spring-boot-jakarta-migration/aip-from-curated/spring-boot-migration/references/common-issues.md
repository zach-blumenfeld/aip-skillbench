# Common issues during Spring Boot 2 → 3 migration

## Issue 1: Compilation errors after the parent-version bump

After changing the Spring Boot version, you will see many compilation errors
related to `javax.*` imports. These must be changed to `jakarta.*`. The
companion **Jakarta Namespace** skill handles this rename across the whole
source tree. OpenRewrite's `UpgradeSpringBoot_3_2` recipe also rewrites these
imports automatically.

## Issue 2: H2 database dialect

The dialect class name changed between Hibernate 5 and Hibernate 6:

```properties
# Before
spring.jpa.database-platform=org.hibernate.dialect.H2Dialect

# After
spring.jpa.database-platform=org.hibernate.dialect.H2Dialect
# Note: In Hibernate 6, this is often auto-detected and may not need explicit configuration.
```

If the property is set explicitly, prefer removing it and letting Hibernate 6
auto-detect.

## Issue 3: Actuator endpoints

Actuator endpoint paths have changed. Review your security configuration if
you expose actuator endpoints — patterns matched by Spring Security rules may
no longer match the new paths.

## Recommended migration order

1. **First** — upgrade to Spring Boot 2.7.x (latest 2.x) if not already.
2. **Second** — update Java version to 17 or 21.
3. **Third** — remove incompatible dependencies (JAXB, monolithic jjwt).
4. **Fourth** — update Spring Boot parent to 3.2.x.
5. **Fifth** — fix namespace imports (`javax.*` → `jakarta.*`).
6. **Sixth** — update Spring Security configuration.
7. **Seventh** — update HTTP clients (RestTemplate → RestClient).
8. **Finally** — run the full test suite.

## Migration checklist

- [ ] Update `spring-boot-starter-parent` version to 3.2.x.
- [ ] Update `java.version` to 17 or 21.
- [ ] Remove `javax.xml.bind:jaxb-api` and related JAXB dependencies.
- [ ] Remove old `io.jsonwebtoken:jjwt` if present; replace with modular jjwt.
- [ ] Run `mvn clean compile` to identify remaining issues.
- [ ] Fix all `javax.*` → `jakarta.*` imports.
- [ ] Update Spring Security configuration (see Spring Security 6 skill).
- [ ] Replace RestTemplate with RestClient (see RestClient Migration skill).
- [ ] Run tests to verify functionality.

## Sources

- [Spring Boot 3.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.0-Migration-Guide)
- [OpenRewrite Spring Boot 3 Migration](https://docs.openrewrite.org/running-recipes/popular-recipe-guides/migrate-to-spring-3)
- [Baeldung — Migrate to Spring Boot 3](https://www.baeldung.com/spring-boot-3-migration)

Fix the APIs in the project at `{workspace}` that were removed or changed in Hibernate 6, Spring 6/Boot 3 or jjwt 0.12. The helper script has finished the mechanical rewrites. These findings remain:

{legacy_api_findings}

pom.xml review items:

{pom_review}

Work through each finding:

- **Hibernate 6:**
  - Replace legacy `org.hibernate.Criteria`/`Restrictions` with the JPA Criteria API (`CriteriaBuilder`, `CriteriaQuery`, `Root`).
  - Replace `@TypeDef` and `@Type(type = "...")` with `@JdbcTypeCode(SqlTypes.X)` or `@Type(MyType.class)`.
  - Replace `createSQLQuery` with `createNativeQuery`.
  - Replace basic-type singletons with `StandardBasicTypes`.
  - Replace `@GenericGenerator` uuid strategies with `@UuidGenerator`.
  - Remove the optional `from` in HQL `update from X`.
  - ID generation: `@GeneratedValue` with no strategy, or `GenerationType.AUTO`, now uses a per-entity `<entity>_seq` sequence (allocationSize 50) instead of `hibernate_sequence`. Use `GenerationType.IDENTITY` or an explicit `@SequenceGenerator` (`allocationSize = 1`) that matches the existing schema.
  - JPQL is parsed more strictly. Use explicit entity aliases and explicit `JOIN` instead of implicit joins. Native queries should compare booleans to `true`, not `1`. `distinct` in fetch-join queries is no longer needed, but is harmless.
  - Keep enum mappings explicit (`@Enumerated(EnumType.STRING)`) and prefer `java.time` types.
  - Load `references/hibernate-6.md`.
- **jjwt 0.12:** move parser and builder calls to the 0.12 API (`Jwts.parser().verifyWith(key).build().parseSignedClaims(token).getPayload()`, `Keys.hmacShaKeyFor`, `Decoders.BASE64`). Load `references/jjwt-0.12.md`.
- **Spring 6 / Boot 3:**
  - `WebMvcConfigurerAdapter` and `HandlerInterceptorAdapter` become interfaces.
  - Status codes are `HttpStatusCode`.
  - `@ConstructorBinding` moved packages.
  - `spring.factories` auto-config moves to `AutoConfiguration.imports`.
  - Wildcard `javax.annotation.*` and `javax.transaction.*` imports must be split: Jakarta EE types go to `jakarta.*`, and JDK types (`javax.annotation.processing`, `javax.transaction.xa`) stay `javax`.
  - Load `references/boot3-pom-and-jakarta.md`.
- **pom review items:**
  - Replace incompatible libraries (springfox becomes springdoc-openapi-starter-webmvc-ui 2.x).
  - Drop explicit Spring versions so Boot 3.2 manages them.
  - Align Spring Cloud to 2023.0.x.
  - Replace any `javax.*` artifact with its Jakarta coordinates.
- Findings that are only informational need no change, for example a dialect line that is already a Hibernate 6 name. Say so in your answer.

Do not change behaviour, and do not run Maven yet.

Answer with `legacy_api_changes`: one short paragraph listing what you changed per file and which findings needed nothing.

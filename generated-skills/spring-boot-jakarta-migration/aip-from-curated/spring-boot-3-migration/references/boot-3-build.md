# Spring Boot 2.x → 3.x: build file, dependencies, build & test

The Boot 3 upgrade is one of the largest in Boot history because of the Java EE → Jakarta EE
move. Targets used by this skill: Spring Boot **3.2.0**, Java **21** (17 is the minimum),
jjwt **0.12.3**.

## Recommended migration order

1. Upgrade to the latest 2.7.x first if the project is older than 2.7.
2. Update the Java version to 17 or 21.
3. Remove incompatible dependencies (JAXB, old JWT).
4. Update the Spring Boot parent to 3.2.x.
5. Fix namespace imports (javax → jakarta).
6. Update the Spring Security configuration.
7. Update HTTP clients (RestTemplate → RestClient).
8. Run the full test suite.

## pom.xml changes

```xml
<!-- parent: 2.7.18 -> 3.2.0 -->
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.2.0</version>
</parent>

<properties>
    <java.version>21</java.version>   <!-- was 1.8 / 8 / 11; Boot 3 requires 17+ -->
</properties>
```

### Remove (CRITICAL) — incompatible with Spring Boot 3

- `javax.xml.bind:jaxb-api` — **must be removed.** Added in Boot 2 projects for Java 9+
  compatibility (often "needed for JWT"); conflicts with `jakarta.xml.bind`.
- `com.sun.xml.bind:jaxb-impl`, `com.sun.xml.bind:jaxb-core`
- `javax.activation:activation`, `javax.activation:javax.activation-api`

Why: `javax.xml.bind` is the old Java EE namespace and conflicts with Jakarta's
`jakarta.xml.bind`; having both on the classpath causes `ClassNotFoundException` and other
runtime errors; Boot 3 brings the Jakarta versions transitively where needed.

If the code actually uses XML binding, add the Jakarta versions (versions managed by Boot):

```xml
<dependency>
    <groupId>jakarta.xml.bind</groupId>
    <artifactId>jakarta.xml.bind-api</artifactId>
</dependency>
<dependency>
    <groupId>org.glassfish.jaxb</groupId>
    <artifactId>jaxb-runtime</artifactId>
</dependency>
```

### Replace the JWT library

```xml
<!-- before -->
<dependency>
    <groupId>io.jsonwebtoken</groupId>
    <artifactId>jjwt</artifactId>
    <version>0.9.1</version>
</dependency>
<!-- after -->
<dependency>
    <groupId>io.jsonwebtoken</groupId>
    <artifactId>jjwt-api</artifactId>
    <version>0.12.3</version>
</dependency>
<dependency>
    <groupId>io.jsonwebtoken</groupId>
    <artifactId>jjwt-impl</artifactId>
    <version>0.12.3</version>
    <scope>runtime</scope>
</dependency>
<dependency>
    <groupId>io.jsonwebtoken</groupId>
    <artifactId>jjwt-jackson</artifactId>
    <version>0.12.3</version>
    <scope>runtime</scope>
</dependency>
```

jjwt 0.12 code changes (only if the project calls jjwt):
- `Jwts.parser()` now returns a builder: `Jwts.parser().verifyWith(key).build().parseSignedClaims(token).getPayload()`
  (old: `Jwts.parser().setSigningKey(k).parseClaimsJws(t).getBody()`).
- Keys: `Keys.hmacShaKeyFor(secret.getBytes(StandardCharsets.UTF_8))`; HMAC secrets must be
  ≥ 256 bits or jjwt throws `WeakKeyException`. `TextCodec` is gone (`Decoders.BASE64`).
- Builder: `Jwts.builder().subject(s).issuedAt(d).expiration(d).signWith(key).compact()`
  (`setSubject`/`signWith(SignatureAlgorithm, String)` are deprecated).

### Other dependencies

Every third-party dependency must have a Jakarta-compatible version. Drop explicit versions of
Boot-managed artifacts (hibernate-core, spring-boot-maven-plugin) so the Boot 3 BOM manages
them. Known swaps: springfox → `org.springdoc:springdoc-openapi-starter-webmvc-ui` 2.x;
`javax.servlet-api` → remove (embedded Tomcat) or `jakarta.servlet-api`; `validation-api` →
`spring-boot-starter-validation`.

## Common issues

1. **Compilation errors after the upgrade** — mostly `javax.*` imports; change to `jakarta.*`.
2. **H2 dialect** — `spring.jpa.database-platform=org.hibernate.dialect.H2Dialect` keeps its
   name; Hibernate 6 usually auto-detects it so the property may be removed.
3. **Actuator endpoints** — paths/exposure changed; review security rules for exposed
   actuator endpoints.
4. **Property renames** — if Boot logs renamed/removed properties, temporarily add
   `org.springframework.boot:spring-boot-properties-migrator` (runtime) to get the new names,
   fix them, then remove it.

## Manual commands (fallback; GNU sed in the container)

```bash
sed -i 's/<version>2\.7\.[0-9]*<\/version>/<version>3.2.0<\/version>/g' pom.xml   # check it only hit the parent!
sed -i 's/<java.version>1\.8<\/java.version>/<java.version>21<\/java.version>/g' pom.xml
sed -i 's/<java.version>8<\/java.version>/<java.version>21<\/java.version>/g' pom.xml
sed -i 's/<java.version>11<\/java.version>/<java.version>21<\/java.version>/g' pom.xml
grep -n "jaxb-api\|javax\.xml\.bind" pom.xml   # remove these blocks by hand (multi-line)
```

## OpenRewrite (alternative for large codebases; needs network)

```xml
<plugin>
    <groupId>org.openrewrite.maven</groupId>
    <artifactId>rewrite-maven-plugin</artifactId>
    <version>5.42.0</version>
    <configuration>
        <activeRecipes>
            <recipe>org.openrewrite.java.spring.boot3.UpgradeSpringBoot_3_2</recipe>
        </activeRecipes>
    </configuration>
    <dependencies>
        <dependency>
            <groupId>org.openrewrite.recipe</groupId>
            <artifactId>rewrite-spring</artifactId>
            <version>5.21.0</version>
        </dependency>
    </dependencies>
</plugin>
```

`mvn rewrite:run` updates the Boot version, migrates `javax.*` → `jakarta.*`, updates
deprecated Security patterns and fixes property names. Remove the plugin afterwards and still
run the verification below.

## Verification

```bash
grep -A2 "spring-boot-starter-parent" pom.xml | grep version   # 3.x
grep "java.version" pom.xml                                      # 17 or 21
grep "jaxb-api" pom.xml                                          # no results
grep "javax\.xml\.bind" pom.xml                                  # no results
grep "<version>0\.9\.1</version>" pom.xml                        # no results (old jjwt)
```

## Build and test in the task container

The container (Ubuntu + SDKMAN) has Java 8 and Java 21 and Maven 3.9.6; Java 21 is the default.

```bash
source /root/.sdkman/bin/sdkman-init.sh      # puts mvn/java on PATH in non-login shells
sdk use java 21.0.2-tem                       # make sure the build runs on 21, not 8
java -version && mvn -v
cd <project_dir>
mvn -B clean compile                          # then
mvn -B test                                   # full suite
```

- Use `./mvnw` if the project ships a wrapper.
- The image pre-downloaded the **Boot 2.7** dependency tree only; Boot 3 artifacts must be
  fetched. If Maven reports it cannot resolve artifacts and the network is unavailable, that
  is an environment limit, not a code error — try `mvn -o` once, then report it.
- Read the first compiler error, fix the code, rerun; don't add `-DskipTests` or delete tests
  to get green.

# Maven dependency fix patterns

One template per `pick-fix-pattern.one_of` value. Match the error class from
`classify-error` to the smallest fix that resolves it.

## Decision rules (error class → pattern)

| error_class       | First-choice pattern                          | Alt / fallback                          |
|-------------------|-----------------------------------------------|-----------------------------------------|
| `missing-artifact`| `fix-repository-config` (typo, missing repo)  | `add-missing-dependency` (new dep)      |
| `package-not-found` (compile) | `change-scope` (provided→compile, test→compile) | `add-missing-dependency` |
| `class-not-found` / `method-not-found` (runtime) | `pin-version-in-dependencyManagement` (transitive skew) | `change-scope` (compile→runtime) |
| `version-conflict`| `pin-version-in-dependencyManagement`         | `import-bom` if it's a framework family |
| `compile-symbol`  | `add-missing-dependency`                      | `change-scope`                          |
| `other`           | Read `references/maven-reference.md` first    | —                                       |

Rule of thumb: prefer `<dependencyManagement>` over per-dep `<version>` so
all paths converge. Prefer BOM import over hand-pinning when a curated BOM
exists for the family.

---

## pin-version-in-dependencyManagement

Pins a single coordinate. Add to the root/parent pom so every module agrees.

```xml
<dependencyManagement>
  <dependencies>
    <dependency>
      <groupId>org.slf4j</groupId>
      <artifactId>slf4j-api</artifactId>
      <version>2.0.9</version>
    </dependency>
  </dependencies>
</dependencyManagement>
```

Use when: `dependency:tree -Dverbose=true` shows two paths bringing the same
artifact at different versions and the convergent version is known-good.

## import-bom

A curated BOM is one pom that pins many coordinates consistently — use it
instead of pinning each one. The `<type>pom</type><scope>import</scope>` pair
only works inside `<dependencyManagement>`.

```xml
<dependencyManagement>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-dependencies</artifactId>
      <version>3.2.0</version>
      <type>pom</type>
      <scope>import</scope>
    </dependency>
  </dependencies>
</dependencyManagement>
```

Common BOMs: `spring-boot-dependencies`, `jackson-bom`, `junit-bom`,
`software.amazon.awssdk:bom`, `io.netty:netty-bom`.

After importing, drop the `<version>` from each managed dependency in the
module poms — re-adding `<version>` overrides the BOM and reintroduces drift.

## add-exclusion

Strip a transitive that shouldn't be on the classpath. Always add a
replacement if the excluded artifact provided functionality.

```xml
<dependency>
  <groupId>org.springframework.boot</groupId>
  <artifactId>spring-boot-starter-web</artifactId>
  <exclusions>
    <exclusion>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-tomcat</artifactId>
    </exclusion>
  </exclusions>
</dependency>
<dependency>
  <groupId>org.springframework.boot</groupId>
  <artifactId>spring-boot-starter-jetty</artifactId>
</dependency>
```

Use when: duplicate classes on classpath, wrong implementation pulled in
(servlet container, logging backend), or a transitive ships an incompatible
license.

## change-scope

`compile`/`provided`/`runtime`/`test` mismatch. Pick by where the symbol is
needed:

| Symbol needed at        | Required scope |
|------------------------|----------------|
| compile + test + runtime | `compile` (default) |
| compile + test only (container supplies at runtime) | `provided` |
| runtime + test only (driver, impl class loaded reflectively) | `runtime` |
| test only              | `test` |

```xml
<dependency>
  <groupId>jakarta.servlet</groupId>
  <artifactId>jakarta.servlet-api</artifactId>
  <version>6.0.0</version>
  <scope>provided</scope>
</dependency>
```

`system` scope is non-portable — do not introduce it.

## add-missing-dependency

The agent's code references a package/class the pom doesn't declare. Add the
smallest declaration that resolves the symbol.

```xml
<dependency>
  <groupId>org.apache.commons</groupId>
  <artifactId>commons-lang3</artifactId>
  <version>3.14.0</version>
</dependency>
```

Confirm before adding: run `mvn dependency:analyze` — "Used undeclared
dependencies" lists exactly what's missing.

## fix-repository-config

`Could not find artifact` despite correct coordinates → the repo hosting it
isn't reachable. Check spelling first, then repository config.

```xml
<repositories>
  <repository>
    <id>company-repo</id>
    <url>https://nexus.company.com/repository/maven-public</url>
    <releases><enabled>true</enabled></releases>
    <snapshots><enabled>true</enabled></snapshots>
  </repository>
</repositories>
```

Credentials live in `~/.m2/settings.xml` under `<servers>` matching the
`<id>`. Do not put credentials in pom.xml.

---

## Diff conventions for `patch_<i>.diff`

The verifier parses with `unidiff` and the agent applies with `git apply`,
so output must be `git diff` format (paths prefixed `a/` and `b/`):

```diff
diff --git a/pom.xml b/pom.xml
index 1111111..2222222 100644
--- a/pom.xml
+++ b/pom.xml
@@ -42,6 +42,7 @@
       <dependency>
         <groupId>org.slf4j</groupId>
         <artifactId>slf4j-api</artifactId>
+        <version>2.0.9</version>
       </dependency>
```

Generate by editing the pom then `git -C <repo> diff --no-color > patch_0.diff`.
Number patches `patch_0.diff`, `patch_1.diff`, … in the repo root.

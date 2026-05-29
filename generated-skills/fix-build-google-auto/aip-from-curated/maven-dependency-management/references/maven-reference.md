# Maven dependency reference (load on demand)

Detailed reference distilled from the original curated skill. The body's
`search_shortcuts` already covers the quick cases — load this file when you
need an XML template, the full scope table, multi-module wiring, or
troubleshooting commands.

## Dependency declaration

### Basic
```xml
<dependency>
  <groupId>org.springframework.boot</groupId>
  <artifactId>spring-boot-starter-web</artifactId>
  <version>3.2.0</version>
</dependency>
```

### Optional
```xml
<dependency>
  <groupId>com.google.code.findbugs</groupId>
  <artifactId>jsr305</artifactId>
  <version>3.0.2</version>
  <optional>true</optional>
</dependency>
```

## Scopes (full table)

| Scope    | Compile CP | Test CP | Runtime CP | Transitive |
|----------|-----------|---------|------------|------------|
| compile  | yes       | yes     | yes        | yes        |
| provided | yes       | yes     | no         | no         |
| runtime  | no        | yes     | yes        | yes        |
| test     | no        | yes     | no         | no         |
| system   | yes       | yes     | no         | no         |
| import   | n/a       | n/a     | n/a        | n/a (BOM only) |

## Version management

### Property-based
```xml
<properties>
  <spring-boot.version>3.2.0</spring-boot.version>
</properties>
<dependencies>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
    <version>${spring-boot.version}</version>
  </dependency>
</dependencies>
```

### Range syntax
| Form           | Meaning                       |
|----------------|-------------------------------|
| `1.0.0`        | Soft pin; transitive can override |
| `[1.0.0]`      | Hard pin; no override        |
| `[1.0.0,)`     | >= 1.0.0                     |
| `(,1.0.0)`     | < 1.0.0                      |
| `[1.0.0,2.0.0]`| inclusive range              |
| `(1.0.0,2.0.0)`| exclusive range              |

`LATEST` and `RELEASE` are removed in Maven 3+ for non-plugin deps. Do not
use them.

## Conflict resolution

Maven's default rule: **nearest definition wins** (fewest hops from root).
```
A -> B -> C 1.0
A -> C 2.0          ← chosen (depth 1 beats depth 2)
```

Force a version via `<dependencyManagement>` at the parent — that overrides
nearest-wins for every module.

### Enforcer plugin
```xml
<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-enforcer-plugin</artifactId>
  <version>3.4.1</version>
  <executions>
    <execution>
      <id>enforce</id>
      <goals><goal>enforce</goal></goals>
      <configuration>
        <rules>
          <dependencyConvergence/>
          <requireUpperBoundDeps/>
          <banDuplicatePomDependencyVersions/>
        </rules>
      </configuration>
    </execution>
  </executions>
</plugin>
```

## Multi-module projects

### Parent pom
```xml
<project>
  <groupId>com.example</groupId>
  <artifactId>parent</artifactId>
  <version>1.0.0</version>
  <packaging>pom</packaging>
  <dependencyManagement>
    <dependencies>
      <dependency>
        <groupId>com.example</groupId>
        <artifactId>common</artifactId>
        <version>${project.version}</version>
      </dependency>
    </dependencies>
  </dependencyManagement>
</project>
```

### Child module
```xml
<project>
  <parent>
    <groupId>com.example</groupId>
    <artifactId>parent</artifactId>
    <version>1.0.0</version>
  </parent>
  <artifactId>module</artifactId>
  <dependencies>
    <dependency>
      <groupId>com.example</groupId>
      <artifactId>common</artifactId>
    </dependency>
  </dependencies>
</project>
```

## Repository configuration

### Central (implicit, but overridable)
```xml
<repositories>
  <repository>
    <id>central</id>
    <url>https://repo.maven.apache.org/maven2</url>
  </repository>
</repositories>
```

### Private with credentials
`pom.xml`:
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

`~/.m2/settings.xml`:
```xml
<settings>
  <servers>
    <server>
      <id>company-repo</id>
      <username>${env.REPO_USER}</username>
      <password>${env.REPO_PASS}</password>
    </server>
  </servers>
</settings>
```

## Dependency analysis commands

```bash
mvn dependency:tree                                # full tree
mvn dependency:tree -Dincludes=org.slf4j           # filter by groupId
mvn dependency:tree -DoutputFile=deps.txt          # write to file
mvn dependency:tree -Dverbose=true                 # show conflict resolution

mvn dependency:analyze                             # unused + undeclared
mvn dependency:analyze-only                        # warnings only
mvn dependency:analyze -DignoreNonCompile=false    # include test scope

mvn dependency:list                                # flat list
mvn dependency:list -DincludeScope=runtime         # runtime only

mvn help:effective-pom                             # resolved versions
```

## Troubleshooting

```bash
mvn dependency:tree -X                  # debug-level diagnostics
mvn dependency:tree -Dverbose=true      # show which version wins
mvn dependency:purge-local-repository   # nuke local ~/.m2 cache entries
mvn -U clean install                    # force snapshot re-download
mvn help:effective-pom                  # see fully resolved pom
```

## Common pitfalls (mapped to anti-patterns in SKILL.md)

- Transitive version conflict — fix via `<dependencyManagement>`, not direct `<version>` bump.
- Duplicate classes from two artifacts → `<exclusions>` on the offender.
- Wrong scope (`compile` vs `runtime` vs `provided`) → see fix-patterns.md → change-scope.
- `<scope>system</scope>` with absolute paths breaks portability — avoid.
- `LATEST` / `RELEASE` / open-ended ranges → non-reproducible builds.
- Re-adding `<version>` on a BOM-managed dep — defeats the BOM.
- Optional dependency that's actually required — leads to runtime ClassNotFound.

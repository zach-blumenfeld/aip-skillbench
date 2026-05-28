# Maven dependency scopes

| Scope    | Compile CP | Test CP | Runtime CP | Packaged | Transitive | Notes |
|----------|------------|---------|------------|----------|------------|-------|
| compile  | Yes        | Yes     | Yes        | Yes      | Yes        | Default. Use when the code references the artifact and it must be in the deployed artifact. |
| provided | Yes        | Yes     | No         | No       | No         | Use for APIs the container/runtime supplies (servlet-api, lombok-as-API). |
| runtime  | No         | Yes     | Yes        | Yes      | Yes        | Use when only an interface is on the compile path but a concrete impl is needed at runtime (JDBC drivers, SLF4J bindings). |
| test     | No         | Yes     | No         | No       | No         | Use for test-only libraries (JUnit, Mockito). Never compile path. |
| system   | Yes        | Yes     | No         | No       | No         | **Avoid.** Requires a hardcoded `<systemPath>`. Breaks portability and is deprecated since Maven 3.x. |
| import   | n/a        | n/a     | n/a        | n/a      | n/a        | Only valid inside `<dependencyManagement>` with `<type>pom</type>`. Pulls another POM's `<dependencyManagement>` block in. |

## Picking a scope

- Production code uses it at compile time → `compile`.
- Tests use it; production code never imports it → `test`.
- App server / runtime container provides it (e.g., `jakarta.servlet-api`,
  `lombok` for IDE only) → `provided`.
- App only needs the JAR on the runtime classpath, never at compile (e.g.,
  Postgres driver, Logback) → `runtime`.

## Symptoms of wrong scope

| Symptom                                              | Likely scope mistake          |
|------------------------------------------------------|-------------------------------|
| `ClassNotFoundException` only in production         | scope=test, should be compile or runtime |
| Duplicate classes from container + app               | scope=compile, should be provided |
| Test code compiles in IDE but fails in `mvn test`    | scope=compile in test module that should be test |
| App still pulls in big artifact you only test with   | scope=compile, should be test |

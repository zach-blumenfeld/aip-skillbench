# Debugging Builds and CI/CD Integration

## Verbosity flags

```bash
mvn install -X     # full debug output (very noisy, but shows plugin classpath, parameter resolution)
mvn install -e     # show stack traces on errors (much smaller than -X)
mvn install -q     # quiet — only errors
mvn install -B     # batch mode (no color, no interactive prompts; use in CI)
```

Pick `-e` first; reach for `-X` only when `-e` isn't enough.

## Effective configuration

```bash
mvn help:effective-pom            # fully resolved POM (parents + profiles + inheritance)
mvn help:effective-settings       # resolved settings.xml
mvn help:active-profiles          # which profiles are actually on right now
mvn help:evaluate -Dexpression=project.version
mvn help:describe -Dplugin=compiler -Ddetail   # plugin params and defaults
```

`mvn help:effective-pom -Pci` resolves with a profile flagged on — invaluable when CI fails and local doesn't (or vice versa).

## Dependency analysis

```bash
mvn dependency:tree                            # full transitive graph
mvn dependency:tree -Dverbose -Dincludes=com.google.guava   # who pulled in guava, including dupes
mvn dependency:analyze                         # used-undeclared / unused-declared dependencies
mvn dependency:resolve                         # force-resolve all deps (fails fast on missing artifacts)
mvn versions:display-plugin-updates            # newer plugin versions available
mvn versions:display-dependency-updates        # newer dependency versions available
```

## Common debugging recipe — build is failing, don't know why

1. `mvn -B clean compile -e` — does it even compile? `-e` keeps output reviewable.
2. If compile fails, the message names a file and a phase. Look up where that phase sits in `lifecycle-phases.md`.
3. If compile passes but a later phase fails: `mvn -B install -e -fae` — `-fae` keeps the reactor going so multiple module failures are visible at once.
4. `mvn help:effective-pom > effective.xml` — diff against what you expected, especially `<source>`, `<target>`, plugin versions, and active executions.
5. `mvn help:active-profiles` — confirm the profile mix matches the failing scenario.
6. `mvn dependency:tree -Dverbose` — version conflicts and omitted-for-duplicate / omitted-for-conflict notes here explain most NoSuchMethodError / NoClassDefFoundError failures at `test` or runtime.
7. Only after the diagnostics: edit code, edit `pom.xml`, or change the build command.

## CI/CD integration

### GitHub Actions

```yaml
- name: Build with Maven
  run: mvn -B clean verify -Pci

- name: Release
  run: mvn -B deploy -Prelease -DskipTests
```

### Jenkins pipeline

```groovy
stage('Build') {
  steps { sh 'mvn -B clean package -DskipTests' }
}
stage('Test') {
  steps { sh 'mvn -B test' }
}
stage('Integration Test') {
  steps { sh 'mvn -B verify -DskipUnitTests' }
}
```

`-B` (batch mode) and explicit profile activation (`-Pci`) are the two most common deltas between a CI build and a local one — when a build passes locally and fails in CI, check those first.

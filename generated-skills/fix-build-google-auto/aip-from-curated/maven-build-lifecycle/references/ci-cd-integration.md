# CI/CD Integration

## GitHub Actions

```yaml
- name: Build with Maven
  run: mvn -B clean verify -Pci

- name: Release
  run: mvn -B deploy -Prelease -DskipTests
```

`-B` is `--batch-mode` — disables interactive prompts and removes the
download-progress noise from logs.

## Jenkins Pipeline

```groovy
stage('Build') {
    steps {
        sh 'mvn -B clean package -DskipTests'
    }
}
stage('Test') {
    steps {
        sh 'mvn -B test'
    }
}
stage('Integration Test') {
    steps {
        sh 'mvn -B verify -DskipUnitTests'
    }
}
```

## CI build hygiene

- `mvn -B` in every step — required for non-interactive runs.
- `mvn -ff` to fail fast on the first reactor failure in CI.
- Use a dedicated `ci` profile rather than scattering CI-only flags
  through the command line.
- Cache `~/.m2/repository` between runs but never commit it.
- Run `mvn verify` (not `mvn test`) in CI when you have integration
  tests bound to Failsafe — `test` skips them silently.

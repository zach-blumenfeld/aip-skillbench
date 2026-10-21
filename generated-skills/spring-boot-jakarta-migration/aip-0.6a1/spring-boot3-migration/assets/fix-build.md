The migrated project at `{workspace}` is not finished yet. Here is the verify report (full Maven logs are in its `log_dir`):

{verify_report}

Fix it, then loop until it is clean:

1. Read `compile_errors` first, then `test_errors`, then `residual_issues`. In the logs, find the first `[ERROR]` with a file and line number, and the first `Caused by:` of a failed `contextLoads`.
2. Fix the root cause in source or in `pom.xml`. Common causes are listed in `references/boot3-pom-and-jakarta.md`: wrong JDK, `HttpStatus` vs `HttpStatusCode`, removed Spring 5 adapters, renamed properties, bean wiring. For security, RestClient, Hibernate or jjwt problems, load the matching reference.
3. In `{workspace}`, re-run exactly `mvn clean compile` and then `mvn test`. Use JDK 21 (in the task container: `source /root/.sdkman/bin/sdkman-init.sh` if `mvn` or `java` is missing). Repeat until both succeed.
4. Clear every `residual_issues` entry as well, even when the build is green. Legacy patterns such as RestTemplate, chained security DSL, `javax` EE imports, jaxb-api or jjwt 0.9.1 mean the migration is incomplete.

Never delete, `@Disabled` or weaken a test. Never pin Spring Boot back to 2.x or Java below 21.

Answer with:
- `build_fixes`: what was wrong and what you changed.
- `final_build_status`: the last result of `mvn clean compile` and `mvn test` (for example "compile OK; Tests run: 6, Failures: 0, Errors: 0").

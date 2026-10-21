Replace `RestTemplate` with Spring 6.1 `RestClient` in the project at `{workspace}`. Usages found:

{rest_template_findings}

For each class:

1. Replace the `RestTemplate` field/bean with a `RestClient`: use `RestClient.create()` or an injected `RestClient.Builder`. A `RestTemplate` `@Bean` becomes a `RestClient` `@Bean`.
2. Translate each call:
   - `getForEntity(url, Map.class)` becomes `.get().uri(...).retrieve().body(new ParameterizedTypeReference<Map<String, Object>>() ...)`.
   - `postForEntity(url, new HttpEntity<>(payload, headers), Void.class)` becomes `.post().uri(...).contentType(...).accept(...).body(payload).retrieve().toBodilessEntity()`.
   - `exchange(url, HttpMethod.GET, new HttpEntity<>(headers), Map.class)` becomes `.get().uri(...).accept(...).retrieve().body(...)`.
   - `delete(url)` becomes `.delete().uri(...).retrieve().toBodilessEntity()`.
   Use URI template variables for path and query values instead of string concatenation.
3. Keep every public method's signature, return values, null handling and try/catch fallbacks exactly as before. Keep a no-arg constructor if one existed. Do not read `@Value` fields inside the constructor: they are still null there.
4. Every request chain must end in `.body(...)`, `.toEntity(...)` or `.toBodilessEntity()`. Without one of these, no request is sent.
5. Remove unused imports (`RestTemplate`, `HttpEntity`, `HttpHeaders`, `HttpMethod`, `ResponseEntity`, `Collections` if unused). Add `org.springframework.web.client.RestClient` and `org.springframework.core.ParameterizedTypeReference`.
6. If tests bind `MockRestServiceServer` to the `RestTemplate`, rebind them to the `RestClient.Builder`. Leave `TestRestTemplate` alone.

Load `references/restclient-migration.md` for the full before/after examples (GET, POST, exchange with headers, DELETE, error handlers, configured bean).

Answer with `restclient_changes`: one short paragraph naming each migrated class and method.

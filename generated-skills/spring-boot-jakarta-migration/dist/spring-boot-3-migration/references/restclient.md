# RestTemplate → RestClient (Spring Framework 6.1 / Boot 3.2+)

Load this before migrating any `RestTemplate` usage (client task "RestClient rewrite"), and when a build
failure is triaged as `restclient`. `RestClient` is the fluent synchronous client that replaces
`RestTemplate` (template methods → fluent builder; `ResponseErrorHandler` → `onStatus` handlers; better
generics). For reactive apps use `WebClient` instead; `RestClient` is the choice for non-reactive code.

## Keep the wiring shape

| Old wiring | New wiring |
|---|---|
| `this.restTemplate = new RestTemplate();` in the constructor | `this.restClient = RestClient.create();` |
| `RestTemplate` `@Bean` built from `RestTemplateBuilder` | `RestClient` `@Bean` built from the auto-configured `RestClient.Builder` |
| `builder.rootUri(url)` | `builder.baseUrl(url)` (then use relative URIs) |
| `builder.setConnectTimeout(d)` / `setReadTimeout(d)` | `SimpleClientHttpRequestFactory f = new SimpleClientHttpRequestFactory(); f.setConnectTimeout(d); f.setReadTimeout(d); builder.requestFactory(f)` |
| `RestTemplate` constructor-injected into a service | inject `RestClient` |

Configured bean example:

```java
@Configuration
public class RestClientConfig {
    @Value("${external.api.base-url}")
    private String baseUrl;

    @Bean
    public RestClient restClient() {
        return RestClient.builder()
            .baseUrl(baseUrl)
            .defaultHeader(HttpHeaders.CONTENT_TYPE, MediaType.APPLICATION_JSON_VALUE)
            .defaultHeader(HttpHeaders.ACCEPT, MediaType.APPLICATION_JSON_VALUE)
            .build();
    }
}
// service: public ExternalApiService(RestClient restClient) { this.restClient = restClient; }
//          restClient.get().uri("/users/{id}", userId)...   (relative URI)
```

Do not switch a self-constructing service to an injected bean (or the reverse) unless needed: a
`@Value` field is not populated inside the constructor, so keep `baseUrl +` concatenation in each call
when the old code did that.

## Call mappings

| RestTemplate | RestClient |
|---|---|
| `getForEntity(url, Map.class).getBody()` / `getForObject(url, Map.class)` | `restClient.get().uri(url).retrieve().body(new ParameterizedTypeReference<Map<String, Object>>() {})` |
| `getForObject(url, User.class, vars...)` | `restClient.get().uri(url, vars...).retrieve().body(User.class)` |
| `postForEntity(url, new HttpEntity<>(payload, headers), Void.class)` | `restClient.post().uri(url).contentType(MediaType.APPLICATION_JSON).accept(MediaType.APPLICATION_JSON).body(payload).retrieve().toBodilessEntity()` |
| `exchange(url, HttpMethod.GET, new HttpEntity<>(headers), Map.class).getBody()` | `restClient.get().uri(url).accept(MediaType.APPLICATION_JSON).retrieve().body(new ParameterizedTypeReference<Map<String, Object>>() {})` |
| `delete(url)` | `restClient.delete().uri(url).retrieve().toBodilessEntity()` |
| `put(url, body)` | `restClient.put().uri(url).body(body).retrieve().toBodilessEntity()` |
| `ResponseEntity<T>` needed (status/headers) | `.retrieve().toEntity(T.class)` |

- Put path/query variables in URI templates instead of string concatenation:
  `.uri(baseUrl + "/users/{id}/profile", userId)`, `.uri(baseUrl + "/verify/email?email={email}", email)`
  (values get URL-encoded).
- `HttpHeaders`/`HttpEntity` building disappears: headers go on the request spec (`.contentType`,
  `.accept`, `.header(name, value)`).
- Generic bodies (`Map`, `List<User>`) need `ParameterizedTypeReference`; simple types use `.body(User.class)`,
  `.body(String.class)`.
- `body(...)` may return `null`: keep the old null checks (`response != null && Boolean.TRUE.equals(response.get("valid"))`).
- Keep every `try/catch` and its fallback value (`return false`, `Collections.emptyMap()`, log line) exactly:
  4xx/5xx still throw (`RestClientResponseException` subclasses) like RestTemplate did.
- Drop now-unused imports (`RestTemplate`, `HttpEntity`, `HttpHeaders`, `HttpMethod`, `ResponseEntity`)
  and update Javadoc/comments that mention RestTemplate.

## Complete method examples

```java
public boolean verifyEmail(String email) {
    try {
        Map<String, Object> response = restClient.get()
            .uri(baseUrl + "/verify/email?email={email}", email)
            .retrieve()
            .body(new ParameterizedTypeReference<Map<String, Object>>() {});
        return response != null && Boolean.TRUE.equals(response.get("valid"));
    } catch (Exception e) {
        return false;
    }
}

public void sendNotification(String userId, String message) {
    Map<String, String> payload = Map.of("userId", userId, "message", message);
    restClient.post()
        .uri(baseUrl + "/notifications")
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaType.APPLICATION_JSON)
        .body(payload)
        .retrieve()
        .toBodilessEntity();
}

public boolean requestDataDeletion(String userId) {
    try {
        restClient.delete().uri(baseUrl + "/users/{id}/data", userId).retrieve().toBodilessEntity();
        return true;
    } catch (Exception e) {
        return false;
    }
}
```

## Error handling with status handlers (only where the old code had a ResponseErrorHandler or mapped errors)

```java
return restClient.get()
    .uri("/users/{id}", userId)
    .retrieve()
    .onStatus(HttpStatusCode::is4xxClientError, (request, response) -> {
        throw new UserNotFoundException("User not found: " + userId);
    })
    .onStatus(HttpStatusCode::is5xxServerError, (request, response) -> {
        throw new ExternalServiceException("External service error");
    })
    .body(new ParameterizedTypeReference<Map<String, Object>>() {});
```

## WebClient (reactive only)

```java
WebClient webClient = WebClient.create(baseUrl);
Mono<User> userMono = webClient.get().uri("/users/{id}", userId).retrieve().bodyToMono(User.class);
```
Needs `spring-boot-starter-webflux`; do not add it to a servlet app just for HTTP calls.

Tests that use `MockRestServiceServer` bound to a `RestTemplate` must bind to the `RestClient.Builder`
instead (`MockRestServiceServer.bindTo(builder)`) — change only the wiring, not the assertions.

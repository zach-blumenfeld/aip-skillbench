# RestTemplate → RestClient (Spring Boot 3.2+ / Spring Framework 6.1)

`RestClient` is the fluent synchronous HTTP client that replaces `RestTemplate`. RestTemplate
still compiles, but the Boot 3 migration replaces it. `RestClient` needs Boot **3.2+**.

| Feature | RestTemplate | RestClient |
|---|---|---|
| API style | Template methods | Fluent builder |
| Configuration | Constructor injection | Builder pattern |
| Error handling | ResponseErrorHandler | Status handlers (`onStatus`) |
| Type safety | Limited (`Map.class` raw) | Generics via `ParameterizedTypeReference` |

Imports: `org.springframework.web.client.RestClient`,
`org.springframework.core.ParameterizedTypeReference`, `org.springframework.http.MediaType`,
`org.springframework.http.HttpStatusCode` (for `onStatus`).

Rules of thumb: keep each method's signature, return values, try/catch and fallback behaviour
(e.g. `return false` / `Collections.emptyMap()` on failure) exactly as before; drop the now
unused `HttpHeaders`/`HttpEntity`/`HttpMethod`/`ResponseEntity` imports; use URI templates
(`"/users/{id}", userId`) instead of string concatenation; null-check bodies.

## GET

```java
// Before
private final RestTemplate restTemplate;
public ExternalApiService() { this.restTemplate = new RestTemplate(); }
public Map<String, Object> getUser(String userId) {
    String url = "https://api.example.com/users/" + userId;
    ResponseEntity<Map> response = restTemplate.getForEntity(url, Map.class);
    return response.getBody();
}

// After
private final RestClient restClient;
public ExternalApiService() { this.restClient = RestClient.create(); }
public Map<String, Object> getUser(String userId) {
    return restClient.get()
        .uri("https://api.example.com/users/{id}", userId)
        .retrieve()
        .body(new ParameterizedTypeReference<Map<String, Object>>() {});
}
```

## POST with body and headers

```java
// Before
HttpHeaders headers = new HttpHeaders();
headers.setContentType(MediaType.APPLICATION_JSON);
headers.setAccept(Collections.singletonList(MediaType.APPLICATION_JSON));
Map<String, String> payload = Map.of("userId", userId, "message", message);
HttpEntity<Map<String, String>> request = new HttpEntity<>(payload, headers);
restTemplate.postForEntity(baseUrl + "/notifications", request, Void.class);

// After
Map<String, String> payload = Map.of("userId", userId, "message", message);
restClient.post()
    .uri(baseUrl + "/notifications")
    .contentType(MediaType.APPLICATION_JSON)
    .accept(MediaType.APPLICATION_JSON)
    .body(payload)
    .retrieve()
    .toBodilessEntity();
```

## exchange() with custom headers

```java
// Before
HttpHeaders headers = new HttpHeaders();
headers.setAccept(Collections.singletonList(MediaType.APPLICATION_JSON));
HttpEntity<?> request = new HttpEntity<>(headers);
ResponseEntity<Map> response = restTemplate.exchange(
    baseUrl + "/users/" + userId + "/profile", HttpMethod.GET, request, Map.class);
return response.getBody();

// After
return restClient.get()
    .uri(baseUrl + "/users/{id}/profile", userId)
    .accept(MediaType.APPLICATION_JSON)
    .retrieve()
    .body(new ParameterizedTypeReference<Map<String, Object>>() {});
```

## DELETE

```java
// Before
restTemplate.delete(baseUrl + "/users/" + userId + "/data");

// After
restClient.delete()
    .uri(baseUrl + "/users/{id}/data", userId)
    .retrieve()
    .toBodilessEntity();
```

## Complete service example (query parameter, @Value base URL)

```java
// Before
@Service
public class ExternalApiService {
    private final RestTemplate restTemplate;
    @Value("${external.api.base-url}")
    private String baseUrl;
    public ExternalApiService() { this.restTemplate = new RestTemplate(); }
    public boolean verifyEmail(String email) {
        try {
            String url = baseUrl + "/verify/email?email=" + email;
            ResponseEntity<Map> response = restTemplate.getForEntity(url, Map.class);
            return Boolean.TRUE.equals(response.getBody().get("valid"));
        } catch (Exception e) {
            return false;
        }
    }
}

// After
@Service
public class ExternalApiService {
    private final RestClient restClient;
    @Value("${external.api.base-url}")
    private String baseUrl;
    public ExternalApiService() { this.restClient = RestClient.create(); }
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
}
```

Keep `RestClient.create()` + the `@Value` field when `baseUrl` is field-injected (it is not yet
set inside the constructor, so do not pass it to `RestClient.builder().baseUrl(...)` there).

## Configured RestClient bean (optional)

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

@Service
public class ExternalApiService {
    private final RestClient restClient;
    public ExternalApiService(RestClient restClient) { this.restClient = restClient; }
    public Map<String, Object> getUser(String userId) {      // relative URIs now
        return restClient.get().uri("/users/{id}", userId).retrieve()
            .body(new ParameterizedTypeReference<Map<String, Object>>() {});
    }
}
```

## Error handling with status handlers

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

## Type-safe responses

```java
Map<String, Object> map = restClient.get().uri("/data").retrieve()
    .body(new ParameterizedTypeReference<Map<String, Object>>() {});
List<User> users = restClient.get().uri("/users").retrieve()
    .body(new ParameterizedTypeReference<List<User>>() {});
User user = restClient.get().uri("/users/{id}", userId).retrieve().body(User.class);
String text = restClient.get().uri("/text").retrieve().body(String.class);
```

## WebClient alternative

Only for reactive applications (`spring-boot-starter-webflux`):

```java
WebClient webClient = WebClient.create(baseUrl);
Mono<User> userMono = webClient.get().uri("/users/{id}", userId).retrieve().bodyToMono(User.class);
```

`RestClient` is preferred for synchronous code in non-reactive (servlet) apps — do not add
WebFlux just to replace RestTemplate.

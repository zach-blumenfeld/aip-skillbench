# jjwt 0.9.x to 0.12.x API changes

The build change (monolithic `io.jsonwebtoken:jjwt:0.9.1` to `jjwt-api` plus runtime `jjwt-impl` and `jjwt-jackson` at 0.12.3) is applied by the helper script. Read this only when Java code imports `io.jsonwebtoken`.

| 0.9.x | 0.12.x |
|-------|--------|
| `Jwts.parser().setSigningKey(secret).parseClaimsJws(token).getBody()` | `Jwts.parser().verifyWith(key).build().parseSignedClaims(token).getPayload()` |
| `Jwts.builder().setSubject(s).setIssuedAt(d).setExpiration(e)` | `Jwts.builder().subject(s).issuedAt(d).expiration(e)` (old setters still compile but are deprecated) |
| `.setClaims(map)` | `.claims(map)` |
| `.signWith(SignatureAlgorithm.HS512, secretString)` | `.signWith(key)` where `SecretKey key = Keys.hmacShaKeyFor(secretBytes)` |
| `TextCodec.BASE64.decode(s)`, `DatatypeConverter.parseBase64Binary(s)` | `io.jsonwebtoken.io.Decoders.BASE64.decode(s)` |
| `ExpiredJwtException`, `MalformedJwtException`, `SignatureException` | the same names; `SignatureException` is now `io.jsonwebtoken.security.SignatureException` |

Gotchas:

- `Keys.hmacShaKeyFor` rejects keys shorter than 256 bits for HS256 (512 bits for HS512) with `WeakKeyException`. If a configured test secret is short, derive a long enough key or lengthen the secret in test properties; do not weaken the algorithm silently.
- `Jwts.parser()` now returns a builder. Without `.build()` there is no `parseSignedClaims` method, and this is the usual compile error after the upgrade.
- No JAXB is needed any more. The old `javax.xml.bind` dependency existed only for jjwt 0.9 on Java 9+.

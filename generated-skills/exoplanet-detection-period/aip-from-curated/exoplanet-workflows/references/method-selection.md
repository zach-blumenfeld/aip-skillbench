# Period-search method selection

When the body says "pick TLS, Lomb-Scargle, or BLS", use this reference to
decide. Load only when you need to justify the pick.

## Transit Least Squares (TLS) — default for exoplanets

Use when:
- Searching for transiting exoplanets specifically.
- Signal has transit shape (box-like dips).
- Flux uncertainties are available (TLS *requires* them).

Pros: most sensitive for transits; handles grazing transits; returns transit
parameters (depth, T0, duration, SDE, SNR) directly.

Cons: slower than Lomb-Scargle; only detects transits.

## Lomb-Scargle periodogram — exploration / non-transit periodics

Use when:
- Hunting for any periodic signal (rotation, pulsation).
- Doing fast initial exploration.
- The signal isn't necessarily transit-shaped.

Pros: fast; works for any periodic shape; great for first-pass exploration.

Cons: less sensitive to shallow transits; can confuse harmonics with the
true period.

## Box Least Squares (BLS) — Astropy-native transit search

Use when:
- You want the Astropy-native option (no extra dependency on TLS).
- You need `compute_stats()` for detailed validation (odd-even depths,
  transit count, depth SNR).

Pros: built into Astropy; rich validation stats; fast for targeted searches.

Cons: simpler (box-shaped) transit model; period-grid setup matters more
than for TLS.

## When to combine

The default exoplanet pipeline is **TLS with the canonical preprocessing
recipe**, refined ±5% around the best candidate. Lomb-Scargle is useful
*before* TLS if you suspect stellar rotation is dominating and you want to
characterise it before flattening, or *after* TLS for context. BLS is a
secondary check when you want odd-even diagnostics that TLS doesn't
expose as directly.

# Method Choice

| Method | Best For | Avoid When |
| --- | --- | --- |
| MTZ | Quick, compact, small/medium MIPs | Large hard VRPs where relaxation strength matters |
| Single-commodity flow | Stronger static connectivity, optional visits | Memory is tight, or `n` is large |
| Multi-commodity flow | Very strong small routing models | Most practical benchmark tasks; too many variables |
| Static DFJ | Tiny instances, debugging | More than roughly 15-18 stations without careful filtering |
| Lazy/iterative DFJ cuts | Strong routing models with many possible SECs | Solver API/callback complexity is too risky |

## Decision heuristic

1. **Default to MTZ.** Fastest to write, lowest variable count, and adequate for small/medium instances. If the solver converges quickly and the objective looks correct, stop.
2. **Switch to single-commodity flow** if MTZ produces weak LP bounds or the solver stalls on instances where you know solutions exist. Pair with MTZ if you want both.
3. **Use static DFJ** only for n ≤ ~15 instances or as a correctness check against another method.
4. **Use lazy/iterative DFJ cuts** for hard, larger routing instances where MTZ is too weak and the solver's callback API is manageable.

## Pickup/dropoff specifics

For pickup/dropoff rebalancing (e.g., bike-sharing), start with MTZ or artificial connectivity flow. Do **not** rely on physical truck load as the only subtour-elimination mechanism — pickup/dropoff load can increase **and** decrease and does not prove route connectivity.

# Flight-Command Grammar

The parser recognizes exactly four command shapes. All four are
**case-insensitive** and tolerate variable whitespace around tokens, commas,
and the literal `m`.

| Mode      | Pattern (case-insensitive)                                                                 | Captured groups               |
| --------- | ------------------------------------------------------------------------------------------ | ----------------------------- |
| `takeoff` | `take off to <h> m height in <t> seconds`                                                  | `h`, `t`                      |
| `hover`   | `hover at <h> m height for <t> seconds`                                                    | `h`, `t`                      |
| `land`    | `land from <h> m height in <t> seconds`                                                    | `h`, `t`                      |
| `fly`     | `fly from (<x>,<y>,<z>) [location] to (<x'>,<y'>,<z'>) in <t> seconds`                     | `x,y,z,x',y',z',t`            |

Numeric tokens accept decimals (e.g., `2.5`) and, for the `fly` triples, a
leading minus sign (e.g., `-1.0`). The trailing `seconds`/`second` is matched
permissively. Whitespace around the commas in coordinate triples is optional.

## Per-mode position/time semantics

Tracked state in the parser: `_pos` (current position) and `_t` (current
clock). Each handler mutates these and pushes the **end** waypoint.

- `takeoff(h, t)` — ensure a start waypoint exists at current `_pos`; advance
  `_t += t`; set `_pos.z = h`; push end waypoint; append mode `'takeoff'`.
- `hover(h, t)` — set `_pos.z = h` first, then ensure start waypoint, then
  advance `_t += t`; push end waypoint; append `'hover'`. Snapping altitude
  *before* the start insertion means the segment is a true hover rather than
  an implicit climb on the very first command.
- `land(h, t)` — set `_pos.z = h`; ensure start waypoint; advance `_t += t`;
  set `_pos.z = 0`; push end waypoint; append `'land'`.
- `fly((x,y,z) → (x',y',z'), t)` — if no waypoints exist yet, push
  `(x,y,z)` as the seeded start (replacing the default `(0,0,0)` origin);
  advance `_t += t`; set `_pos = (x',y',z')`; push end waypoint; append
  `'fly'`.

## Output contract

For a plan of `N` commands the parser returns:

- `waypoints`: `numpy.ndarray` of shape `(4, n)` where `n = N + 1`. Rows are
  `[x, y, z, yaw]`. Yaw is always 0.0 — yaw is not addressed by the grammar.
- `waypoint_times`: `numpy.ndarray` of shape `(n,)` — strictly increasing,
  starting at 0.0.
- `modes`: `list[str]` of length `n - 1`. Each entry is one of
  `'takeoff' | 'hover' | 'fly' | 'land'`.

## Single-command worked examples

These mirror the shapes the drone simulator's command files use.

### Take off to 2.5 m height in 5 seconds

```
waypoints     : [[0,0],[0,0],[0,2.5],[0,0]]   # shape (4, 2)
waypoint_times: [0, 5]
modes         : ['takeoff']
```

### Hover at 3 m height for 12 seconds

```
waypoints     : [[0,0],[0,0],[3,3],[0,0]]     # shape (4, 2)
waypoint_times: [0, 12]
modes         : ['hover']
```

Note: the start waypoint's z is already 3 — `_pos.z = h` runs *before*
`_ensure_start`.

### Land from 1 m height in 1.5 seconds

```
waypoints     : [[0,0],[0,0],[1,0],[0,0]]     # shape (4, 2)
waypoint_times: [0, 1.5]
modes         : ['land']
```

### Fly from (0,0,1) to (-1,0,1) in 4 seconds

```
waypoints     : [[0,-1],[0,0],[1,1],[0,0]]    # shape (4, 2)
waypoint_times: [0, 4]
modes         : ['fly']
```

The default origin is *replaced* by the `from (0,0,1)` triple — note z=1 at
the start, not 0.

## Multi-command example

```
Take off to 2 m height in 3 seconds
Hover at 2 m height for 5 seconds
Land from 2 m height in 4 seconds
```

yields

```
waypoints     : [[0,0,0,0],[0,0,0,0],[0,2,2,0],[0,0,0,0]]   # shape (4, 4)
waypoint_times: [0, 3, 8, 12]
modes         : ['takeoff', 'hover', 'land']
```

## Anti-patterns / common mistakes

- Treating `Fly`'s start triple as a no-op when waypoints already exist.
  The handler always reads it but only *pushes* it when the list is empty.
  Mid-plan, the `from (...)` is informational; the active position is
  whatever the previous segment ended at.
- Forgetting that `Hover` snaps altitude before the implicit start insertion
  — a leading `Hover at 3 m for 5 seconds` starts at z=3, not z=0.
- Skipping `.strip()` / blank-line filtering when feeding multi-line input.
  The convenience `parse_flight_plan(str)` form handles both for you.
- Treating yaw as a degree of freedom. The grammar does not address yaw;
  the parser fills it with 0.0 throughout.

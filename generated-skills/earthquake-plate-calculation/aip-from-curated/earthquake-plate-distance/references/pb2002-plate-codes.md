# PB2002 plate codes (Bird 2003)

Two-letter `Code` values used in `PB2002_plates.json` (property `Code`) and
in `PB2002_boundaries.json` (properties `PlateA`, `PlateB`). The matching
long name lives under `PlateName` in the plates file.

Major plates most tasks ask about:

| Code | PlateName       |
|------|-----------------|
| PA   | Pacific         |
| NA   | North America   |
| SA   | South America   |
| EU   | Eurasia         |
| AF   | Africa          |
| AN   | Antarctica      |
| AU   | Australia       |
| IN   | India           |
| NZ   | Nazca           |
| CO   | Cocos           |
| CA   | Caribbean       |
| AR   | Arabia          |
| PH   | Philippine Sea  |
| JF   | Juan de Fuca    |
| SO   | Somalia         |
| SC   | Scotia          |

The file carries 54 plates in total. If the user names a smaller plate
not listed above, open `PB2002_plates.json` and grep its `features[*].properties`
for a `PlateName` match — the `Code` beside it is the key.

## Boundary filtering convention

A plate's boundaries are the lines with `PlateA == <Code>` OR
`PlateB == <Code>`. Boundary segments carry both neighbors in their
`Name` property as `AA-BB`, so a text match on `PA` would also match
`PAC`/`PAN`-style false positives — prefer the `PlateA`/`PlateB` fields.

# OpenPowerlifting data columns that affect scoring

Condensed from the OpenPowerlifting data README shipped next to the workbook (`data-readme.md`).

- **Name**: lifters sharing a name are suffixed `#1`, `#2` (e.g. `Jonathan Cruz #1`); keep the suffix.
- **Sex**: `M`, `F`, or `Mx` (gender-neutral; scored with men's constants).
- **Event**: `SBD` full power, `BD` push-pull, `SD`, `SB`, `S`, `B`, `D`. Only the lifts in the event exist; IPF GL is defined only for SBD and B.
- **Equipment**: `Raw` (bare knees/sleeves), `Wraps`, `Single-ply`, `Multi-ply`, `Unlimited`, `Straps`. It is the category allowed, not what was worn.
- **Age**: integer exact, or `n.5` meaning n or n+1. **AgeClass** / **BirthYearClass**: e.g. `40-44`, `40-49`.
- **BodyweightKg**: optional, two decimals. Blank = unknown, scores 0.
- **WeightClassKg**: text, `90` = up to 90 kg, `90+` = above 90 kg. Never use it as bodyweight.
- **Best3SquatKg / Best3BenchKg / Best3DeadliftKg**: best of the first three successful attempts. Rarely negative: the lowest weight attempted and failed.
- **TotalKg**: sum of the three bests if all succeeded; empty if a lift failed or the lifter was disqualified. Rarely present without lift data (old meets).
- **Place**: number, `G` guest (succeeded, not award eligible), `DQ`, `DD` doping DQ, `NS` no-show. Stored as text.
- **Tested**: `Yes` if drug-tested category. **Federation** / **ParentFederation** (e.g. USAPL -> IPF). **Date**: ISO `YYYY-MM-DD` text, meet start date. **Sanctioned**: `Yes`/`No`.

# Output format reference

Both files go in `/root/output/`. Create the directory if it doesn't exist.

## `unified_taxonomy_full.csv`

One row per input source path. Every input row from every source file ends up
here exactly once.

| Column            | Type    | Notes                                                          |
|-------------------|---------|----------------------------------------------------------------|
| `source`          | string  | `amazon`, `facebook`, or `google` (lowercase, no other values) |
| `category_path`   | string  | The original input path, verbatim (preserve casing/spacing)    |
| `depth`           | int     | 1–5; the depth of the original path (count segments split on `>`) |
| `unified_level_1` | string  | Always populated                                               |
| `unified_level_2` | string  | Populated when the unified path has ≥2 levels                  |
| `unified_level_3` | string  | Populated when the unified path has ≥3 levels                  |
| `unified_level_4` | string  | Populated when the unified path has ≥4 levels                  |
| `unified_level_5` | string  | Populated when the unified path has 5 levels                   |

Leave deeper-level cells **empty** (not `NaN`, not `"none"`) when the unified
path is shorter than 5.

### Example rows

```csv
source,category_path,depth,unified_level_1,unified_level_2,unified_level_3,unified_level_4,unified_level_5
amazon,"Electronics > Computers > Laptops",3,Electronics,Computers | Tablets,Laptops,,
facebook,"Apparel & Accessories > Clothing > Shirts > T-Shirts",4,Apparel,Clothing,Tops,T-Shirts,
google,"Home & Garden > Kitchen > Cookware > Pans > Non-Stick",5,Home | Garden,Kitchen,Cookware,Pans,Non-Stick
```

## `unified_taxonomy_hierarchy.csv`

One row per **unique unified path** (any depth). Same five `unified_level_*`
columns, empty cells for unused depths. No `source` or `category_path` here.

### Example rows

```csv
unified_level_1,unified_level_2,unified_level_3,unified_level_4,unified_level_5
Electronics,,,,
Electronics,Computers | Tablets,,,
Electronics,Computers | Tablets,Laptops,,
Apparel,Clothing,Tops,T-Shirts,
Home | Garden,Kitchen,Cookware,Pans,Non-Stick
```

The hierarchy file must include **every prefix** of every leaf path. If
`(A, B, C)` appears, so must `(A,)` and `(A, B)`.

## Name formatting (applies to every `unified_level_*` cell)

- ≤5 words.
- Multiple words joined with ` | ` (space-pipe-space). Single-word names need
  no separator.
- Title Case or the casing convention you pick — be consistent across the file.
- Never use commas inside a name (CSV-safe).
- Never duplicate a parent's words in a child (e.g., parent `Electronics`,
  child must not be `Electronics | Accessories` — use `Accessories` alone).

## Sanity invariants

- Every `unified_level_1` in `full.csv` appears as a `(level_1, , , , )` row in
  `hierarchy.csv`.
- No `unified_level_k` is populated when `unified_level_{k-1}` is empty.
- `source` distribution across distinct `unified_level_1` values should be
  roughly even — no single source should dominate (>70%) any top-level bucket
  unless that bucket is small (<3% of total rows).

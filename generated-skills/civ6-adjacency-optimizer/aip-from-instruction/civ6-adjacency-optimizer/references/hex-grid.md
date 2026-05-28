# Civ6 Hex Grid

Civ6 uses an **offset hex grid** with pointy-top hexes. Coordinates are
`(x, y)`. Each row is offset; odd rows shift right (the "odd-r" layout),
which is the most common Civ6 convention.

## Neighbors

For tile `(x, y)`, the six neighbors are:

```python
def hex_neighbors(x, y):
    if y % 2 == 0:                       # even row
        return [(x-1, y),   (x+1, y),    # W,  E
                (x-1, y+1), (x,   y+1),  # NW, NE
                (x-1, y-1), (x,   y-1)]  # SW, SE
    else:                                # odd row
        return [(x-1, y),   (x+1, y),    # W,  E
                (x,   y+1), (x+1, y+1),  # NW, NE
                (x,   y-1), (x+1, y-1)]  # SW, SE
```

**Verify this against the map data first.** If the .Civ6Map file uses
"odd-q" or "even-r" instead, swap the rule. To verify: pick two tiles
the game considers adjacent (rivers between them, or visible
"adjacent_to" data) and confirm one is in the other's neighbor list.

## Distance

Hex distance between `(x1,y1)` and `(x2,y2)` (odd-r offset → axial):

```python
def offset_to_axial(x, y):              # odd-r
    q = x - (y - (y & 1)) // 2
    r = y
    return q, r

def hex_distance(a, b):
    aq, ar = offset_to_axial(*a)
    bq, br = offset_to_axial(*b)
    return (abs(aq - bq) + abs(ar - br) + abs(aq + ar - bq - br)) // 2
```

Districts must satisfy `hex_distance(district, city_center) <= 3`.
City centers must be `>= 4` apart from each other.

## Bounds and wrap-around

Civ6 maps can be cylinder-wrapping in the x direction. Check the map's
`Wrap_X` flag (in the .Civ6Map MapAttributes table) before computing
neighbors near the east/west edges. If wrap is enabled:

```python
def wrap_x(x, width):
    return x % width
```

Y direction does not wrap.

## Common pitfalls

- Mixing even-row and odd-row offset rules → "near edge" tiles look
  un-adjacent. Always run the verification test above.
- Off-by-one on distance: max district range is `<= 3` inclusive.
- Ignoring x-wrap on world maps → missed adjacencies, undercounted bonus.

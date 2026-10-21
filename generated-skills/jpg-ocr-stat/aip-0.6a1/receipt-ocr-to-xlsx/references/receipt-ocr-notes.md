# Receipt OCR notes

## Misreads seen on scanned Malaysian receipts (Tesseract 5)

| Printed | OCR read | Effect |
|---|---|---|
| `10 00` (thermal print, no point) | `1000`, `100¢`, `10:00` | total off by 100x, or missing |
| `RM` | `RN`, `Ri`, `ARM`, `FN` | `TOTAL RM` keyword missed |
| `Total` | `Tota!`, `Tolal`, `TOTAI`, `Het Total` (Net) | keyword missed |
| `17.70` | `17.76`; `0` read as `6`/`8`/`9` | wrong cents |
| `19/02/2018` | `19/62/2018`, `14/62/2018` | invalid month |
| `26/02/18` | `38/02/18`, `30/02/18` | invalid or wrong day |
| `102.00` | `702.00`, `402.00`, `S702.` | leading digit wrong on faint print |
| `Incl` | `Inc]`, `[nc]`, `inal` | inclusive-GST line looks excluded |
| `Date:` | `Data:`, `bate:`, `Dat` | label missed |

Cross-checks that settle most disagreements: the total equals payment minus change, it
repeats on the next lines (Total, Visa/Cash, Total Gross on Shell fuel slips), and it is
subtotal + GST + service charge + rounding.

## Targeted re-OCR when you cannot view an image

```python
import pytesseract
from PIL import Image, ImageOps

img = ImageOps.grayscale(Image.open(path))
w, h = img.size
part = img.crop((0, int(h * 0.4), w, h))          # totals: lower part; date: (0, 0, w, h*0.4)
part = ImageOps.autocontrast(part.resize((part.width * 3, part.height * 3), Image.LANCZOS))
for psm in (4, 6, 11):
    print(psm, pytesseract.image_to_string(part, config=f"--psm {psm}"))
```

Other variants worth one try on faint or dark scans: binarize
`part.point(lambda p: 255 if p > 128 else 0)` (also try 100 and 150),
`ImageOps.invert` for light text on dark backgrounds, `ImageFilter.SHARPEN`.

PSM modes: 3 automatic (default), 4 single column of variable-size text (best for
receipts), 6 uniform block, 11 sparse text (finds stray amounts in a right-hand column),
7 single line, 13 raw line.

`pytesseract.get_tesseract_version()` raises `TesseractNotFoundError` when the
`tesseract` binary is not on PATH.

## Limits

Handwriting (pen notes on the scan) is not read reliably; ignore it. Heavily faded
thermal print, blur and skew reduce accuracy; when the value is not legible even on the
image, leave it null rather than guessing.

# Re-OCR one stubborn image (Tesseract via pytesseract)

Load this only when `scripts/receipts.py extract` gives nothing usable for an image and you want
more OCR text, e.g. you cannot view images, or you want text to confirm what you see.

## Quick snippet

```python
import pytesseract
from PIL import Image, ImageOps, ImageFilter

img = Image.open(path)
gray = ImageOps.autocontrast(ImageOps.grayscale(img))
variants = {
    "gray": gray,
    "inverted": ImageOps.invert(gray),                   # light text on a dark background
    "up2x": gray.resize((gray.width * 2, gray.height * 2), Image.LANCZOS),  # small or faded print
    "sharp": gray.filter(ImageFilter.SHARPEN),
    "bin128": gray.point(lambda p: 255 if p > 128 else 0),  # also try thresholds of 100 and 160
}
for name, v in variants.items():
    for psm in ("--psm 6", "--psm 4", "--psm 11"):
        print(name, psm, pytesseract.image_to_string(v, config=psm, lang="eng"))
```

Crop to the totals block first (`img.crop((left, top, right, bottom))`) and use `--psm 6`, or
`--psm 7` for a single line. This often recovers large-font `TOTAL:` lines that full-page OCR drops.

## Page segmentation modes

- `0`: orientation and script detection only
- `3`: fully automatic (default)
- `4`: one column of text in varying sizes (good for receipts)
- `6`: one uniform block of text
- `7`: a single line of text
- `11`: sparse text, finds as much as possible
- `13`: raw line

Other languages: `lang='eng+fra'` (only if that traineddata is installed).

## Confidence

```python
d = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
confs = [c for c in d["conf"] if float(c) > 0]
avg = sum(map(float, confs)) / len(confs) if confs else 0   # >=80 high, >=50 medium, else low
```

Each entry also carries `block_num`, `line_num`, `left`, `top`, `width`, and `height`. Use these to find
where a keyword sits so you can crop beside it.

## Failure modes

- `pytesseract.TesseractNotFoundError`: the `tesseract` binary is not on PATH (apt `tesseract-ocr`).
- Empty or garbage output: try another PSM, the inverted or upscaled variant, and check that the file is a real image.
- Tesseract handles handwriting, decorative fonts, heavy blur, watermarks, and rotated text poorly.
  Correct EXIF rotation with `ImageOps.exif_transpose(img)`. Aim for roughly 300 DPI equivalent.

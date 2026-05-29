# PDF Processing Advanced Reference

Advanced PDF features, additional libraries, performance, and troubleshooting.
Load only when general operations and form filling don't already cover the need.

## pypdfium2 (Apache/BSD License)

Python binding for PDFium (Chromium's PDF library). Fast rendering and image
generation. Drop-in replacement for PyMuPDF for many tasks.

### Render PDF to Images
```python
import pypdfium2 as pdfium

pdf = pdfium.PdfDocument("document.pdf")

page = pdf[0]
bitmap = page.render(scale=2.0, rotation=0)
img = bitmap.to_pil()
img.save("page_1.png", "PNG")

for i, page in enumerate(pdf):
    bitmap = page.render(scale=1.5)
    img = bitmap.to_pil()
    img.save(f"page_{i+1}.jpg", "JPEG", quality=90)
```

### Extract Text
```python
import pypdfium2 as pdfium

pdf = pdfium.PdfDocument("document.pdf")
for i, page in enumerate(pdf):
    text = page.get_text()
    print(f"Page {i+1} text length: {len(text)} chars")
```

## JavaScript Libraries

### pdf-lib (MIT)

#### Load and Manipulate Existing PDF
```javascript
import { PDFDocument } from 'pdf-lib';
import fs from 'fs';

async function manipulatePDF() {
    const existingPdfBytes = fs.readFileSync('input.pdf');
    const pdfDoc = await PDFDocument.load(existingPdfBytes);

    const pageCount = pdfDoc.getPageCount();
    console.log(`Document has ${pageCount} pages`);

    const newPage = pdfDoc.addPage([600, 400]);
    newPage.drawText('Added by pdf-lib', { x: 100, y: 300, size: 16 });

    const pdfBytes = await pdfDoc.save();
    fs.writeFileSync('modified.pdf', pdfBytes);
}
```

#### Create Complex PDFs from Scratch
```javascript
import { PDFDocument, rgb, StandardFonts } from 'pdf-lib';
import fs from 'fs';

async function createPDF() {
    const pdfDoc = await PDFDocument.create();
    const helveticaFont = await pdfDoc.embedFont(StandardFonts.Helvetica);
    const helveticaBold = await pdfDoc.embedFont(StandardFonts.HelveticaBold);

    const page = pdfDoc.addPage([595, 842]); // A4
    const { width, height } = page.getSize();

    page.drawText('Invoice #12345', {
        x: 50, y: height - 50, size: 18,
        font: helveticaBold,
        color: rgb(0.2, 0.2, 0.8),
    });

    page.drawRectangle({
        x: 40, y: height - 100, width: width - 80, height: 30,
        color: rgb(0.9, 0.9, 0.9),
    });

    const items = [
        ['Item', 'Qty', 'Price', 'Total'],
        ['Widget', '2', '$50', '$100'],
        ['Gadget', '1', '$75', '$75'],
    ];

    let yPos = height - 150;
    items.forEach(row => {
        let xPos = 50;
        row.forEach(cell => {
            page.drawText(cell, { x: xPos, y: yPos, size: 12, font: helveticaFont });
            xPos += 120;
        });
        yPos -= 25;
    });

    const pdfBytes = await pdfDoc.save();
    fs.writeFileSync('created.pdf', pdfBytes);
}
```

#### Merge and Split
```javascript
import { PDFDocument } from 'pdf-lib';
import fs from 'fs';

async function mergePDFs() {
    const mergedPdf = await PDFDocument.create();

    const pdf1 = await PDFDocument.load(fs.readFileSync('doc1.pdf'));
    const pdf2 = await PDFDocument.load(fs.readFileSync('doc2.pdf'));

    const pdf1Pages = await mergedPdf.copyPages(pdf1, pdf1.getPageIndices());
    pdf1Pages.forEach(p => mergedPdf.addPage(p));

    const pdf2Pages = await mergedPdf.copyPages(pdf2, [0, 2, 4]);
    pdf2Pages.forEach(p => mergedPdf.addPage(p));

    fs.writeFileSync('merged.pdf', await mergedPdf.save());
}
```

### pdfjs-dist (Apache)

Mozilla's PDF.js — render and parse PDFs in browser/Node.

#### Basic Rendering
```javascript
import * as pdfjsLib from 'pdfjs-dist';
pdfjsLib.GlobalWorkerOptions.workerSrc = './pdf.worker.js';

async function renderPDF() {
    const loadingTask = pdfjsLib.getDocument('document.pdf');
    const pdf = await loadingTask.promise;
    const page = await pdf.getPage(1);
    const viewport = page.getViewport({ scale: 1.5 });

    const canvas = document.createElement('canvas');
    const context = canvas.getContext('2d');
    canvas.height = viewport.height;
    canvas.width = viewport.width;

    await page.render({ canvasContext: context, viewport }).promise;
    document.body.appendChild(canvas);
}
```

#### Extract Text with Coordinates
```javascript
async function extractText() {
    const loadingTask = pdfjsLib.getDocument('document.pdf');
    const pdf = await loadingTask.promise;
    let fullText = '';
    for (let i = 1; i <= pdf.numPages; i++) {
        const page = await pdf.getPage(i);
        const textContent = await page.getTextContent();
        const pageText = textContent.items.map(it => it.str).join(' ');
        fullText += `\n--- Page ${i} ---\n${pageText}`;
        const textWithCoords = textContent.items.map(it => ({
            text: it.str, x: it.transform[4], y: it.transform[5],
            width: it.width, height: it.height,
        }));
    }
    return fullText;
}
```

#### Extract Annotations and Forms
```javascript
async function extractAnnotations() {
    const loadingTask = pdfjsLib.getDocument('annotated.pdf');
    const pdf = await loadingTask.promise;
    for (let i = 1; i <= pdf.numPages; i++) {
        const page = await pdf.getPage(i);
        const annotations = await page.getAnnotations();
        annotations.forEach(a => {
            console.log(a.subtype, a.contents, a.rect);
        });
    }
}
```

## Advanced CLI

### poppler-utils

```bash
# Text with bounding box coordinates
pdftotext -bbox-layout document.pdf output.xml

# PNG / JPEG with explicit DPI
pdftoppm -png -r 300 document.pdf output_prefix
pdftoppm -png -r 600 -f 1 -l 3 document.pdf high_res_pages
pdftoppm -jpeg -jpegopt quality=85 -r 200 document.pdf jpeg_output

# Image extraction
pdfimages -j -p document.pdf page_images
pdfimages -list document.pdf
pdfimages -all document.pdf images/img
```

### qpdf

```bash
# Splitting and complex page ranges
qpdf --split-pages=3 input.pdf output_group_%02d.pdf
qpdf input.pdf --pages input.pdf 1,3-5,8,10-end -- extracted.pdf
qpdf --empty --pages doc1.pdf 1-3 doc2.pdf 5-7 doc3.pdf 2,4 -- combined.pdf

# Optimization and repair
qpdf --linearize input.pdf optimized.pdf
qpdf --optimize-level=all input.pdf compressed.pdf
qpdf --check input.pdf
qpdf --fix-qdf damaged.pdf repaired.pdf
qpdf --show-all-pages input.pdf > structure.txt

# Encryption
qpdf --encrypt user_pass owner_pass 256 --print=none --modify=none -- input.pdf encrypted.pdf
qpdf --show-encryption encrypted.pdf
qpdf --password=secret123 --decrypt encrypted.pdf decrypted.pdf
```

## Advanced Python

### pdfplumber

#### Text with Coordinates
```python
import pdfplumber

with pdfplumber.open("document.pdf") as pdf:
    page = pdf.pages[0]
    chars = page.chars
    for char in chars[:10]:
        print(f"Char: '{char['text']}' at x:{char['x0']:.1f} y:{char['y0']:.1f}")

    bbox_text = page.within_bbox((100, 100, 400, 200)).extract_text()
```

#### Custom Table Extraction
```python
import pdfplumber

with pdfplumber.open("complex_table.pdf") as pdf:
    page = pdf.pages[0]
    table_settings = {
        "vertical_strategy": "lines",
        "horizontal_strategy": "lines",
        "snap_tolerance": 3,
        "intersection_tolerance": 15,
    }
    tables = page.extract_tables(table_settings)

    img = page.to_image(resolution=150)
    img.save("debug_layout.png")
```

### reportlab — Professional Reports

```python
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors

data = [
    ['Product', 'Q1', 'Q2', 'Q3', 'Q4'],
    ['Widgets', '120', '135', '142', '158'],
    ['Gadgets', '85', '92', '98', '105'],
]

doc = SimpleDocTemplate("report.pdf")
elements = []
styles = getSampleStyleSheet()
elements.append(Paragraph("Quarterly Sales Report", styles['Title']))

table = Table(data)
table.setStyle(TableStyle([
    ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
    ('FONTSIZE', (0, 0), (-1, 0), 14),
    ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
    ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
    ('GRID', (0, 0), (-1, -1), 1, colors.black),
]))
elements.append(table)

doc.build(elements)
```

## Complex Workflows

### Extract Figures / Images
```bash
pdfimages -all document.pdf images/img
```

```python
import pypdfium2 as pdfium
from PIL import Image
import numpy as np

def extract_figures(pdf_path, output_dir):
    pdf = pdfium.PdfDocument(pdf_path)
    for page_num, page in enumerate(pdf):
        bitmap = page.render(scale=3.0)
        img = bitmap.to_pil()
        img_array = np.array(img)
        mask = np.any(img_array != [255, 255, 255], axis=2)
        # contour detection / saving omitted for brevity
```

### Batch Processing with Error Handling
```python
import os, glob, logging
from pypdf import PdfReader, PdfWriter

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def batch_process_pdfs(input_dir, operation='merge'):
    pdf_files = glob.glob(os.path.join(input_dir, "*.pdf"))

    if operation == 'merge':
        writer = PdfWriter()
        for pdf_file in pdf_files:
            try:
                reader = PdfReader(pdf_file)
                for page in reader.pages:
                    writer.add_page(page)
                logger.info(f"Processed: {pdf_file}")
            except Exception as e:
                logger.error(f"Failed to process {pdf_file}: {e}")
                continue
        with open("batch_merged.pdf", "wb") as output:
            writer.write(output)

    elif operation == 'extract_text':
        for pdf_file in pdf_files:
            try:
                reader = PdfReader(pdf_file)
                text = "".join(page.extract_text() for page in reader.pages)
                output_file = pdf_file.replace('.pdf', '.txt')
                with open(output_file, 'w', encoding='utf-8') as f:
                    f.write(text)
                logger.info(f"Extracted text from: {pdf_file}")
            except Exception as e:
                logger.error(f"Failed to extract text from {pdf_file}: {e}")
                continue
```

### Cropping
```python
from pypdf import PdfWriter, PdfReader

reader = PdfReader("input.pdf")
writer = PdfWriter()
page = reader.pages[0]
page.mediabox.left = 50
page.mediabox.bottom = 50
page.mediabox.right = 550
page.mediabox.top = 750
writer.add_page(page)
with open("cropped.pdf", "wb") as output:
    writer.write(output)
```

## Performance Tips

1. **Large PDFs** — stream rather than load whole; use `qpdf --split-pages`; process pages one at a time with pypdfium2.
2. **Text extraction** — `pdftotext -bbox-layout` is fastest for plain text; pdfplumber for tables; avoid pypdf for large docs.
3. **Image extraction** — `pdfimages` beats rendering pages.
4. **Form filling** — use this skill's structured workflow; pre-validate field IDs and values.
5. **Memory** — chunked processing:
   ```python
   def process_large_pdf(pdf_path, chunk_size=10):
       reader = PdfReader(pdf_path)
       total_pages = len(reader.pages)
       for start_idx in range(0, total_pages, chunk_size):
           end_idx = min(start_idx + chunk_size, total_pages)
           writer = PdfWriter()
           for i in range(start_idx, end_idx):
               writer.add_page(reader.pages[i])
           with open(f"chunk_{start_idx//chunk_size}.pdf", "wb") as output:
               writer.write(output)
   ```

## Troubleshooting

### Encrypted PDFs
```python
from pypdf import PdfReader
try:
    reader = PdfReader("encrypted.pdf")
    if reader.is_encrypted:
        reader.decrypt("password")
except Exception as e:
    print(f"Failed to decrypt: {e}")
```

### Corrupted PDFs
```bash
qpdf --check corrupted.pdf
qpdf --replace-input corrupted.pdf
```

### Text Extraction Issues (OCR fallback)
```python
import pytesseract
from pdf2image import convert_from_path

def extract_text_with_ocr(pdf_path):
    images = convert_from_path(pdf_path)
    text = ""
    for image in images:
        text += pytesseract.image_to_string(image)
    return text
```

## Licenses

- pypdf — BSD
- pdfplumber — MIT
- pypdfium2 — Apache/BSD
- reportlab — BSD
- poppler-utils — GPL-2
- qpdf — Apache
- pdf-lib — MIT
- pdfjs-dist — Apache

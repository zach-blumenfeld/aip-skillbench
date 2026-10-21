"""Step `render-pages` (non-fillable forms): render each page to PNG with poppler's
pdftoppm (replaces the pdf skill's pdf2image-based convert_pdf_to_images.py; pdf2image
is not installed in the container), longest side scaled to 1000 px.

stdin state: form_pdf_path, output_pdf_path (page images go to <output stem>_pages/).
stdout: {"page_images": [{page_number, image_path, image_width, image_height,
                          pdf_width, pdf_height}]}
"""
import glob
import os
import re
import subprocess

from PIL import Image

from pdf_form_lib import emit, fail, open_reader, read_stdin


def main():
    st = read_stdin().get("state", {})
    pdf = st["form_pdf_path"]
    out_dir = os.path.splitext(os.path.abspath(st["output_pdf_path"]))[0] + "_pages"
    os.makedirs(out_dir, exist_ok=True)
    reader = open_reader(pdf)
    prefix = os.path.join(out_dir, "page")
    r = subprocess.run(["pdftoppm", "-png", "-scale-to", "1000", pdf, prefix], capture_output=True, text=True)
    if r.returncode != 0:
        fail(f"pdftoppm failed: {r.stderr.strip()}")
    pages = []
    for path in sorted(glob.glob(prefix + "-*.png"), key=lambda p: int(re.findall(r"-(\d+)\.png$", p)[0])):
        n = int(re.findall(r"-(\d+)\.png$", path)[0])
        with Image.open(path) as im:
            w, h = im.size
        box = reader.pages[n - 1].mediabox
        pages.append({"page_number": n, "image_path": path, "image_width": w, "image_height": h,
                      "pdf_width": float(box.width), "pdf_height": float(box.height)})
    emit({"page_images": pages})


if __name__ == "__main__":
    main()

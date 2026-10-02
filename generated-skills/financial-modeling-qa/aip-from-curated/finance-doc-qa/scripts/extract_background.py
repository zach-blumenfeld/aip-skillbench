#!/usr/bin/env python3
import json
import sys
from pathlib import Path


def main() -> None:
    payload = json.load(sys.stdin)
    state = payload.get("currentState", {})
    path = Path(state["background_path"])
    if not path.exists():
        raise FileNotFoundError(f"background_path not found: {path}")

    from pypdf import PdfReader

    reader = PdfReader(str(path))
    pages = []
    for i, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception as exc:
            text = f"[pypdf extraction error on page {i}: {exc}]"
        pages.append(f"--- Page {i} ---\n{text.strip()}")

    background_text = "\n\n".join(pages).strip()
    if not background_text:
        background_text = "[no extractable text in background PDF]"

    json.dump({"background_text": background_text}, sys.stdout)


if __name__ == "__main__":
    main()

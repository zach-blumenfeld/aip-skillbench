#!/usr/bin/env python3
"""Pick the canonical final/latest artifact among several versions.

Usage:
    python select_version.py '<json_list_of_doc_objects>'

Each input object should have at least `id` and `date`; `document_link` is
also inspected for the version marker.

Precedence (Step 3 of the procedure):
  1. Explicit `latest` marker in `id` or `document_link` (case-insensitive)
  2. Explicit `final` marker in `id` or `document_link`
  3. Most recent `date` (ISO-8601 lexicographic comparison)
  4. Otherwise the first item in the input order

Prints the selected object plus a `_selection_reason` field explaining
the tier that triggered selection.
"""
import json
import sys


def has_marker(doc, marker):
    s = " ".join(filter(None, [
        str(doc.get("id") or ""),
        str(doc.get("document_link") or ""),
        str(doc.get("title") or ""),
    ])).lower()
    return marker in s


def main(payload):
    docs = json.loads(payload)
    if not docs:
        print(json.dumps({"selected": None,
                          "_selection_reason": "empty input"}))
        return

    latest = [d for d in docs if has_marker(d, "latest")]
    if latest:
        latest.sort(key=lambda d: d.get("date") or "", reverse=True)
        out = dict(latest[0])
        out["_selection_reason"] = "explicit 'latest' marker"
        print(json.dumps(out, indent=2))
        return

    final = [d for d in docs if has_marker(d, "final")]
    if final:
        final.sort(key=lambda d: d.get("date") or "", reverse=True)
        out = dict(final[0])
        out["_selection_reason"] = "explicit 'final' marker"
        print(json.dumps(out, indent=2))
        return

    dated = [d for d in docs if d.get("date")]
    if dated:
        dated.sort(key=lambda d: d["date"], reverse=True)
        out = dict(dated[0])
        out["_selection_reason"] = "most recent date"
        print(json.dumps(out, indent=2))
        return

    out = dict(docs[0])
    out["_selection_reason"] = "first in input (no markers, no dates)"
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: select_version.py '<json_list>'", file=sys.stderr)
        sys.exit(2)
    main(sys.argv[1])

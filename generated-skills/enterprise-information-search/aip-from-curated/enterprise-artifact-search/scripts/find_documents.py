#!/usr/bin/env python3
"""Filter documents in a product file by `type` (case-insensitive substring).

Usage:
    python find_documents.py <product_file.json> "<type_substring>"

Example:
    python find_documents.py CoachForce.json "Market Research Report"

Prints a JSON list of matching docs with id, type, link, author, date, and
flags indicating whether explicit reviewer/feedback fields are present.
"""
import json
import sys


def main(path, query):
    with open(path) as f:
        data = json.load(f)

    q = query.lower()
    matches = []
    for d in data.get("documents", []):
        type_val = (d.get("type") or "").lower()
        title_val = (d.get("title") or "").lower()
        if q in type_val or q in title_val:
            matches.append({
                "id": d.get("id"),
                "type": d.get("type"),
                "title": d.get("title"),
                "document_link": d.get("document_link"),
                "author": d.get("author"),
                "authors": d.get("authors"),
                "created_by": d.get("created_by"),
                "owner": d.get("owner"),
                "date": d.get("date"),
                "reviewers": d.get("reviewers"),
                "key_reviewers": d.get("key_reviewers"),
                "approvers": d.get("approvers"),
                "requested_reviewers": d.get("requested_reviewers"),
                "feedback": d.get("feedback"),
            })

    print(json.dumps(matches, indent=2))


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print('usage: find_documents.py <product_file.json> "<type_substring>"',
              file=sys.stderr)
        sys.exit(2)
    main(sys.argv[1], sys.argv[2])

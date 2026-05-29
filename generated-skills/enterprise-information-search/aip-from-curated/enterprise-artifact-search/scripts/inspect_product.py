#!/usr/bin/env python3
"""Summarize a product artifact file without dumping its full contents.

Usage:
    python inspect_product.py <product_file.json>

Prints a JSON object with:
- channels: unique slack channel names
- documents: id + type + document_link (truncated)
- meeting_transcripts: id + document_type + participant count
- meeting_chats: id + first 80 chars of text
- urls: id + link + first 80 chars of description
- prs: id + title + author + reviewer logins

Keeps the agent context lean — the full file can be 1M+ tokens.
"""
import json
import sys


def truncate(s, n=120):
    if not isinstance(s, str):
        return s
    return s if len(s) <= n else s[:n] + "..."


def main(path):
    with open(path) as f:
        data = json.load(f)

    channels = sorted({
        s.get("Channel", {}).get("name", "")
        for s in data.get("slack", [])
        if s.get("Channel", {}).get("name")
    })

    docs = [
        {
            "id": d.get("id"),
            "type": d.get("type"),
            "document_link": d.get("document_link"),
            "author": d.get("author"),
            "date": d.get("date"),
            "has_feedback": bool(d.get("feedback")),
            "has_reviewers": bool(d.get("reviewers") or d.get("key_reviewers") or d.get("approvers")),
        }
        for d in data.get("documents", [])
    ]

    transcripts = [
        {
            "id": m.get("id"),
            "document_type": m.get("document_type"),
            "date": m.get("date"),
            "participants_count": len(m.get("participants", []) or []),
        }
        for m in data.get("meeting_transcripts", [])
    ]

    chats = [
        {"id": m.get("id"), "text_preview": truncate(m.get("text", ""), 80)}
        for m in data.get("meeting_chats", [])
    ]

    urls = [
        {
            "id": u.get("id"),
            "link": u.get("link"),
            "description_preview": truncate(u.get("description", ""), 120),
        }
        for u in data.get("urls", [])
    ]

    prs = [
        {
            "id": p.get("id"),
            "title": truncate(p.get("title", ""), 100),
            "author": (p.get("user") or {}).get("login"),
            "reviewer_logins": [
                (r.get("user") or {}).get("login")
                for r in (p.get("reviews") or [])
            ],
            "state": p.get("state"),
            "merged": p.get("merged"),
        }
        for p in data.get("prs", [])
    ]

    out = {
        "source_file": path,
        "channels": channels,
        "documents": docs,
        "meeting_transcripts": transcripts,
        "meeting_chats": chats,
        "urls": urls,
        "prs": prs,
        "counts": {
            "slack_messages": len(data.get("slack", [])),
            "documents": len(docs),
            "meeting_transcripts": len(transcripts),
            "meeting_chats": len(chats),
            "urls": len(urls),
            "prs": len(prs),
        },
    }
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: inspect_product.py <product_file.json>", file=sys.stderr)
        sys.exit(2)
    main(sys.argv[1])

#!/usr/bin/env python3
"""Search slack messages by keyword(s) with an optional channel filter.

Usage:
    python search_slack_text.py <product_file.json> '<json_list_of_keywords>' [channel_substring]

Returns top-level slack messages whose text contains ANY of the keywords
(case-insensitive). If `channel_substring` is provided, also restricts to
channels whose name contains it.

Each result includes channel, user_id, timestamp, text, message_id, and the
list of `urls_in_text` extracted from `<url|label>` slack mark-up and bare
http(s) links — useful for "demo URL" style questions.
"""
import json
import re
import sys


# Slack-style <url|label> and bare URLs.
SLACK_URL = re.compile(r"<((?:https?://|/)[^>|]+)(?:\|[^>]*)?>")
BARE_URL = re.compile(r"https?://[^\s<>|)\]]+")


def extract_urls(text):
    if not text:
        return []
    urls = []
    for m in SLACK_URL.finditer(text):
        urls.append(m.group(1))
    for m in BARE_URL.finditer(text):
        if m.group(0) not in urls:
            urls.append(m.group(0))
    return urls


def main(path, keywords_payload, channel_filter):
    with open(path) as f:
        data = json.load(f)
    keywords = [k.lower() for k in json.loads(keywords_payload) if k]
    cf = (channel_filter or "").lower()
    out = []
    for msg in data.get("slack", []):
        ch = (msg.get("Channel") or {}).get("name") or ""
        if cf and cf not in ch.lower():
            continue
        body = msg.get("Message", {}) or {}
        user = body.get("User", {}) or {}
        text = user.get("text") or ""
        tl = text.lower()
        if not any(k in tl for k in keywords):
            continue
        out.append({
            "channel": ch,
            "user_id": user.get("userId"),
            "timestamp": user.get("timestamp"),
            "text": text,
            "message_id": msg.get("id") or user.get("utteranceID"),
            "urls_in_text": extract_urls(text),
        })
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    if len(sys.argv) not in (3, 4):
        print("usage: search_slack_text.py <product_file.json> '<json_keywords>' [channel_substring]",
              file=sys.stderr)
        sys.exit(2)
    main(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) == 4 else "")

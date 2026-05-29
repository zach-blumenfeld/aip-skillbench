#!/usr/bin/env python3
"""Find slack messages and follow-up replies tied to a document link or id.

Usage:
    python slack_replies_to_doc.py <product_file.json> <doc_id_or_link_substring> [follow_up_hours]

Walks the `slack` array. For every top-level message whose text contains the
substring (case-insensitive), returns:
- the "share" message (channel, user, timestamp, message id)
- threaded replies under `ThreadReplies` (if any)
- inline follow-ups: the next messages in the SAME channel within
  `follow_up_hours` (default 24h) of the share — many datasets omit
  `ThreadReplies` and instead model replies as subsequent channel messages.

Use for Step 5 Tier 3 (slack-thread reviewers): the agent inspects the
returned replies for substantive feedback (questions, suggestions, edits)
vs. pure acknowledgements ("looks good", "thanks").
"""
import json
import sys
from datetime import datetime, timedelta


def parse_ts(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", ""))
    except Exception:
        return None


def main(path, needle, follow_up_hours):
    with open(path) as f:
        data = json.load(f)

    n = needle.lower()
    window = timedelta(hours=float(follow_up_hours))
    slack = data.get("slack", [])

    # Index messages by channel for inline follow-up scanning.
    by_channel = {}
    for i, msg in enumerate(slack):
        ch = (msg.get("Channel") or {}).get("name") or ""
        by_channel.setdefault(ch, []).append((i, msg))

    matches = []
    for msg in slack:
        body = msg.get("Message", {}) or {}
        user = body.get("User", {}) or {}
        text = (user.get("text") or "")
        if n not in text.lower():
            continue
        ch_name = (msg.get("Channel") or {}).get("name")
        share_ts = parse_ts(user.get("timestamp"))
        share = {
            "channel": ch_name,
            "channel_id": (msg.get("Channel") or {}).get("channelID"),
            "share_user_id": user.get("userId"),
            "share_text": text,
            "share_timestamp": user.get("timestamp"),
            "share_message_id": msg.get("id") or user.get("utteranceID"),
        }
        author = share["share_user_id"]

        thread_replies = []
        for r in msg.get("ThreadReplies") or []:
            ru = (r.get("User") or (r.get("Message") or {}).get("User") or {})
            thread_replies.append({
                "user_id": ru.get("userId"),
                "text": ru.get("text"),
                "timestamp": ru.get("timestamp"),
                "is_share_author": ru.get("userId") == author,
            })

        inline_followups = []
        if share_ts is not None and ch_name in by_channel:
            for _, other in by_channel[ch_name]:
                ob = other.get("Message", {}) or {}
                ou = ob.get("User", {}) or {}
                ots = parse_ts(ou.get("timestamp"))
                if ots is None or ots <= share_ts:
                    continue
                if ots - share_ts > window:
                    continue
                otext = ou.get("text") or ""
                # Skip later "share" messages of the same doc (e.g., a new
                # version posted by the author later that day).
                if n in otext.lower() and ou.get("userId") == author:
                    continue
                inline_followups.append({
                    "user_id": ou.get("userId"),
                    "text": otext,
                    "timestamp": ou.get("timestamp"),
                    "is_share_author": ou.get("userId") == author,
                    "message_id": other.get("id") or ou.get("utteranceID"),
                })

        matches.append({
            "share": share,
            "thread_replies": thread_replies,
            "inline_followups": inline_followups,
        })

    print(json.dumps(matches, indent=2))


if __name__ == "__main__":
    if len(sys.argv) not in (3, 4):
        print("usage: slack_replies_to_doc.py <product_file.json> <needle> [follow_up_hours=24]",
              file=sys.stderr)
        sys.exit(2)
    hours = sys.argv[3] if len(sys.argv) == 4 else "24"
    main(sys.argv[1], sys.argv[2], hours)

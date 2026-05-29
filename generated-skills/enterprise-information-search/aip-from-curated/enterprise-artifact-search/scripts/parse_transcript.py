#!/usr/bin/env python3
"""Parse a meeting transcript into per-speaker turns with eid mapping.

Usage:
    python parse_transcript.py <product_file.json> <meeting_id>

The dataset's transcripts follow this convention:
    Attendees
    <Name1>, <Name2>, ...
    Transcript
    <Speaker>: <text>
    <Speaker>: <text>
    ...

The `participants` list (employee IDs) is in the SAME ORDER as the Attendees
line, so name -> eid is a position-based mapping. Confirmed empirically on
this dataset; the agent should still sanity-check via the employee directory
when uncertain.

Output JSON:
{
  "meeting_id": "...",
  "document_type": "...",
  "date": "...",
  "name_to_eid": {"<Name>": "eid_..."},
  "turns": [{"name": "...", "eid": "eid_...|null", "text": "..."}],
  "speakers_with_turns": ["<Name>", ...],
  "speakers_eids": ["eid_...", ...]   # eids of all speakers that had >=1 turn
}

The agent decides which turns are "substantive feedback" vs. acknowledgement
(Step 5 Tier 2). This script does NOT classify substantivity — that's
judgment.
"""
import json
import re
import sys


SPEAKER_LINE = re.compile(r"^([A-Z][A-Za-z .'-]+):\s*(.*)$")


def parse(transcript: str):
    lines = transcript.splitlines()
    names = []
    turns = []
    in_transcript = False
    in_attendees = False
    for ln in lines:
        s = ln.strip()
        if not s:
            continue
        if s.lower() == "attendees":
            in_attendees = True
            continue
        if s.lower() == "transcript":
            in_attendees = False
            in_transcript = True
            continue
        if in_attendees:
            # Header may be one comma-separated line or wrap across lines.
            names.extend([n.strip() for n in s.split(",") if n.strip()])
            continue
        if in_transcript:
            m = SPEAKER_LINE.match(s)
            if m:
                turns.append({"name": m.group(1).strip(),
                              "text": m.group(2).strip()})
            elif turns:
                # Continuation of previous speaker turn.
                turns[-1]["text"] += " " + s
    return names, turns


def main(path, meeting_id):
    with open(path) as f:
        data = json.load(f)
    mt = next((m for m in data.get("meeting_transcripts", [])
               if m.get("id") == meeting_id), None)
    if mt is None:
        print(f"meeting_id {meeting_id} not found", file=sys.stderr)
        sys.exit(1)
    names, turns = parse(mt.get("transcript") or "")
    participants = mt.get("participants") or []
    name_to_eid = {}
    for i, nm in enumerate(names):
        if i < len(participants):
            name_to_eid[nm] = participants[i]
    for t in turns:
        t["eid"] = name_to_eid.get(t["name"])

    speakers_with_turns = []
    seen = set()
    for t in turns:
        if t["name"] not in seen:
            speakers_with_turns.append(t["name"])
            seen.add(t["name"])
    speakers_eids = [name_to_eid[n] for n in speakers_with_turns
                     if name_to_eid.get(n)]

    out = {
        "meeting_id": meeting_id,
        "document_type": mt.get("document_type"),
        "date": mt.get("date"),
        "attendees_header_order": names,
        "participants_eids": participants,
        "name_to_eid": name_to_eid,
        "turns": turns,
        "speakers_with_turns": speakers_with_turns,
        "speakers_eids": speakers_eids,
    }
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("usage: parse_transcript.py <product_file.json> <meeting_id>",
              file=sys.stderr)
        sys.exit(2)
    main(sys.argv[1], sys.argv[2])

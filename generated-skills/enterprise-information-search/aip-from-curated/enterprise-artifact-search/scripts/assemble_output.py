#!/usr/bin/env python3
"""Assemble the final, strict JSON answer object for the host agent.

Usage:
    python assemble_output.py '<json_payload>'

Payload (object):
{
  "target_product": "<ProductName>",
  "report_doc_id": "<doc_id>",
  "author_employee_ids": ["eid_..."],
  "key_reviewer_employee_ids": ["eid_..."],
  "recommendation": "USE_EVIDENCE|NEED_MORE_SEARCH|AMBIGUOUS",
  "evidence": [
    {"employee_id": "eid_...", "role": "author|key_reviewer",
     "evidence": [{"artifact_type": "...", "artifact_id": "...", "snippet": "..."}]}
  ]
}

Output:
- Order-preserving dedup: authors first, key reviewers next (Step 6).
- Computes all_employee_ids_union.
- Validates eid_* pattern on every output id; emits a `_warnings` list
  for malformed entries instead of crashing — surfaces them to the agent.
"""
import json
import re
import sys


EID_RE = re.compile(r"^eid_[A-Za-z0-9]+$")


def ordered_dedup(items):
    seen = set()
    out = []
    for x in items or []:
        if x and x not in seen:
            out.append(x)
            seen.add(x)
    return out


def main(payload):
    data = json.loads(payload)
    warnings = []

    authors = ordered_dedup(data.get("author_employee_ids") or [])
    reviewers = ordered_dedup(data.get("key_reviewer_employee_ids") or [])
    # Authors first, reviewers next; remove reviewers that duplicate authors.
    union = ordered_dedup(authors + reviewers)

    for eid in union:
        if not EID_RE.match(eid):
            warnings.append(f"malformed employee_id: {eid!r}")

    final = {
        "target_product": data.get("target_product"),
        "report_doc_id": data.get("report_doc_id"),
        "author_employee_ids": authors,
        "key_reviewer_employee_ids": [r for r in reviewers if r not in authors],
        "all_employee_ids_union": union,
    }

    out = {
        "final_answer": final,
        "evidence_map": data.get("evidence") or [],
        "recommendation": data.get("recommendation") or "USE_EVIDENCE",
    }
    if warnings:
        out["_warnings"] = warnings
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: assemble_output.py '<json_payload>'", file=sys.stderr)
        sys.exit(2)
    main(sys.argv[1])

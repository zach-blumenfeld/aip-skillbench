#!/usr/bin/env python3
"""Resolve a mix of employee IDs and names to canonical eid_* IDs.

Usage:
    python resolve_employee_ids.py <employee_dir.json> '<json_list_of_strings>'

For each input string:
- If it already matches `eid_*` and is present in the directory: kept as-is.
- If it's a `name` (case-insensitive exact match against directory `name`):
  resolved to its `employee_id`.
- Otherwise: emitted under `unresolved`.

Output JSON:
{
  "resolved": ["eid_..."],            # in input order, duplicates collapsed
  "unresolved": ["<original>", ...],
  "mapping": {"<input>": "eid_..."}   # only for items resolved by name
}
"""
import json
import re
import sys


EID_RE = re.compile(r"^eid_[A-Za-z0-9]+$")


def main(dir_path, payload):
    with open(dir_path) as f:
        directory = json.load(f)

    # The provided employee.json is a dict keyed by eid; build helpers.
    if isinstance(directory, dict):
        eid_set = set(directory.keys())
        # name_to_eid: lowercased name -> list of eids (may collide)
        name_to_eid = {}
        for eid, info in directory.items():
            if not isinstance(info, dict):
                continue
            nm = (info.get("name") or "").strip().lower()
            if nm:
                name_to_eid.setdefault(nm, []).append(eid)
    elif isinstance(directory, list):
        eid_set = {item.get("employee_id") for item in directory if isinstance(item, dict)}
        name_to_eid = {}
        for item in directory:
            if not isinstance(item, dict):
                continue
            nm = (item.get("name") or "").strip().lower()
            if nm:
                name_to_eid.setdefault(nm, []).append(item.get("employee_id"))
    else:
        print("unsupported employee directory shape", file=sys.stderr)
        sys.exit(2)

    items = json.loads(payload)
    resolved = []
    unresolved = []
    mapping = {}
    seen = set()
    for raw in items:
        if not raw:
            continue
        s = str(raw).strip()
        # Strip leading '@' (slack mentions sometimes carry it).
        if s.startswith("@"):
            s = s[1:].strip()
        if EID_RE.match(s):
            if s in eid_set:
                if s not in seen:
                    resolved.append(s)
                    seen.add(s)
            else:
                unresolved.append(raw)
            continue
        hits = name_to_eid.get(s.lower(), [])
        if len(hits) == 1:
            eid = hits[0]
            mapping[raw] = eid
            if eid not in seen:
                resolved.append(eid)
                seen.add(eid)
        elif len(hits) > 1:
            # Ambiguous — return all candidates under unresolved with a tag.
            unresolved.append({"input": raw, "ambiguous_candidates": hits})
        else:
            unresolved.append(raw)

    print(json.dumps({
        "resolved": resolved,
        "unresolved": unresolved,
        "mapping": mapping,
    }, indent=2))


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("usage: resolve_employee_ids.py <employee_dir.json> '<json_list>'",
              file=sys.stderr)
        sys.exit(2)
    main(sys.argv[1], sys.argv[2])

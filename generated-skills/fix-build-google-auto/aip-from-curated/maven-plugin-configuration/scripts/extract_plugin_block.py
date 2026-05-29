#!/usr/bin/env python3
"""Locate a specific `<plugin>` block (by groupId + artifactId) inside a pom.xml
and emit it with its byte offsets, so the agent can build a precise patch
without re-scanning the whole file.

Usage:
    extract_plugin_block.py <pom.xml> <groupId> <artifactId>

Output (JSON on stdout):
    {
      "found": true|false,
      "pom_path": "...",
      "match_count": N,
      "matches": [
        {
          "start_line": L1,    // 1-indexed, line of the opening <plugin>
          "end_line":   L2,    // 1-indexed, line of the closing </plugin>
          "in_management": true|false,  // inside <pluginManagement>?
          "block": "<plugin>...</plugin>"
        }
      ]
    }

The script uses regex slicing rather than an XML parser so it preserves
formatting exactly — Maven POMs commonly carry comments and whitespace that
ElementTree would normalize away when round-tripping.
"""
import json
import re
import sys
from pathlib import Path


def find_plugin_blocks(text: str, group_id: str, artifact_id: str):
    matches = []
    plugin_pat = re.compile(r"<plugin>", re.IGNORECASE)
    close_pat = re.compile(r"</plugin>", re.IGNORECASE)
    mgmt_open = re.compile(r"<pluginManagement\b", re.IGNORECASE)
    mgmt_close = re.compile(r"</pluginManagement>", re.IGNORECASE)

    pos = 0
    while True:
        m = plugin_pat.search(text, pos)
        if not m:
            break
        start = m.start()
        end_m = close_pat.search(text, m.end())
        if not end_m:
            break
        end = end_m.end()
        block = text[start:end]
        # tolerant matching of inner <groupId> / <artifactId>
        g = re.search(r"<groupId>\s*([^<]+?)\s*</groupId>", block)
        a = re.search(r"<artifactId>\s*([^<]+?)\s*</artifactId>", block)
        if g and a and g.group(1) == group_id and a.group(1) == artifact_id:
            preceding = text[:start]
            depth = len(mgmt_open.findall(preceding)) - len(mgmt_close.findall(preceding))
            matches.append({
                "start": start,
                "end": end,
                "block": block,
                "in_management": depth > 0,
            })
        pos = end
    return matches


def main(argv):
    if len(argv) != 4:
        print("usage: extract_plugin_block.py <pom.xml> <groupId> <artifactId>", file=sys.stderr)
        return 2

    pom_path, group_id, artifact_id = argv[1], argv[2], argv[3]
    text = Path(pom_path).read_text(encoding="utf-8")

    matches = find_plugin_blocks(text, group_id, artifact_id)

    def line_of(offset: int) -> int:
        return text.count("\n", 0, offset) + 1

    out = {
        "found": bool(matches),
        "pom_path": pom_path,
        "match_count": len(matches),
        "matches": [
            {
                "start_line": line_of(m["start"]),
                "end_line": line_of(m["end"]),
                "in_management": m["in_management"],
                "block": m["block"],
            }
            for m in matches
        ],
    }
    json.dump(out, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

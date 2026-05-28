#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///
"""Scan RAW JSON for Jackson deserialization attack structure.

This is the raw-input gate the `jackson-security` skill is built around: the
structural attacks Jackson is vulnerable to (empty-key injection, polymorphic
type directives, duplicate keys, nested variants) are invisible once `readValue`
has produced a Java object, so they must be detected on the JSON *text/bytes*
before deserialization runs. This script is that detector.

Use it two ways:
  1. As a triage tool — point it at a suspicious payload to see exactly which
     attack patterns it carries and at what depth.
  2. As the reference for a pre-deserialization validator you port into the
     target application's language (e.g. a Java check that runs on the raw
     request body before `mapper.readValue(...)`).

Patterns detected (all walked to arbitrary depth):
  * empty-key        — an object key equal to "" (the empty-string injection
                       vector). High severity.
  * type-directive   — a key beginning with "@" (e.g. @class, @type) that can
                       drive Jackson polymorphic instantiation / gadget loading.
                       High severity.
  * duplicate-key    — the same key appearing more than once in one object
                       (Jackson keeps the last; upstream filters often see the
                       first). High severity.

Duplicate and empty keys can be collapsed or hidden by a normalizing parser, so
the walk uses a pairs hook that preserves every key/value pair as written. If
the text does not parse as JSON at all, a raw-text regex fallback still flags
empty keys and @-directives (lenient parsers may accept what `json` rejects).

Usage:
  uv run scan_raw_json.py payload.json
  cat payload.json | uv run scan_raw_json.py -
  uv run scan_raw_json.py --quiet payload.json   # suppress stdout JSON

Output contract:
  stdout — JSON object {"malicious": bool, "findings": [...]} (unless --quiet).
  stderr — one human-readable line per finding, then a summary.
  exit 0 — no high-severity pattern found.
  exit 1 — at least one high-severity pattern found.
  exit 2 — usage / I/O error.
"""

import argparse
import json
import re
import sys


class _Obj:
    """Carrier for an object's key/value pairs, preserving order and dupes."""

    __slots__ = ("pairs",)

    def __init__(self, pairs):
        self.pairs = pairs


def _pairs_hook(pairs):
    return _Obj(list(pairs))


def _walk(node, path, findings):
    if isinstance(node, _Obj):
        counts = {}
        for key, value in node.pairs:
            counts[key] = counts.get(key, 0) + 1
            here = path + [key if key != "" else '""']
            loc = "/".join(here) if here else "<root>"
            if key == "":
                findings.append({
                    "pattern": "empty-key",
                    "severity": "high",
                    "path": loc,
                    "depth": len(path),
                    "detail": 'empty-string ("") key — can override server-set '
                              "values via @JacksonInject/@JsonAnySetter",
                })
            elif key.startswith("@"):
                findings.append({
                    "pattern": "type-directive",
                    "severity": "high",
                    "path": loc,
                    "depth": len(path),
                    "detail": f"polymorphic type key {key!r} — can drive "
                              "@JsonTypeInfo gadget instantiation",
                })
            _walk(value, here, findings)
        for key, n in counts.items():
            if n > 1:
                shown = key if key != "" else '""'
                findings.append({
                    "pattern": "duplicate-key",
                    "severity": "high",
                    "path": "/".join(path + [shown]) if path else shown,
                    "depth": len(path),
                    "detail": f"key {shown!r} repeated {n}x — Jackson keeps the "
                              "last value; upstream filters often see the first",
                })
    elif isinstance(node, list):
        for i, item in enumerate(node):
            _walk(item, path + [f"[{i}]"], findings)


# Raw-text fallback for input that does not parse as strict JSON.
_EMPTY_KEY_RE = re.compile(r'""\s*:')
_AT_KEY_RE = re.compile(r'"(@[^"]*)"\s*:')


def _raw_text_scan(text, findings):
    for _ in _EMPTY_KEY_RE.finditer(text):
        findings.append({
            "pattern": "empty-key",
            "severity": "high",
            "path": "<unparsed>",
            "depth": -1,
            "detail": 'empty-string ("") key found via raw-text scan '
                      "(input did not parse as strict JSON)",
        })
    for m in _AT_KEY_RE.finditer(text):
        findings.append({
            "pattern": "type-directive",
            "severity": "high",
            "path": "<unparsed>",
            "depth": -1,
            "detail": f"polymorphic type key {m.group(1)!r} found via raw-text "
                      "scan (input did not parse as strict JSON)",
        })


def scan(text):
    findings = []
    try:
        root = json.loads(text, object_pairs_hook=_pairs_hook)
        _walk(root, [], findings)
    except (json.JSONDecodeError, ValueError):
        _raw_text_scan(text, findings)
    malicious = any(f["severity"] == "high" for f in findings)
    return {"malicious": malicious, "findings": findings}


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path", help="path to a JSON file, or - for stdin")
    ap.add_argument("--quiet", action="store_true",
                    help="suppress the stdout JSON report (exit code still signals)")
    args = ap.parse_args()

    try:
        if args.path == "-":
            text = sys.stdin.read()
        else:
            with open(args.path, "r", encoding="utf-8") as fh:
                text = fh.read()
    except OSError as exc:
        print(f"ERROR: cannot read input: {exc}", file=sys.stderr)
        return 2

    result = scan(text)

    if not args.quiet:
        print(json.dumps(result, indent=2))

    for f in result["findings"]:
        print(f"[{f['severity'].upper()}] {f['pattern']} at {f['path']} "
              f"(depth {f['depth']}): {f['detail']}", file=sys.stderr)
    if result["malicious"]:
        print(f"FAIL: {len(result['findings'])} attack pattern(s) detected in "
              "raw input — reject before deserialization", file=sys.stderr)
        return 1
    print("OK: no Jackson deserialization attack patterns detected", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

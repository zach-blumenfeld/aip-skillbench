#!/usr/bin/env python3
"""Fill a Word (.docx) template's {{KEY}} placeholders and {{IF_X}}...{{END_IF_X}}
conditional blocks from a JSON data file, preserving run formatting.

Requires: Python >= 3.8, python-docx >= 1.1 (pip name `python-docx`; brings lxml).

Subcommands
  inspect TEMPLATE [--data JSON] [--condition K=yes|no] [--text]
      List every placeholder and conditional block (joined across split runs) in
      body, nested tables, headers, footers, footnotes/endnotes; show which data
      key and value each one resolves to. Exit 0 if everything resolves, 2 if a
      placeholder or condition is unresolved. --text dumps every paragraph.
  fill TEMPLATE --data JSON --out OUT.docx [--condition K=yes|no]... [--set KEY=VALUE]...
      Resolve conditionals (keep content + strip markers, or delete the block),
      replace placeholders, save, reload and verify. Prints a JSON report.
      Exit 0 = saved and verified; 1 = saved but verification failed;
      2 = unresolved placeholder/condition (nothing saved); 3 = bad input.

Why run-aware editing: Word splits "{{CANDIDATE_NAME}}" into runs like "{{CANDI" +
"DATE_NAME}}". Text is matched on the paragraph's joined text, and each edit is
written into the run where the match starts, so surrounding runs keep their own
formatting (bold labels, underlined dates) instead of collapsing into run 1.
"""
import argparse
import json
import os
import re
import sys
import zipfile

try:
    from docx import Document
    from docx.oxml.ns import qn
    from lxml import etree
except ImportError:  # pragma: no cover
    sys.exit("ERROR: python-docx is not installed. Install with: pip install python-docx")

W_P, W_T, W_TC = qn("w:p"), qn("w:t"), qn("w:tc")
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"
TEXT_PART_TYPES = (
    "wordprocessingml.document.main+xml",
    "wordprocessingml.template.main+xml",
    "wordprocessingml.header+xml",
    "wordprocessingml.footer+xml",
    "wordprocessingml.footnotes+xml",
    "wordprocessingml.endnotes+xml",
)
MARKER_RE = re.compile(r"\{\{\s*(END_IF|IF)_([A-Za-z0-9_]+?)\s*\}\}")
PH_RE = re.compile(r"\{\{\s*([A-Za-z0-9_.\-]+)\s*\}\}")
LEFTOVER_RE = re.compile(r"\{\{|\}\}")
TRUE_WORDS = {"yes", "y", "true", "t", "on", "include", "included", "eligible", "x"}
FALSE_WORDS = {"no", "n", "false", "f", "off", "none", "exclude", "excluded",
               "not eligible", "ineligible", "n/a", "na", ""}


class Unresolved(Exception):
    pass


# ---------------------------------------------------------------- data helpers
def load_data(path):
    try:
        with open(path, encoding="utf-8-sig") as fh:
            raw = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        sys.exit(f"ERROR: cannot read data JSON {path}: {exc}")
    if isinstance(raw, list) and len(raw) == 1 and isinstance(raw[0], dict):
        raw = raw[0]
    if not isinstance(raw, dict):
        sys.exit("ERROR: data JSON must be an object of KEY: value (or a 1-element list of one); "
                 "if it holds several records, extract the one to use into its own file first.")
    flat = {}

    def walk(obj, prefix):
        for k, v in obj.items():
            key = f"{prefix}_{k}" if prefix else str(k)
            if isinstance(v, dict):
                walk(v, key)
            else:
                flat[key] = v
                flat.setdefault(str(k), v)  # nested leaf also reachable by its own name
    walk(raw, "")
    return flat


def parse_kv(items, what):
    out = {}
    for item in items or []:
        if "=" not in item:
            sys.exit(f"ERROR: {what} must look like KEY=VALUE, got {item!r}")
        k, v = item.split("=", 1)
        out[k.strip()] = v
    return out


def lookup(data, key):
    if key in data:
        return True, data[key]
    low = {k.lower(): k for k in data}
    if key.lower() in low:
        return True, data[low[key.lower()]]
    return False, None


def to_bool(value, strict_words_only=False):
    """Return True/False, or None if the value is not a yes/no-like flag."""
    if isinstance(value, bool):
        return value
    if value is None:
        return None if strict_words_only else False
    if isinstance(value, (int, float)):
        return None if strict_words_only else value != 0
    s = str(value).strip().lower()
    if strict_words_only and s in ("", "n/a", "na", "none", "x", "t", "f"):
        return None
    if s in TRUE_WORDS:
        return True
    if s in FALSE_WORDS:
        return False
    if not strict_words_only and s in ("1", "0"):
        return s == "1"
    return None


def resolve_condition(name, data, overrides):
    """Map IF_<name> to include True/False. Returns (bool, source-description)."""
    for k, v in overrides.items():
        if k.upper() in (name.upper(), f"IF_{name}".upper()):
            b = to_bool(v)
            if b is None:
                raise Unresolved(f"--condition {k}={v!r} is not yes/no")
            return b, f"--condition {k}={v}"
    for cand in (name, f"IF_{name}", f"INCLUDE_{name}", f"HAS_{name}", f"SHOW_{name}"):
        found, v = lookup(data, cand)
        if found and to_bool(v, strict_words_only=True) is not None:
            return to_bool(v), f"{cand}={v!r}"  # a non-flag value (e.g. BONUS="5,000") falls through
    # e.g. IF_RELOCATION <- RELOCATION_PACKAGE: "Yes". Only yes/no-word values qualify,
    # so RELOCATION_AMOUNT / RELOCATION_DAYS are never mistaken for the flag.
    u = name.upper()
    cands = [(k, v) for k, v in data.items()
             if (k.upper().startswith(u + "_") or k.upper().endswith("_" + u)
                 or (u + "_") in k.upper() or ("_" + u) in k.upper())
             and to_bool(v, strict_words_only=True) is not None]
    if len(cands) == 1:
        k, v = cands[0]
        return to_bool(v), f"{k}={v!r}"
    if len(cands) > 1:
        raise Unresolved(f"IF_{name}: several yes/no data keys could govern it: "
                         + ", ".join(f"{k}={v!r}" for k, v in cands))
    found, v = lookup(data, name)
    if found and isinstance(v, (int, float)) and not isinstance(v, bool) and v in (0, 1):
        return bool(v), f"{name}={v!r}"
    raise Unresolved(f"IF_{name}: no data key holds a yes/no value for it")


def format_value(v):
    if v is None:
        return ""
    if isinstance(v, bool):
        return "Yes" if v else "No"
    if isinstance(v, (list, dict)):
        raise Unresolved(f"value {v!r} is a list/object, not text")
    return str(v)


# ------------------------------------------------------------ XML text helpers
def text_parts(doc):
    """Yield (name, root_element, commit_fn) for every part that holds document text."""
    seen = set()
    for part in doc.part.package.iter_parts():
        ct = part.content_type or ""
        if not ct.endswith(TEXT_PART_TYPES) or part.partname in seen:
            continue
        seen.add(part.partname)
        name = str(part.partname).rsplit("/", 1)[-1]
        if hasattr(part, "element"):
            yield name, part.element, (lambda: None)
        else:  # footnotes/endnotes load as plain blob parts
            root = etree.fromstring(part.blob)

            def commit(part=part, root=root):
                part._blob = etree.tostring(root, xml_declaration=True,
                                            encoding="UTF-8", standalone=True)
            yield name, root, commit


def own_ts(p):
    """w:t elements belonging to paragraph p itself (not to text boxes nested in it)."""
    out = []
    for t in p.iter(W_T):
        anc = t.getparent()
        while anc is not None and anc.tag != W_P:
            anc = anc.getparent()
        if anc is p:
            out.append(t)
    return out


def ptext(p):
    return "".join(t.text or "" for t in own_ts(p))


def splice(p, start, end, repl):
    """Replace chars [start, end) of p's joined text with repl, editing runs in place.
    The replacement lands in the run holding `start`, so it inherits that run's format."""
    ts = own_ts(p)
    spans, pos = [], 0
    for t in ts:
        n = len(t.text or "")
        spans.append((pos, pos + n))
        pos += n
    if not ts or start > pos or end > pos or start > end:
        raise RuntimeError("splice position outside paragraph text")
    home = next((i for i, (a, b) in enumerate(spans) if a <= start < b), None)
    if home is None:  # start sits at the very end of the text
        home = max(i for i, (a, b) in enumerate(spans) if a <= start <= b)
    for i, (t, (a, b)) in enumerate(zip(ts, spans)):
        s = t.text or ""
        if i == home:
            new = s[:start - a] + repl + s[max(min(end, b) - a, start - a):]
        elif max(start, a) < min(end, b):
            new = s[:max(start, a) - a] + s[min(end, b) - a:]
        else:
            continue
        if new != s:
            t.text = new
            t.set(XML_SPACE, "preserve")


def has_content_besides_text(p):
    return any(el.tag.endswith(("}drawing", "}pict", "}object")) for el in p.iter())


def remove_paragraph(p):
    """Delete p; keep it (emptied) where Word requires a paragraph or it carries a section break."""
    parent = p.getparent()
    if parent is None:
        return
    ppr = p.find(qn("w:pPr"))
    keeps_section = ppr is not None and ppr.find(qn("w:sectPr")) is not None
    last_in_cell = parent.tag == W_TC and len(parent.findall(W_P)) == 1
    if keeps_section or last_in_cell:
        for child in list(p):
            if child.tag != qn("w:pPr"):
                p.remove(child)
    else:
        parent.remove(p)


# ------------------------------------------------------------- core passes
def find_markers(root):
    paras = list(root.iter(W_P))
    marks = []
    for i, p in enumerate(paras):
        for m in MARKER_RE.finditer(ptext(p)):
            marks.append({"para": i, "start": m.start(), "end": m.end(),
                          "end_marker": m.group(1) == "END_IF", "name": m.group(2)})
    return paras, marks


def innermost_pair(marks):
    stack = []
    for m in marks:
        if not m["end_marker"]:
            stack.append(m)
        else:
            if not stack or stack[-1]["name"] != m["name"]:
                raise Unresolved(f"unbalanced conditional marker END_IF_{m['name']}")
            return stack.pop(), m
    if stack:
        raise Unresolved(f"IF_{stack[-1]['name']} has no matching END_IF_{stack[-1]['name']}")
    return None


def apply_conditionals(root, data, overrides, report, part_name):
    while True:
        paras, marks = find_markers(root)
        pair = innermost_pair(marks)
        if pair is None:
            return
        a, b = pair
        include, src = resolve_condition(a["name"], data, overrides)
        pa, pb = paras[a["para"]], paras[b["para"]]
        a_only = ptext(pa).strip() == ptext(pa)[a["start"]:a["end"]].strip() if pa is not pb else False
        b_only = ptext(pb).strip() == ptext(pb)[b["start"]:b["end"]].strip() if pa is not pb else False
        if pa is pb:
            inner = ptext(pa)[a["end"]:b["start"]]
        else:
            inner = "\n".join([ptext(pa)[a["end"]:]] + [ptext(x) for x in paras[a["para"] + 1:b["para"]]]
                              + [ptext(pb)[:b["start"]]])
        report["conditionals"].append({"part": part_name, "block": f"IF_{a['name']}", "include": include,
                                       "decided_by": src, "content": inner.strip()})
        if include:
            splice(pb, b["start"], b["end"], "")
            splice(pa, a["start"], a["end"], "")
            for p, only in ((pb, b_only), (pa, a_only)):
                if only and not ptext(p).strip() and not has_content_besides_text(p):
                    remove_paragraph(p)
            continue
        if pa is pb:
            text = ptext(pa)
            had_other = bool((text[:a["start"]] + text[b["end"]:]).strip())
            cut_end = b["end"]
            if a["start"] > 0 and text[a["start"] - 1] == " " and text[cut_end:cut_end + 1] == " ":
                cut_end += 1  # "Pre {{IF_X}}...{{END_IF_X}} post" -> "Pre post", not "Pre  post"
            splice(pa, a["start"], cut_end, "")
            if not had_other and not has_content_besides_text(pa):
                remove_paragraph(pa)
            continue
        splice(pb, 0, b["end"], "")
        splice(pa, a["start"], len(ptext(pa)), "")
        middle = paras[a["para"] + 1:b["para"]]
        if pa.getparent() is pb.getparent() and pa.getparent() is not None:
            parent = pa.getparent()
            sibs = list(parent)
            for el in sibs[sibs.index(pa) + 1:sibs.index(pb)]:
                if el.tag != qn("w:sectPr"):
                    parent.remove(el)
        else:
            for p in middle:
                remove_paragraph(p)
        for p in (pb, pa):
            if not ptext(p).strip() and not has_content_besides_text(p):
                remove_paragraph(p)


def placeholders_in(root):
    for p in root.iter(W_P):
        for m in PH_RE.finditer(ptext(p)):
            yield p, m


def replace_placeholders(root, data, sets, report, part_name, unresolved):
    for p in list(root.iter(W_P)):
        text = ptext(p)
        matches = [m for m in PH_RE.finditer(text) if not MARKER_RE.fullmatch(m.group(0))]
        for m in reversed(matches):  # right-to-left keeps earlier offsets valid
            key = m.group(1)
            found, v = lookup(sets, key)
            if not found:
                found, v = lookup(data, key)
            if not found:
                unresolved.append(f"{part_name}: {{{{{key}}}}} has no data key")
                continue
            try:
                val = format_value(v)
            except Unresolved as exc:
                unresolved.append(f"{part_name}: {{{{{key}}}}} {exc}")
                continue
            if val.startswith("$") and m.start() > 0 and text[m.start() - 1] == "$":
                val = val[1:]  # template already has "$" before the placeholder
            splice(p, m.start(), m.end(), val)
            report["replaced"].append({"part": part_name, "key": key, "value": val})


# ---------------------------------------------------------------- commands
def all_text(doc):
    return {name: [ptext(p) for p in root.iter(W_P)] for name, root, _ in text_parts(doc)}


def cmd_inspect(args):
    doc = Document(args.template)
    data = load_data(args.data) if args.data else None
    overrides = parse_kv(args.condition, "--condition")
    sets = parse_kv(args.set, "--set")
    problems, out = [], {"placeholders": {}, "conditionals": []}
    for name, root, _ in text_parts(doc):
        paras, marks = find_markers(root)
        names_seen = set()
        for m in marks:
            if m["end_marker"] or m["name"] in names_seen:
                continue
            names_seen.add(m["name"])
            entry = {"part": name, "block": f"IF_{m['name']}"}
            if data is not None:
                try:
                    entry["include"], entry["decided_by"] = resolve_condition(m["name"], data, overrides)
                except Unresolved as exc:
                    entry["unresolved"] = str(exc)
                    problems.append(str(exc))
            out["conditionals"].append(entry)
        try:
            innermost_pair(marks)
        except Unresolved as exc:
            problems.append(f"{name}: {exc}")
        for p, m in placeholders_in(root):
            if MARKER_RE.fullmatch(m.group(0)):
                continue
            key = m.group(1)
            entry = out["placeholders"].setdefault(key, {"parts": [], "count": 0})
            entry["count"] += 1
            if name not in entry["parts"]:
                entry["parts"].append(name)
            if data is not None and "value" not in entry:
                found, v = lookup(sets, key)
                if not found:
                    found, v = lookup(data, key)
                entry["value"] = v if found else None
                if not found:
                    entry["unresolved"] = True
                    problems.append(f"{name}: {{{{{key}}}}} has no data key")
    if data is not None:
        used = {k.lower() for k in out["placeholders"]}
        out["data_keys_not_in_template"] = [k for k in data if k.lower() not in used]
    if args.text:
        out["text"] = all_text(doc)
    out["problems"] = problems
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 2 if problems else 0


def cmd_fill(args):
    data = load_data(args.data)
    overrides = parse_kv(args.condition, "--condition")
    sets = parse_kv(args.set, "--set")
    try:
        doc = Document(args.template)
    except Exception as exc:
        print(f"ERROR: cannot open template {args.template}: {exc}", file=sys.stderr)
        return 3
    report = {"conditionals": [], "replaced": [], "unresolved": [], "verify": {}}
    unresolved = []
    commits = []
    try:
        for name, root, commit in text_parts(doc):
            apply_conditionals(root, data, overrides, report, name)
            replace_placeholders(root, data, sets, report, name, unresolved)
            commits.append(commit)
    except Unresolved as exc:
        unresolved.append(str(exc))
    if unresolved:
        report["unresolved"] = unresolved
        print(json.dumps(report, indent=2, ensure_ascii=False))
        print("ERROR: unresolved items; nothing saved. Answer them with --condition / --set.", file=sys.stderr)
        return 2
    for c in commits:
        c()
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    doc.save(args.out)
    report["verify"] = verify(args.out, report)
    report["output"] = os.path.abspath(args.out)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if report["verify"]["failures"]:
        print("ERROR: output saved but verification failed; see verify.failures", file=sys.stderr)
        return 1
    return 0


def verify(path, report):
    """Reload the saved file independently and check the fill really landed."""
    failures = []
    try:
        doc = Document(path)
        zipfile.ZipFile(path).testzip()
    except Exception as exc:
        return {"failures": [f"output does not reopen: {exc}"]}
    texts = all_text(doc)
    joined = {k: "\n".join(v) for k, v in texts.items()}
    for part, paras in texts.items():
        for t in paras:
            if LEFTOVER_RE.search(t):
                failures.append(f"{part}: leftover braces in paragraph '{t[:120]}'")
    for r in report["replaced"]:
        if r["value"] and r["value"] not in joined.get(r["part"], ""):
            failures.append(f"{r['part']}: value for {r['key']} ({r['value']!r}) not found")
    everything = "\n".join(joined.values())
    for c in report["conditionals"]:
        # literal text of the block between its placeholders, e.g. "This includes moving expenses"
        frags = [f.strip() for f in re.split(r"\x00|\n", PH_RE.sub("\x00", c["content"]))]
        frags = [f for f in frags if len(f) >= 4]
        if not frags:
            continue
        if c["include"]:
            missing = [f for f in frags if f not in everything]
            if missing:
                failures.append(f"{c['block']} should be kept but text is missing: {missing[0]!r}")
        else:
            longest = max(frags, key=len)
            if len(longest) >= 12 and longest in everything:
                failures.append(f"{c['block']} should be removed but {longest!r} is still present")
    return {"failures": failures, "parts_checked": sorted(joined),
            "replacements": len(report["replaced"])}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("inspect")
    i.add_argument("template")
    i.add_argument("--data")
    i.add_argument("--condition", action="append")
    i.add_argument("--set", action="append")
    i.add_argument("--text", action="store_true")
    f = sub.add_parser("fill")
    f.add_argument("template")
    f.add_argument("--data", required=True)
    f.add_argument("--out", required=True)
    f.add_argument("--condition", action="append", help="NAME=yes|no for an IF_NAME block")
    f.add_argument("--set", action="append", help="KEY=VALUE to add or override a placeholder value")
    args = ap.parse_args()
    sys.exit(cmd_inspect(args) if args.cmd == "inspect" else cmd_fill(args))


if __name__ == "__main__":
    main()

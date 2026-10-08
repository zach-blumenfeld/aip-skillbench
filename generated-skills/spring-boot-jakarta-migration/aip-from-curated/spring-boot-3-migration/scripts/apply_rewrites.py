"""apply-rewrites: deterministic Boot 3 edits (pom, javax->jakarta, security renames, HQL), then re-scan."""
import os

import sys

sys.dont_write_bytecode = True  # keep the skill folder free of __pycache__

import sb3lib  # noqa: E402


def main():
    state, cfg = sb3lib.read_payload()
    root = sb3lib.project_root(state)
    _, before = sb3lib.scan(root, cfg)
    changes = []

    # Source/config files first so the pom step knows whether XML binding is used.
    uses_xml_bind = False
    for path in sb3lib.walk(root, cfg, sb3lib.EDIT_EXTS):
        if os.path.basename(path) == "pom.xml":
            continue
        text = sb3lib.read(path)
        new, edits = sb3lib.rewrite_source(path, text, cfg)
        if new != text:
            sb3lib.write(path, new)
            for rule, n in edits:
                changes.append({"file": sb3lib.rel(root, path), "rule": rule, "count": n})
        if path.endswith((".java", ".kt")) and ("jakarta.xml.bind" in new or "javax.xml.bind" in new):
            uses_xml_bind = True

    for path in sb3lib.walk(root, cfg, (".xml",)):
        if os.path.basename(path) != "pom.xml":
            continue
        text = sb3lib.read(path)
        new, edits = sb3lib.rewrite_pom(text, cfg, uses_xml_bind)
        if new != text:
            sb3lib.write(path, new)
            for e in edits:
                changes.append({"file": sb3lib.rel(root, path), "rule": "build", "detail": e})

    inv, remaining = sb3lib.scan(root, cfg, state.get("waived_issues"))
    sb3lib.emit({
        "changes": changes,
        "issues_fixed_automatically": len(before) - len(remaining),
        "remaining_issues": remaining,
        "remaining_issue_counts": sb3lib.summarize(remaining),
        "inventory": inv,
    })


if __name__ == "__main__":
    main()

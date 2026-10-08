"""Step locate-product: resolve the dataset root, the target product (by file name or
by a codename found in a product's own workspace), its alias list, the document type
the question names, and a compact inventory of the product's artifacts."""
import json
import re
from collections import Counter

from eas_lib import (derive_aliases, emit, fail, load_json, norm, product_files,
                     read_payload, resolve_root, slack_items)


def find_doc_type(question, synonyms, dataset_types):
    q = " " + re.sub(r"[^a-z0-9 ]", " ", question.lower()) + " "
    best = ""
    for dtype, syns in synonyms.items():
        for s in sorted(syns, key=len, reverse=True):
            if " " + s + " " in q and len(s) > len(best and best[1] or ""):
                best = (dtype, s)
    if best:
        return best[0]
    for t in dataset_types:
        if t and t.lower() in question.lower():
            return t
    return ""


def main():
    state, assets, _ = read_payload()
    question = state.get("question") or fail("state.question is required")
    root = resolve_root(state.get("data_root"))
    files = product_files(root)
    if not files:
        fail("no product files under products/", data_root=root)

    qn = norm(question)
    by_name = [p for p in files if norm(p) in qn]
    target, matched_via = "", ""
    if by_name:
        target, matched_via = max(by_name, key=len), "product file name"
    alias_map = {}
    for p, path in files.items():
        alias_map[p] = derive_aliases(p, load_json(path))
    if not target:
        hits = [(p, a) for p, al in alias_map.items() for a in al
                if len(norm(a)) >= 5 and norm(a) in qn]
        if hits:
            target, a = max(hits, key=lambda h: len(norm(h[1])))
            matched_via = "codename '%s' found in %s workspace" % (a, target)

    syn = assets.get("doc_types")
    syn = json.loads(syn) if isinstance(syn, str) else (syn or {})
    dataset_types = set()
    inventory = {}
    if target:
        prod = load_json(files[target])
        dataset_types = {d.get("type", "") for d in prod.get("documents", [])}
        items = slack_items(prod)
        inventory = {
            "counts": {k: len(v or []) for k, v in prod.items()},
            "channels": dict(Counter(i["channel"] for i in items).most_common()),
            "documents": [{"id": d.get("id"), "type": d.get("type"), "date": d.get("date"),
                           "author": d.get("author"), "has_feedback": bool(d.get("feedback"))}
                          for d in prod.get("documents", [])],
            "meetings": [{"id": m.get("id"), "document_type": m.get("document_type"),
                          "date": m.get("date")} for m in prod.get("meeting_transcripts", [])],
        }
    doc_type = find_doc_type(question, syn, dataset_types)

    emit({
        "data_root": root,
        "target_product": target,
        "product_found": bool(target),
        "product_match": matched_via or "no product or codename named in the question",
        "product_file": files.get(target, ""),
        "aliases": alias_map.get(target, []),
        "doc_type": doc_type,
        "all_products": sorted(files),
        "inventory": inventory,
    })


if __name__ == "__main__":
    main()

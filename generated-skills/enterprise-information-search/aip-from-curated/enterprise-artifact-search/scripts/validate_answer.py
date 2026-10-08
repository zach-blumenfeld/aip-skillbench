"""Step validate-answer: check the assembled answer against the dataset. Every eid must
exist in the employee directory, every URL must appear verbatim in the data, every
answer value needs an evidence record whose artifact id exists, lists are de-duplicated
in order, and the report case gets its authors-then-reviewers union rebuilt."""
import json

from eas_lib import EID_RE, URL_RE, emit, fail, load_employees, load_json, product_files, read_payload

RECS = {"USE_EVIDENCE", "NEED_MORE_SEARCH", "AMBIGUOUS"}


def dedupe(seq):
    return list(dict.fromkeys(x for x in seq if x not in (None, "")))


def artifact_ids(prod):
    ids = set()
    for m in prod.get("slack", []) or []:
        ids.add(m.get("id"))
        u = (m.get("Message") or {}).get("User") or {}
        ids.add(u.get("utterranceID"))
    for k in ("documents", "meeting_transcripts", "meeting_chats", "urls", "prs"):
        for x in prod.get(k, []) or []:
            ids.add(x.get("id"))
    return {i for i in ids if i}


def main():
    state, _, _ = read_payload()
    root = state.get("data_root") or fail("state.data_root is required")
    ans = state.get("final_answer")
    if not isinstance(ans, dict):
        fail("state.final_answer must be an object")
    files = product_files(root)
    employees = load_employees(root)
    product = state.get("target_product") or ans.get("target_product") or ""
    scope = [product] if product in files else list(files)
    known, blobs = set(), []
    for p in scope:
        prod = load_json(files[p])
        known |= artifact_ids(prod)
        blobs.append(json.dumps(prod, ensure_ascii=False))
    blob = "\n".join(blobs)
    errors = []

    for k, v in list(ans.items()):
        if isinstance(v, list) and all(isinstance(x, str) for x in v):
            ans[k] = dedupe(v)
    if "author_employee_ids" in ans or "key_reviewer_employee_ids" in ans:
        authors = ans.get("author_employee_ids") or []
        ans["key_reviewer_employee_ids"] = [i for i in ans.get("key_reviewer_employee_ids") or [] if i not in authors]
        ans["all_employee_ids_union"] = dedupe(authors + ans["key_reviewer_employee_ids"])
        ans["answer"] = ans["all_employee_ids_union"]

    values = ans.get("answer")
    if not isinstance(values, list) or not values:
        errors.append("final_answer.answer must be a non-empty list (use [] only with recommendation NEED_MORE_SEARCH or AMBIGUOUS)")
        values = values if isinstance(values, list) else []
    if ans.get("recommendation") not in RECS:
        errors.append("final_answer.recommendation must be one of %s" % sorted(RECS))

    for v in values:
        if not isinstance(v, str):
            errors.append("answer value %r is not a string" % (v,))
            continue
        if v.startswith("eid_"):
            if not EID_RE.fullmatch(v):
                errors.append("%s is not a well-formed employee id" % v)
            elif employees and v not in employees:
                errors.append("%s is not in metadata/employee.json" % v)
        elif URL_RE.match(v) and v not in blob:
            errors.append("URL %s does not appear verbatim in the dataset" % v)

    ev = ans.get("evidence") or []
    covered = {}
    for e in ev if isinstance(ev, list) else []:
        if not isinstance(e, dict):
            continue
        aid = e.get("artifact_id")
        if aid and aid not in known and aid not in blob:
            errors.append("evidence artifact_id %s not found in the dataset" % aid)
        covered.setdefault(e.get("value"), []).append(aid)
    for v in values:
        if not covered.get(v):
            errors.append("no evidence record for answer value %s" % v)

    emit({
        "answer_valid": not errors,
        "validation_errors": errors,
        "final_answer": ans,
    })


if __name__ == "__main__":
    main()

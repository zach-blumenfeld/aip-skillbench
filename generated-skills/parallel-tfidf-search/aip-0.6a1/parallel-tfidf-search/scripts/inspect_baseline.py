#!/usr/bin/env python3
"""
Inspect the sequential TF-IDF baseline and decide whether the bundled
parallel_solution.py template applies unchanged ("template") or must be
adapted ("adapt").

stdin : {"state": {workspace_dir, solution_path, num_workers, num_docs, num_queries}, ...}
stdout: {"plan", "deviations", "baseline_profile"}
"""

import ast
import json
import multiprocessing as mp
import os
import platform
import re
import sys

# Names the template imports from the workspace modules.
REQUIRED = {
    "sequential.py": {
        "functions": {
            "tokenize": ["text"],
            "compute_term_frequencies": ["tokens"],
            "build_tfidf_index_sequential": ["documents"],
            "search_sequential": ["query", "index", "top_k", "documents"],
            "batch_search_sequential": ["queries", "index", "top_k", "documents"],
        },
        "classes": {
            "TFIDFIndex": ["num_documents", "vocabulary", "document_frequencies", "idf", "inverted_index", "doc_vectors", "doc_norms"],
            "SearchResult": ["doc_id", "score", "title"],
            "IndexingResult": ["index", "elapsed_time", "num_documents", "vocabulary_size"],
        },
    },
    "document_generator.py": {
        "functions": {"generate_corpus": ["num_docs"]},
        "classes": {"Document": ["doc_id", "title", "content"]},
    },
}

# Semantics the template's single-pass merge and posting-list scorer reproduce. If one is missing the
# baseline computes the index differently and the template must be adapted.
FINGERPRINTS = {
    "document text is title + ' ' + content": r'doc\.title\s*\+\s*" "\s*\+\s*doc\.content',
    "IDF = log(N / df) + 1": r"math\.log\(\s*N\s*/\s*df\s*\)\s*\+\s*1",
    "TF-IDF = tf * idf[term]": r"tf\s*\*\s*index\.idf\[term\]",
    "posting lists stable-sorted by score descending": r"\.sort\(\s*key\s*=\s*lambda x:\s*x\[1\]\s*,\s*reverse\s*=\s*True\s*\)",
    "doc norm = sqrt(sum of squared TF-IDF)": r"math\.sqrt\(\s*norm_squared\s*\)",
    "N = number of documents passed in": r"num_documents\s*=\s*len\(\s*documents\s*\)",
    "posting lists stored whole (no truncation)": r"index\.inverted_index\[term\]\s*=\s*posting_list\s*$",
    "query tokens = tokenize(query), unmodified": r"query_tokens\s*=\s*tokenize\(\s*query\s*\)\s*$",
    "query TF-IDF = tf * idf over terms known to the index": r"if term in index\.idf:",
    "candidates = docs in the query terms' posting lists, collected in a set": r"candidate_docs\.add\(\s*doc_id\s*\)",
    "dot product = builtin sum of query weight * doc weight in query-term order": r"sum\(\s*query_vector\.get\(\s*term\s*,\s*0\s*\)\s*\*\s*doc_vector\.get\(\s*term\s*,\s*0\s*\)\s*for term in query_vector\s*\)",
    "zero-norm documents skipped": r"if doc_norm == 0:",
    "cosine = dot / (query_norm * doc_norm)": r"dot_product\s*/\s*\(\s*query_norm\s*\*\s*doc_norm\s*\)",
    "top-k = nlargest by score": r"nlargest\(\s*top_k\s*,\s*scores\s*,\s*key\s*=\s*lambda x:\s*x\[1\]\s*\)",
    "titles default to f'Document {doc_id}'": r'doc_titles\.get\(\s*doc_id\s*,\s*f"Document \{doc_id\}"\s*\)',
}


def fields_of(node):
    names = []
    for stmt in node.body:
        if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
            names.append(stmt.target.id)
    return names


def check_module(path, spec, deviations):
    with open(path) as f:
        src = f.read()
    tree = ast.parse(src)
    funcs = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
    classes = {n.name: n for n in tree.body if isinstance(n, ast.ClassDef)}
    base = os.path.basename(path)
    for name, params in spec["functions"].items():
        if name not in funcs:
            deviations.append(f"{base}: function {name}() is missing")
            continue
        args = [a.arg for a in funcs[name].args.args]
        if args[: len(params)] != params:
            deviations.append(f"{base}: {name}() parameters are {args}, template expects {params}")
    for name, fields in spec["classes"].items():
        if name not in classes:
            deviations.append(f"{base}: class {name} is missing")
            continue
        have = fields_of(classes[name])
        missing = [f for f in fields if f not in have]
        if missing:
            deviations.append(f"{base}: class {name} lacks fields {missing}")
    return src


def main():
    payload = json.load(sys.stdin)
    state = payload.get("state", {})
    workspace = state["workspace_dir"]
    solution_path = state["solution_path"]
    num_workers = int(state.get("num_workers", 4))

    deviations = []
    sources = {}
    for fname, spec in REQUIRED.items():
        path = os.path.join(workspace, fname)
        if not os.path.isfile(path):
            deviations.append(f"{fname} not found in {workspace}")
            continue
        try:
            sources[fname] = check_module(path, spec, deviations)
        except SyntaxError as e:
            deviations.append(f"{fname} does not parse: {e}")

    seq = sources.get("sequential.py", "")
    matched = []
    for label, pattern in FINGERPRINTS.items():
        if seq and re.search(pattern, seq, re.MULTILINE):
            matched.append(label)
        elif seq:
            deviations.append(f"sequential.py: expected semantics not found: {label}")

    if os.path.dirname(os.path.abspath(solution_path)) != os.path.abspath(workspace):
        deviations.append("solution_path is not inside workspace_dir; the template imports sequential.py from its own folder")

    cpus = os.cpu_count() or 1
    profile = {
        "workspace_files": sorted(os.listdir(workspace)) if os.path.isdir(workspace) else [],
        "solution_exists": os.path.isfile(solution_path),
        "python": platform.python_version(),
        "cpu_count": cpus,
        "start_methods": mp.get_all_start_methods(),
        "default_start_method": mp.get_start_method(allow_none=True) or mp.get_context().get_start_method(),
        "fork_available": "fork" in mp.get_all_start_methods(),
        "semantics_matched": matched,
        "enough_cores_for_target": cpus >= num_workers,
    }
    plan = "template" if not deviations else "adapt"
    json.dump({"plan": plan, "deviations": deviations, "baseline_profile": profile}, sys.stdout)


if __name__ == "__main__":
    main()

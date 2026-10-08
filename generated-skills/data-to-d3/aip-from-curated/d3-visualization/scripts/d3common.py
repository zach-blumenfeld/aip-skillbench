"""Shared helpers for the d3-visualization scripts (stdlib only).

Every script is run as `python <script>` with cwd = this folder and one JSON object
on stdin ({"currentState", "assets", "expects"}); each writes one JSON object to stdout.
"""
import csv
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
VENDOR_DIR = os.path.normpath(os.path.join(HERE, "..", "assets", "vendor"))
BUNDLED_D3 = {"6": "6.7.0", "7": "7.9.0"}
MISSING_TOKENS = {"", "na", "n/a", "nan", "null", "none", "-"}
NUM_RE = re.compile(r"^[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?$")


def read_stdin():
    raw = sys.stdin.read()
    data = json.loads(raw) if raw.strip() else {}
    return data.get("currentState", data), data.get("assets", {})


def emit(obj):
    sys.stdout.write(json.dumps(obj, ensure_ascii=False))
    sys.stdout.write("\n")


def is_missing(v):
    return v is None or str(v).strip().lower() in MISSING_TOKENS


def to_number(v):
    if is_missing(v):
        return None
    s = str(v).strip().replace(",", "")
    if NUM_RE.match(s):
        f = float(s)
        if f != f or f in (float("inf"), float("-inf")):
            return None
        return f
    return None


def read_table(path):
    """Read CSV/TSV/JSON into (columns, rows as dicts of raw strings/values).

    Pandas-style exports start with an unnamed index column (header cell ''); it is
    kept under the name '' so callers can see and ignore it.
    """
    ext = os.path.splitext(path)[1].lower()
    if ext == ".json":
        with open(path, encoding="utf-8-sig") as f:
            data = json.load(f)
        if isinstance(data, dict):
            for v in data.values():
                if isinstance(v, list):
                    data = v
                    break
        rows = [r for r in data if isinstance(r, dict)]
        cols = []
        for r in rows:
            for k in r:
                if k not in cols:
                    cols.append(k)
        return cols, rows
    with open(path, encoding="utf-8-sig", newline="") as f:
        text = f.read()
    delim = "\t" if ext == ".tsv" else ","
    if ext not in (".csv", ".tsv"):
        try:
            delim = csv.Sniffer().sniff(text[:4096], delimiters=",\t;|").delimiter
        except csv.Error:
            delim = ","
    reader = csv.reader(io.StringIO(text), delimiter=delim)
    header = next(reader, [])
    rows = []
    for rec in reader:
        if not rec or all(not c.strip() for c in rec):
            continue
        rows.append({header[i]: (rec[i] if i < len(rec) else "") for i in range(len(header))})
    return header, rows


def find_column(columns, name):
    """Exact match first, then case/space/underscore-insensitive."""
    if name in columns:
        return name
    norm = lambda s: re.sub(r"[\s_\-]+", "", str(s).lower())
    for c in columns:
        if norm(c) == norm(name):
            return c
    return None


def find_file_for_key(directory, key):
    """Per-entity files may differ in case from the key (e.g. key SPY -> spy.csv)."""
    try:
        names = sorted(os.listdir(directory))
    except OSError:
        return None
    for n in names:
        if os.path.splitext(n)[0] == str(key):
            return os.path.join(directory, n)
    for n in names:
        if os.path.splitext(n)[0].lower() == str(key).lower():
            return os.path.join(directory, n)
    return None


def d3_header_version(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            head = f.read(300)
    except OSError:
        return None
    m = re.search(r"d3js\.org v?(\d+\.\d+\.\d+)", head) or re.search(r'version\s*=\s*"(\d+\.\d+\.\d+)"', head)
    return m.group(1) if m else None


def vendor_d3(version, dest):
    """Place a pinned D3 UMD bundle at dest without touching a CDN at page runtime.

    Order: bundled copy in assets/vendor (6.7.0, 7.9.0) -> node_modules on disk ->
    `npm pack` -> download from jsdelivr/unpkg (build time only). Returns (path, version, source).
    """
    version = str(version or "6").lstrip("v")
    major = version.split(".")[0]
    exact = version if version.count(".") == 2 else BUNDLED_D3.get(major)
    os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
    if exact:
        bundled = os.path.join(VENDOR_DIR, f"d3.v{exact}.min.js")
        if os.path.exists(bundled):
            shutil.copyfile(bundled, dest)
            return dest, exact, "bundled:" + os.path.basename(bundled)
    candidates = [
        os.path.join(os.getcwd(), "node_modules/d3/dist/d3.min.js"),
        "/root/node_modules/d3/dist/d3.min.js",
        "/usr/lib/node_modules/d3/dist/d3.min.js",
        "/usr/local/lib/node_modules/d3/dist/d3.min.js",
    ]
    for c in candidates:
        v = d3_header_version(c)
        if v and v.split(".")[0] == major and (not exact or v == exact):
            shutil.copyfile(c, dest)
            return dest, v, "node_modules:" + c
    spec = exact or major
    tmp = tempfile.mkdtemp(prefix="d3pack-")
    try:
        subprocess.run(["npm", "pack", f"d3@{spec}", "--silent"], cwd=tmp, check=True,
                       capture_output=True, timeout=120)
        tgz = [n for n in os.listdir(tmp) if n.endswith(".tgz")][0]
        subprocess.run(["tar", "xzf", tgz], cwd=tmp, check=True, capture_output=True)
        src = os.path.join(tmp, "package", "dist", "d3.min.js")
        shutil.copyfile(src, dest)
        return dest, d3_header_version(dest) or spec, "npm-pack"
    except Exception:
        pass
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    for url in (f"https://cdn.jsdelivr.net/npm/d3@{spec}/dist/d3.min.js",
                f"https://unpkg.com/d3@{spec}/dist/d3.min.js"):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                body = r.read()
            with open(dest, "wb") as f:
                f.write(body)
            return dest, d3_header_version(dest) or spec, "download:" + url
        except Exception:
            continue
    raise RuntimeError(f"Could not obtain d3@{spec}: no bundled copy, no node_modules, npm pack and download failed")


def resolve(base, p):
    if not p:
        return None
    return p if os.path.isabs(p) else os.path.normpath(os.path.join(base, p))


def write_text(path, text):
    """LF line endings, UTF-8, parent dirs created."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text.replace("\r\n", "\n"))

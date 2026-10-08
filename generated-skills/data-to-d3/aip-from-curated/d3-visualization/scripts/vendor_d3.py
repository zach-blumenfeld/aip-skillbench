"""Place a pinned D3 bundle at page_manifest.d3_path (never a CDN link in the page).

State in:  page_manifest {d3_path, d3_version, ...}
State out: page_manifest with d3_version set to the exact version written, d3_vendor_source.
"""
from d3common import emit, read_stdin, vendor_d3


def main():
    state, _ = read_stdin()
    m = dict(state.get("page_manifest") or {})
    if not m.get("d3_path"):
        emit({"page_manifest": m, "d3_vendor_source": "error: page_manifest.d3_path missing"})
        return
    try:
        path, ver, src = vendor_d3(m.get("d3_version") or "6", m["d3_path"])
        m["d3_version"] = ver
        js = m.get("js_paths") or []
        if path not in js:
            m["js_paths"] = [path] + js
        emit({"page_manifest": m, "d3_vendor_source": src})
    except Exception as e:  # noqa: BLE001
        emit({"page_manifest": m, "d3_vendor_source": f"error: {e}"})


if __name__ == "__main__":
    main()

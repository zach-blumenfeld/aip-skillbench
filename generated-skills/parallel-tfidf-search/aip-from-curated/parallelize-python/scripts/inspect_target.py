#!/usr/bin/env python3
"""Inspect sequential Python code and the machine it will run on.

stdin:  {"currentState": {"target_path": str, "profile_command": str, ...}, "assets": {...}, "expects": [...]}
stdout: {"analysis": {...}}

Static AST scan (stdlib only) for parallelization candidates and hotspots, a probe of
the runtime (CPUs incl. cgroup quota, start method, memory, importable packages), and,
when profile_command is non-empty, a cProfile run of the baseline.
"""

import ast
import importlib.util
import json
import multiprocessing as mp
import os
import platform
import shlex
import subprocess
import sys
import time

OPTIONAL_PACKAGES = [
    "numpy", "scipy", "pandas", "numba", "dask", "joblib", "psutil",
    "memory_profiler", "pympler", "tqdm", "aiohttp", "aiofiles", "ijson", "cupy", "jax",
]
IO_CALLS = {
    "requests", "urlopen", "urllib", "httpx", "aiohttp", "socket", "sleep",
    "open", "read_csv", "read_json", "subprocess", "connect", "execute", "fetch",
}
GEN_NAME = ("make_", "generate_", "gen_", "create_", "synth", "random_", "fake_", "build_test", "setup", "main", "_generate")
CONCURRENCY_MODULES = {"multiprocessing", "concurrent", "threading", "asyncio", "joblib", "dask", "numba"}


def resolve(path):
    if not path:
        return None
    if os.path.isabs(path):
        return path if os.path.exists(path) else None
    for base in (os.environ.get("PWD"), os.environ.get("INIT_CWD")):
        if base and os.path.exists(os.path.join(base, path)):
            return os.path.abspath(os.path.join(base, path))
    return None


def src(node):
    try:
        return ast.unparse(node)[:120]
    except Exception:
        return "?"


def iter_names(node):
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}


class Scan(ast.NodeVisitor):
    def __init__(self, fname):
        self.f = fname
        self.loop_stack = []  # (lineno, iter_src, iter_names, target_names)
        self.func = "<module>"
        self.functions = []
        self.hotspots = []
        self.io = []
        self.imports = set()
        self.classes_without_slots = []
        self.lambdas_to_pool = []
        self.globals_mutated = []
        self.string_concat_in_loop = []

    def visit_Import(self, node):
        for a in node.names:
            self.imports.add(a.name.split(".")[0])

    def visit_ImportFrom(self, node):
        if node.module:
            self.imports.add(node.module.split(".")[0])

    def visit_FunctionDef(self, node):
        prev, self.func = self.func, node.name
        loops = [n for n in ast.walk(node) if isinstance(n, (ast.For, ast.While, ast.comprehension))]
        self.functions.append({"name": node.name, "file": self.f, "lines": [node.lineno, getattr(node, "end_lineno", node.lineno)], "loops": len(loops)})
        saved, self.loop_stack = self.loop_stack, []
        self.generic_visit(node)
        self.loop_stack = saved
        self.func = prev

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node):
        has_slots = any(
            isinstance(s, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "__slots__" for t in s.targets)
            for s in node.body
        )
        dc_slots = any("slots=True" in src(d) for d in node.decorator_list)
        if not (has_slots or dc_slots):
            self.classes_without_slots.append({"class": node.name, "file": self.f, "line": node.lineno})
        self.generic_visit(node)

    def visit_Global(self, node):
        self.globals_mutated.append({"names": node.names, "function": self.func, "file": self.f, "line": node.lineno})

    def _loop(self, node, iter_node, target):
        if self.loop_stack:
            outer = self.loop_stack[-1]
            inner_names = iter_names(iter_node)
            # inner collection independent of the outer loop variable -> O(outer x inner)
            if not (inner_names & outer[3]):
                self.hotspots.append({
                    "likely_input_generation": self.func.lower().startswith(GEN_NAME) or "generat" in self.func.lower(),
                    "kind": "nested_loop_independent_collections",
                    "file": self.f, "function": self.func, "line": node.lineno,
                    "outer": outer[1], "inner": src(iter_node),
                    "hint": "O(len(outer) x len(inner)); invert or index (one pass over the inner collection) before parallelizing",
                })
        self.loop_stack.append((node.lineno, src(iter_node), iter_names(iter_node), iter_names(target)))

    def visit_For(self, node):
        self._loop(node, node.iter, node.target)
        for child in node.body + node.orelse:
            self.visit(child)
        self.loop_stack.pop()
        self.visit(node.iter)

    visit_AsyncFor = visit_For

    def _comp(self, node):
        pushed = 0
        for gen in node.generators:
            self._loop(node, gen.iter, gen.target)
            pushed += 1
        self.generic_visit(node)
        for _ in range(pushed):
            self.loop_stack.pop()

    visit_ListComp = visit_SetComp = visit_DictComp = visit_GeneratorExp = _comp

    def visit_AugAssign(self, node):
        if self.loop_stack and isinstance(node.op, ast.Add) and isinstance(node.value, (ast.JoinedStr, ast.Constant)) and isinstance(getattr(node.value, "value", ""), str):
            self.string_concat_in_loop.append({"file": self.f, "line": node.lineno, "function": self.func})
        self.generic_visit(node)

    def visit_Call(self, node):
        name = src(node.func)
        last = name.split(".")[-1]
        first = name.split(".")[0]
        if last in IO_CALLS or first in IO_CALLS:
            self.io.append({"call": name, "file": self.f, "line": node.lineno, "in_loop": bool(self.loop_stack)})
        if last == "pop" and node.args and src(node.args[0]) == "0" and self.loop_stack:
            self.hotspots.append({"kind": "list_pop0_in_loop", "file": self.f, "function": self.func, "line": node.lineno, "hint": "O(n) per pop; use collections.deque.popleft"})
        if last in {"map", "imap", "imap_unordered", "submit", "starmap", "apply_async"} and any(isinstance(a, ast.Lambda) for a in node.args):
            self.lambdas_to_pool.append({"file": self.f, "line": node.lineno, "hint": "lambdas cannot be pickled for process pools; use a module-level function"})
        self.generic_visit(node)


def scan_files(root):
    files = []
    if os.path.isfile(root):
        files = [root]
    else:
        for d, dirs, fs in os.walk(root):
            dirs[:] = [x for x in dirs if not x.startswith(".") and x not in {"__pycache__", "venv", ".venv", "node_modules"}]
            files += [os.path.join(d, f) for f in fs if f.endswith(".py")]
    out = {"files": [], "functions": [], "hotspots": [], "io_calls": [], "imports": [], "classes_without_slots": [],
           "lambdas_to_pool": [], "globals_mutated": [], "string_concat_in_loop": [], "parse_errors": []}
    imports = set()
    for f in sorted(files)[:200]:
        try:
            with open(f, encoding="utf-8", errors="replace") as fh:
                text = fh.read()
            tree = ast.parse(text)
        except Exception as e:  # noqa: BLE001
            out["parse_errors"].append({"file": f, "error": str(e)[:200]})
            continue
        s = Scan(os.path.relpath(f, root if os.path.isdir(root) else os.path.dirname(root)))
        s.visit(tree)
        out["files"].append({"file": s.f, "lines": text.count("\n") + 1})
        for k in ("functions", "hotspots", "classes_without_slots", "lambdas_to_pool", "globals_mutated", "string_concat_in_loop"):
            out[k] += getattr(s, k)
        out["io_calls"] += s.io
        imports |= s.imports
    out["imports"] = sorted(imports)
    out["concurrency_already_used"] = sorted(imports & CONCURRENCY_MODULES)
    out["io_calls_in_loops"] = sum(1 for c in out["io_calls"] if c["in_loop"])
    out["hotspots"] = out["hotspots"][:40]
    out["io_calls"] = out["io_calls"][:40]
    return out


def cgroup_cpus():
    try:
        with open("/sys/fs/cgroup/cpu.max") as f:
            quota, period = f.read().split()[:2]
        if quota != "max":
            return max(1.0, int(quota) / int(period))
    except Exception:  # noqa: BLE001
        pass
    try:
        with open("/sys/fs/cgroup/cpu/cpu.cfs_quota_us") as f:
            q = int(f.read())
        with open("/sys/fs/cgroup/cpu/cpu.cfs_period_us") as f:
            p = int(f.read())
        if q > 0:
            return max(1.0, q / p)
    except Exception:  # noqa: BLE001
        pass
    return None


def memory_mb():
    for path in ("/sys/fs/cgroup/memory.max", "/sys/fs/cgroup/memory/memory.limit_in_bytes"):
        try:
            with open(path) as f:
                v = f.read().strip()
            if v != "max" and int(v) < 1 << 60:
                return {"limit_mb": int(v) // (1 << 20), "source": path}
        except Exception:  # noqa: BLE001
            pass
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal"):
                    return {"limit_mb": int(line.split()[1]) // 1024, "source": "/proc/meminfo"}
    except Exception:  # noqa: BLE001
        pass
    try:
        return {"limit_mb": os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") // (1 << 20), "source": "sysconf"}
    except Exception:  # noqa: BLE001
        return {"limit_mb": None, "source": None}


def environment():
    logical = os.cpu_count() or 1
    try:
        affinity = len(os.sched_getaffinity(0))
    except AttributeError:
        affinity = logical
    quota = cgroup_cpus()
    usable = min([x for x in (logical, affinity, int(quota) if quota else None) if x])
    try:
        methods = mp.get_all_start_methods()
        default = mp.get_start_method(allow_none=True) or methods[0]
    except Exception:  # noqa: BLE001
        methods, default = [], None
    pkgs = {p: importlib.util.find_spec(p) is not None for p in OPTIONAL_PACKAGES}
    return {
        "python": platform.python_version(),
        "platform": sys.platform,
        "cpu_count_logical": logical,
        "cpu_affinity": affinity,
        "cgroup_cpu_quota": quota,
        "usable_cpus": usable,
        "start_methods": methods,
        "default_start_method": default,
        "fork_available": "fork" in methods,
        "memory": memory_mb(),
        "packages": pkgs,
        "stdlib_only": not any(pkgs[p] for p in ("numpy", "scipy", "pandas", "numba", "dask", "joblib")),
    }


def profile(command, cwd, timeout, exe=None):
    args = shlex.split(command)
    if args and os.path.basename(args[0]).startswith("python"):
        args = args[1:]
    if not args:
        return {"ran": False, "reason": "empty command"}
    if args[0] == "-m":
        cmd = [exe or sys.executable, "-m", "cProfile", "-s", "tottime", "-m"] + args[1:]
    else:
        cmd = [exe or sys.executable, "-m", "cProfile", "-s", "tottime"] + args
    t = time.perf_counter()
    try:
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
    except subprocess.TimeoutExpired:
        return {"ran": False, "reason": f"timed out after {timeout}s; profile a smaller input", "command": cmd}
    wall = time.perf_counter() - t
    out = p.stdout.splitlines()
    head = [l for l in out if "function calls" not in l][:15]
    stats_start = next((i for i, l in enumerate(out) if "ncalls" in l and "tottime" in l), None)
    stats = out[stats_start: stats_start + 26] if stats_start is not None else []
    return {
        "ran": p.returncode == 0, "returncode": p.returncode, "wall_seconds": round(wall, 3),
        "program_output_head": head, "top_by_tottime": stats,
        "stderr_tail": p.stderr.splitlines()[-15:],
        "note": "wall time includes cProfile overhead (~1.5-2x); time the baseline without it for speedup math",
    }


def target_python(state):
    exe = (state.get("python_executable") or "").strip()
    if not exe:
        return None
    try:
        out = subprocess.run([exe, os.path.abspath(__file__), "--probe"], capture_output=True, text=True, timeout=120)
        return exe, json.loads(out.stdout)
    except Exception as e:  # noqa: BLE001
        return exe, {"error": f"could not probe {exe}: {e}"}


def main():
    if "--probe" in sys.argv:
        print(json.dumps(environment()))
        return
    payload = json.load(sys.stdin)
    state = payload.get("currentState", payload)
    raw = state.get("target_path", "")
    root = resolve(raw)
    if root is None:
        print(json.dumps({"error": f"target_path {raw!r} not found; pass an absolute path to the sequential code (file or directory)"}))
        sys.exit(1)
    probed = target_python(state)
    env = probed[1] if probed and "error" not in probed[1] else environment()
    env["probed_interpreter"] = probed[0] if probed and "error" not in probed[1] else sys.executable
    if probed and "error" in probed[1]:
        env["probe_error"] = probed[1]["error"]
    elif not probed:
        env["probe_note"] = "Probed the interpreter running this script; if the task runs under a different python (e.g. a container's), pass python_executable or re-check start method / CPUs / packages there."
    analysis = {"target_path": root, "environment": env, "static": scan_files(root)}
    cmd = (state.get("profile_command") or "").strip()
    if cmd:
        cwd = root if os.path.isdir(root) else os.path.dirname(root)
        analysis["profile"] = profile(cmd, cwd, int(state.get("profile_timeout", 600)), env.get("probed_interpreter"))
    else:
        analysis["profile"] = {"ran": False, "reason": "no profile_command given; profile in the characterize step"}
    print(json.dumps({"analysis": analysis}))


if __name__ == "__main__":
    main()

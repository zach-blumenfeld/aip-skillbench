#!/usr/bin/env python3
"""Run the Maven build (or read an existing log) and diagnose the failure.

stdin:  {"currentState": {"project_dir", "build_command", "jdk", "round", ...},
         "assets": {"failure_catalog": "<json>"}, "expects": [...]}
Optional state keys:
  external_log_path      diagnose this log instead of running the build (use when you ran Maven yourself)
  build_timeout_seconds  overrides the catalog default
  log_dir                where build logs go (default from the catalog; never inside the project)
  original_build_command set automatically on the first round
stdout: build_outcome ("passed" | "failed" | "exhausted"), failure_category, diagnosis, round, ...

Standard library only (Python 3.6+).
"""
import json
import os
import re
import signal
import subprocess
import sys
import time

ANSI = re.compile(r"\x1b\[[0-9;]*m")
FAILED_GOAL = re.compile(
    r"Failed to execute goal (?:(?P<group>[\w.\-]+):)?(?P<artifact>[\w.\-]+):(?P<version>[\w.\-]+):(?P<goal>[\w\-]+)"
    r"(?: \((?P<exec>[^)]*)\))? on project (?P<module>[\w.\-]+): ?(?P<msg>.*)")
NO_GOAL = re.compile(r"Failed to execute goal on project (?P<module>[\w.\-]+): ?(?P<msg>.*)")
COMPILE_ERR = re.compile(r"^\[ERROR\] (?P<file>/?[^\s:\[]+\.java):\[(?P<line>\d+),(?P<col>\d+)\] (?P<msg>.*)$")
JAVAC_ERR = re.compile(r"^(?P<file>/?\S+\.java):(?P<line>\d+): error: (?P<msg>.*)$")
TESTS_RUN = re.compile(r"Tests run: (\d+), Failures: (\d+), Errors: (\d+), Skipped: (\d+)")
REACTOR = re.compile(r"^\[INFO\] (?P<name>.+?) \.{2,}\s*(?P<status>SUCCESS|FAILURE|SKIPPED)")
SKIP_FLAGS = ("-DskipTests", "-Dmaven.test.skip", "-Dtest.skip", "-DskipITs", "-Dmaven.test.failure.ignore", "-fae", "--fail-never", "-fn")
SWITCHER = "/opt/jdk_switcher/jdk_switcher.sh"


def jdk_prefix(jdk):
    """Shell prefix that selects the JDK. Accepts a jdk_switcher alias, a JAVA_HOME path, or 'jdkN'."""
    jdk = (jdk or "").strip()
    if not jdk:
        return "", "JDK left as the environment default"
    if jdk.startswith("/"):
        return 'export JAVA_HOME="%s" PATH="%s/bin:$PATH" && ' % (jdk, jdk), "JAVA_HOME=%s" % jdk
    if os.path.isfile(SWITCHER) and re.match(r"^(open|oracle)jdk\d+$", jdk):
        return "source %s >/dev/null 2>&1; jdk_switcher use %s && " % (SWITCHER, jdk), "jdk_switcher use %s" % jdk
    m = re.search(r"(\d+)$", jdk)
    if m and os.path.isdir("/usr/lib/jvm"):
        n = m.group(1)
        dirs = sorted(d for d in os.listdir("/usr/lib/jvm")
                      if re.search(r"(^|[^\d.])(1\.)?%s([^\d]|$)" % n, d) and os.path.isdir(os.path.join("/usr/lib/jvm", d)))
        if dirs:
            p = os.path.join("/usr/lib/jvm", dirs[0])
            return 'export JAVA_HOME="%s" PATH="%s/bin:$PATH" && ' % (p, p), "JAVA_HOME=%s" % p
    return "", "could not map jdk %r to an installed JDK; left default" % jdk


def maven_home_env(env):
    """Point HOME at the user whose ~/.m2 already holds the cached repository (CI images cache under /home/travis)."""
    home = env.get("HOME", os.path.expanduser("~"))
    if os.path.isdir(os.path.join(home, ".m2", "repository")):
        return env, None
    for cand in ("/home/travis", "/root"):
        if cand != home and os.path.isdir(os.path.join(cand, ".m2", "repository")):
            env = dict(env)
            env["HOME"] = cand
            return env, "HOME set to %s so Maven uses its populated ~/.m2" % cand
    return env, None


def run(state, catalog, log_path):
    cmd = state["build_command"]
    prefix, jdk_note = jdk_prefix(state.get("jdk", ""))
    env, home_note = maven_home_env(dict(os.environ))
    env.setdefault("MAVEN_OPTS", "")
    timeout = int(state.get("build_timeout_seconds") or catalog.get("build_timeout_seconds", 3000))
    full = prefix + "java -version 2>&1 | head -1; " + cmd
    start = time.time()
    with open(log_path, "wb") as log:
        log.write(("$ (cwd=%s) %s\n" % (state["project_dir"], full)).encode())
        log.flush()
        try:
            proc = subprocess.Popen(["bash", "-c", full], cwd=state["project_dir"], stdout=log,
                                    stderr=subprocess.STDOUT, env=env, preexec_fn=os.setsid)
        except OSError as exc:
            log.write(("could not start build: %s\n" % exc).encode())
            return 127, False, [jdk_note, home_note], 0
        timed_out = False
        try:
            code = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(proc.pid, signal.SIGKILL)
            code = proc.wait()
            log.write(("\n[aip] build killed after %ss timeout\n" % timeout).encode())
    return code, timed_out, [jdk_note, home_note], round(time.time() - start)


def first_lines(lines, pred, n):
    out = []
    for l in lines:
        if pred(l):
            out.append(l)
            if len(out) >= n:
                break
    return out


def classify(error_text, failing, catalog):
    matched = []
    for cat in catalog["categories"]:
        for pat in cat["patterns"]:
            if re.search(pat, error_text):
                matched.append(cat["id"])
                break
    by_plugin = {
        "maven-surefire-plugin": "test-failure", "maven-failsafe-plugin": "test-failure",
        "maven-compiler-plugin": "compilation", "maven-enforcer-plugin": "enforcer",
        "maven-javadoc-plugin": "javadoc", "maven-resources-plugin": "resources",
    }
    primary = matched[0] if matched else None
    if failing:
        plug = by_plugin.get(failing.get("artifact"))
        # The failing plugin narrows the category when the generic patterns disagree with it.
        if plug == "test-failure" and primary not in ("test-failure", "test-fork-crash", "out-of-memory", "jdk-mismatch"):
            primary = "test-fork-crash" if "test-fork-crash" in matched else "test-failure"
        elif plug == "compilation" and primary not in ("compilation", "jdk-mismatch", "annotation-processing", "out-of-memory"):
            primary = "compilation"
        elif plug and primary is None:
            primary = plug
    return primary or "unknown", matched


def diagnose(log_text, code, timed_out, catalog, state):
    raw = ANSI.sub("", log_text).splitlines()
    success = any("BUILD SUCCESS" in l for l in raw)
    failure = any("BUILD FAILURE" in l for l in raw)
    passed = code == 0 and not failure and not timed_out
    err_lines = [l for l in raw if l.startswith("[ERROR]") or "<<< FAILURE" in l or "<<< ERROR" in l
                 or JAVAC_ERR.match(l) or l.startswith("Caused by:")
                 or re.match(r"^\[WARNING\] Rule \d+: .* failed with message", l)
                 or l.startswith("Dependency convergence error")]
    error_text = "\n".join(err_lines) if err_lines else "\n".join(raw[-80:])
    failing = None
    for l in raw:
        m = FAILED_GOAL.search(l)
        if m:
            failing = m.groupdict()
            break
        m = NO_GOAL.search(l)
        if m:  # resolution failures happen before any plugin goal runs
            failing = {"group": "", "artifact": "", "version": "", "goal": "", "exec": "",
                       "module": m.group("module"), "msg": m.group("msg")}
            break
    if timed_out:
        category, matched = "timeout", []
    elif passed:
        category, matched = "none", []
    elif code == 127 or any(re.search(r"(mvn|java|mvnw): (command )?not found", l) for l in raw[:20]):
        category, matched = "tooling-missing", []
    else:
        category, matched = classify(error_text, failing, catalog)

    goal_key = phase = None
    if failing and failing["artifact"]:
        short = re.sub(r"^maven-|-maven-plugin$|-plugin$", "", failing["artifact"])
        goal_key = "%s:%s" % (short, failing["goal"])
        phase = catalog["goal_phase"].get(goal_key)
    compile_errors = []
    for i, l in enumerate(raw):
        m = COMPILE_ERR.match(l) or JAVAC_ERR.match(l)
        if m:
            e = "%s:%s %s" % (m.group("file"), m.group("line"), m.group("msg"))
            # javac puts symbol/location/required/found on the following indented lines
            for nxt in raw[i + 1:i + 5]:
                t = nxt.replace("[ERROR]", "").strip()
                if re.match(r"^(symbol|location|required|found|reason)\b", t):
                    e += " | " + t
                else:
                    break
            if e not in compile_errors:
                compile_errors.append(e)
    failed_tests = []
    in_section = False
    for l in raw:
        s = l.replace("[ERROR] ", "")
        hdr = re.match(r"^(Failed tests|Tests in error|Failures|Errors|Crashed tests):\s*(.*)$", s)
        if hdr:
            in_section = True
            if hdr.group(2).strip() and len(failed_tests) < 40:
                failed_tests.append(hdr.group(2).strip()[:300])
            continue
        if in_section:
            if not s.strip() or s.startswith("Tests run:") or s.startswith("[INFO]"):
                in_section = False
                continue
            t = s.strip()
            if t and not t.startswith("Run ") and len(failed_tests) < 40:
                failed_tests.append(t[:300])
        m = re.match(r"^(?:\[ERROR\] )?(?:Tests run:.*?<<< (?:FAILURE|ERROR)! - in |)(\S+)\s.*<<< (FAILURE|ERROR)!", l)
        if m and len(failed_tests) < 40 and m.group(1) not in failed_tests:
            failed_tests.append(l.strip()[:300])
    reactor = [m.group("name") + ": " + m.group("status") for m in (REACTOR.match(l) for l in raw) if m]

    base = re.search(r"(\./mvnw|mvn)\b", state["build_command"])
    mvn = base.group(1) if base else "mvn"
    fflag = re.search(r"\s(-f|--file)\s+(\S+)", state["build_command"])
    focused = ""
    if failing and not passed:
        focused = "%s -B -e %s -pl :%s -am%s" % (mvn, phase or "install", failing["module"],
                                               " -f %s" % fflag.group(2) if fflag else "")
        if category == "test-failure":
            focused += "  (single test: add -Dtest=<Class>#<method> -DfailIfNoTests=false)"
    excerpt = first_lines(err_lines, lambda l: True, 60) or raw[-60:]
    cat = next((c for c in catalog["categories"] if c["id"] == category), None)
    playbook = cat["playbook"] if cat else {
        "none": "Build passed.",
        "timeout": "The build exceeded the timeout. Check the log tail for a hang (a test waiting on network, a stuck fork); rerun the failing module only with the focused command, or raise build_timeout_seconds in the state.",
        "tooling-missing": "mvn or java is not on PATH for the build shell. Locate them (ls /usr/share/maven/bin /usr/lib/jvm; source /etc/profile) and fix build_command or jdk in the state.",
        "unknown": "No catalog pattern matched. Read the full log around the first [ERROR] and the 'Failed to execute goal' line; rerun with -e (stack trace) or -X (debug) for more detail.",
    }.get(category, "")
    return {
        "passed": passed,
        "category": category,
        "matched": matched,
        "layer_hint": cat["layer_hint"] if cat else ("none" if passed else "unknown"),
        "playbook": playbook,
        "failing_goal": ("%s:%s:%s:%s" % (failing.get("group") or "", failing["artifact"], failing["version"], failing["goal"])).lstrip(":") if failing and failing["artifact"] else "",
        "failing_module": failing["module"] if failing else "",
        "failing_phase": phase or "",
        "failure_message": (failing["msg"][:600] if failing else ""),
        "compile_errors": compile_errors[:40],
        "failed_tests": failed_tests,
        "tests_summary": [l.strip() for l in raw if TESTS_RUN.search(l) and ("Failures: 0, Errors: 0" not in l)][:20],
        "reactor_summary": reactor,
        "error_excerpt": excerpt,
        "log_tail": raw[-40:],
        "focused_command": focused,
        "build_success_marker": success,
    }


def main():
    payload = json.load(sys.stdin)
    state = payload.get("currentState", {})
    assets = payload.get("assets", {})
    catalog = assets.get("failure_catalog")
    catalog = json.loads(catalog) if isinstance(catalog, str) else catalog
    rnd = int(state.get("round", 0) or 0) + 1
    original = state.get("original_build_command") or state["build_command"]
    log_dir = state.get("log_dir") or catalog.get("log_dir", "/tmp/aip-maven-build-fix")
    notes = []
    ext = (state.get("external_log_path") or "").strip()
    if ext:
        log_path = ext
        with open(ext, "r", errors="replace") as fh:
            text = fh.read()
        code = 0 if ("BUILD SUCCESS" in text and "BUILD FAILURE" not in text) else 1
        timed_out, secs = False, 0
        notes.append("diagnosed external log %s (no build run)" % ext)
    else:
        try:
            os.makedirs(log_dir, exist_ok=True)
        except OSError:
            log_dir = "/tmp"
        log_path = os.path.join(log_dir, "build-round-%d.log" % rnd)
        code, timed_out, run_notes, secs = run(state, catalog, log_path)
        notes += [n for n in run_notes if n]
        with open(log_path, "r", errors="replace") as fh:
            text = fh.read()
        seen = re.search(r'^(?:openjdk|java) version "?([^"\s]+)', text, re.M)
        notes.append("java that ran the build: %s (check it matches jdk %r)"
                     % (seen.group(1) if seen else "unknown", state.get("jdk", "")))
    d = diagnose(text, code, timed_out, catalog, state)
    added_skips = [f for f in SKIP_FLAGS if f in state["build_command"] and f not in original]
    if added_skips:
        notes.append("WARNING: build_command adds %s that the original command did not use; a green build "
                     "obtained this way does not count as fixed" % ", ".join(added_skips))
    max_rounds = int(catalog.get("max_rounds", 8))
    if d["passed"] and not added_skips:
        outcome = "passed"
    elif rnd >= max_rounds:
        outcome = "exhausted"
    else:
        outcome = "failed"
    print(json.dumps({
        "build_outcome": outcome,
        "failure_category": d["category"],
        "fix_playbook": d["playbook"],
        "first_error": next((l for l in d["error_excerpt"] if l.strip() not in ("[ERROR]", "[ERROR] COMPILATION ERROR :")), "")[:800],
        "diagnosis": d,
        "build_log_path": log_path,
        "build_exit_code": code,
        "build_seconds": secs,
        "run_notes": notes,
        "round": rnd,
        "original_build_command": original,
    }))


if __name__ == "__main__":
    main()

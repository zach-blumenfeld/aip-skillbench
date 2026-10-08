#!/usr/bin/env python3
"""Inspect a Maven project and its environment before reproducing a failed build.

stdin:  {"currentState": {"project_dir": str, "failure_report": str, ...}, "assets": {...}, "expects": [...]}
stdout: {"project_dir", "project_facts", "pom_findings", "build_command", "jdk", "round"}

Standard library only (Python 3.6+): the task container may have nothing else.
"""
import glob
import json
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

SEARCH_ROOTS = [
    "/home/travis/build/failed",
    "/home/travis/build",
    "/root",
    "/workspace",
    "/app",
    "/home",
]
SKIP_DIRS = {".git", "target", "node_modules", ".m2", ".idea", "build", "out"}
CENTRAL_HTTP = re.compile(r"^http://(repo1?\.maven\.org|repo\.maven\.apache\.org|central\.maven\.org)", re.I)
VERSION_RANGE = re.compile(r"^[\[\(].*[\]\)]$")
TRAVIS_CMD_KEYS = ("before_install", "install", "before_script", "script", "env", "after_success")
PROP_REF = re.compile(r"\$\{([^}]+)\}")


def strip_ns(root):
    for el in root.iter():
        if isinstance(el.tag, str) and "}" in el.tag:
            el.tag = el.tag.split("}", 1)[1]
    return root


def text(el, path, default=None):
    if el is None:
        return default
    found = el.find(path)
    if found is None or found.text is None:
        return default
    return found.text.strip()


def parse_pom(path):
    try:
        return strip_ns(ET.parse(path).getroot()), None
    except Exception as exc:  # malformed POM is itself a finding
        return None, "%s: %s" % (path, exc)


def find_project_dir(given):
    cands = []
    if given:
        cands.append(given)
    cands.append(os.getcwd())
    for c in cands:
        if c and os.path.isdir(c) and aggregator_poms(c):
            return os.path.abspath(c)
    for root in SEARCH_ROOTS:
        if not os.path.isdir(root):
            continue
        for depth in range(0, 4):
            pattern = os.path.join(root, *(["*"] * depth))
            hits = sorted(d for d in glob.glob(pattern) if os.path.isdir(d) and aggregator_poms(d))
            if hits:
                return os.path.abspath(hits[0])
    return os.path.abspath(given) if given else os.getcwd()


def aggregator_poms(d):
    """Root-level POM files. Some projects (e.g. google/auto) aggregate modules in build-pom.xml, not pom.xml."""
    out = []
    for f in sorted(os.listdir(d)) if os.path.isdir(d) else []:
        p = os.path.join(d, f)
        if not (os.path.isfile(p) and f.endswith(".xml")):
            continue
        if f == "pom.xml" or "pom" in f.lower():
            try:
                with open(p, "r", errors="replace") as fh:
                    head = fh.read(20000)
            except OSError:
                continue
            if "<project" in head:
                out.append(f)
    return out


def collect_reactor(project_dir, root_pom_file):
    """Walk <modules> recursively from the root POM; return [(path, root_el_or_None, err)]."""
    seen, out = set(), []
    stack = [os.path.join(project_dir, root_pom_file)]
    while stack:
        p = os.path.normpath(stack.pop(0))
        if p in seen:
            continue
        seen.add(p)
        if not os.path.isfile(p):
            out.append((p, None, "module POM missing: %s" % p))
            continue
        root, err = parse_pom(p)
        out.append((p, root, err))
        if root is None:
            continue
        mods = [m.text.strip() for m in root.findall("modules/module") if m.text]
        for prof in root.findall("profiles/profile"):
            mods += [m.text.strip() for m in prof.findall("modules/module") if m.text]
        for m in mods:
            mp = os.path.join(os.path.dirname(p), m)
            stack.append(mp if mp.endswith(".xml") else os.path.join(mp, "pom.xml"))
    return out


def gav(el):
    return "%s:%s" % (text(el, "groupId", "org.apache.maven.plugins" if el.tag == "plugin" else "?"),
                      text(el, "artifactId", "?"))


def lint_pom(path, root, rel, props_all, managed_all, has_bom):
    findings = []

    def add(kind, msg):
        findings.append({"pom": rel, "kind": kind, "detail": msg})

    props = {c.tag: (c.text or "").strip() for c in root.findall("properties/*")}
    # plugins without versions (Common pitfall: Missing Versions)
    managed_plugins = {gav(p) for p in root.findall("build/pluginManagement/plugins/plugin") if text(p, "version")}
    for p in root.iter("plugin"):
        if text(p, "version") is None and gav(p) not in managed_plugins and gav(p) not in managed_all.get("plugins", set()):
            add("plugin-without-version", "%s has no <version> here or in reactor pluginManagement (pin it)" % gav(p))
    # dependency checks
    seen = {}
    for parent_tag in ("dependencies", "dependencyManagement/dependencies"):
        for d in root.findall(parent_tag + "/dependency"):
            key = gav(d) + ":" + text(d, "type", "jar") + ":" + text(d, "classifier", "")
            v = text(d, "version")
            scope = text(d, "scope", "compile")
            if parent_tag == "dependencies":
                if key in seen:
                    add("duplicate-dependency", "%s declared twice in <dependencies>" % gav(d))
                seen[key] = v
                if v is None and gav(d) not in managed_all.get("deps", set()) and not has_bom:
                    add("missing-dependency-version", "%s has no version and no dependencyManagement entry in the reactor" % gav(d))
            if v:
                if v in ("LATEST", "RELEASE"):
                    add("floating-version", "%s uses %s (pin an exact version)" % (gav(d), v))
                elif VERSION_RANGE.match(v):
                    add("version-range", "%s uses range %s (pin an exact version)" % (gav(d), v))
                elif v.endswith("-SNAPSHOT") and not gav(d).startswith(text(root, "groupId", text(root, "parent/groupId", "\0"))):
                    add("external-snapshot", "%s:%s is an external SNAPSHOT (may no longer resolve)" % (gav(d), v))
                for ref in PROP_REF.findall(v):
                    if not ref.startswith(("project.", "pom.", "env.", "settings.")) and ref not in props_all:
                        add("undefined-property", "%s version references undefined ${%s}" % (gav(d), ref))
            if scope == "system":
                add("system-scope", "%s uses system scope with systemPath %s (non-portable)" % (gav(d), text(d, "systemPath")))
    # repositories over plain http (Central has required HTTPS since 2020-01-15 -> 501)
    for r in list(root.iter("repository")) + list(root.iter("pluginRepository")):
        url = text(r, "url", "")
        if url.startswith("http://"):
            add("http-repository", "repository %s uses %s (use https; Central returns 501 for http)" % (text(r, "id"), url))
    return findings, props


def compiler_levels(roots):
    out = {}
    for path, root in roots:
        for k in ("maven.compiler.source", "maven.compiler.target", "maven.compiler.release", "java.version"):
            v = text(root, "properties/" + k)
            if v:
                out.setdefault(k, set()).add(v)
        for p in root.iter("plugin"):
            if text(p, "artifactId") == "maven-compiler-plugin":
                for k in ("source", "target", "release"):
                    v = text(p, "configuration/" + k)
                    if v:
                        out.setdefault("compiler-plugin." + k, set()).add(v)
                v = text(p, "version")
                if v:
                    out.setdefault("compiler-plugin.version", set()).add(v)
    return {k: sorted(v) for k, v in out.items()}


def profiles(roots, rel):
    out = []
    for path, root in roots:
        for prof in root.findall("profiles/profile"):
            act = prof.find("activation")
            trig = {}
            if act is not None:
                for c in act:
                    if c.tag == "property":
                        trig["property"] = "%s=%s" % (text(c, "name"), text(c, "value", "*"))
                    elif c.tag == "file":
                        trig["file"] = text(c, "exists") or ("missing:" + str(text(c, "missing")))
                    elif c.tag == "os":
                        trig["os"] = ",".join("%s=%s" % (x.tag, (x.text or "").strip()) for x in c)
                    else:
                        trig[c.tag] = (c.text or "").strip()
            out.append({"pom": rel(path), "id": text(prof, "id"), "activation": trig})
    return out


def parse_travis(project_dir):
    p = os.path.join(project_dir, ".travis.yml")
    if not os.path.isfile(p):
        return None
    info, key = {"jdk": [], "commands": {}}, None
    with open(p, "r", errors="replace") as fh:
        lines = fh.read().splitlines()
    for line in lines:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        m = re.match(r"^([A-Za-z_]+):\s*(.*)$", line)
        if m:
            key, val = m.group(1), m.group(2).strip()
            if val:
                if key == "jdk":
                    info["jdk"].append(val)
                elif key in TRAVIS_CMD_KEYS:
                    info["commands"].setdefault(key, []).append(val.strip("'\""))
            continue
        m = re.match(r"^\s*-\s*(.+)$", line)
        if m and key:
            val = m.group(1).strip().strip("'\"")
            if key == "jdk":
                info["jdk"].append(val)
            elif key in TRAVIS_CMD_KEYS:
                info["commands"].setdefault(key, []).append(val)
        m = re.match(r"^\s+-?\s*jdk:\s*(\S+)", line)
        if m:
            info["jdk"].append(m.group(1))
    info["raw"] = "\n".join(lines[:80])
    return info


def environment():
    env = {}
    jvm = "/usr/lib/jvm"
    env["jdks"] = sorted(os.listdir(jvm)) if os.path.isdir(jvm) else []
    env["jdk_switcher"] = os.path.isfile("/opt/jdk_switcher/jdk_switcher.sh")
    env["java_home"] = os.environ.get("JAVA_HOME", "")
    for cmd, key in ((["mvn", "-v"], "maven"), (["java", "-version"], "java")):
        try:
            r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=30)
            env[key] = r.stdout.decode("utf-8", "replace").strip().splitlines()[:3]
        except Exception as exc:
            env[key] = ["unavailable: %s" % exc]
    home = os.path.expanduser("~")
    homes = [home] + [h for h in ("/home/travis", "/root") if h != home]
    env["m2_repositories"] = [os.path.join(h, ".m2/repository") for h in homes if os.path.isdir(os.path.join(h, ".m2/repository"))]
    settings = [os.path.join(h, ".m2/settings.xml") for h in homes if os.path.isfile(os.path.join(h, ".m2/settings.xml"))]
    env["settings_files"] = settings
    mirrors = []
    for s in settings:
        root, _ = parse_pom(s)
        if root is not None:
            for m in root.iter("mirror"):
                mirrors.append("%s -> %s (mirrorOf %s)" % (text(m, "id"), text(m, "url"), text(m, "mirrorOf")))
            if text(root, "offline") == "true":
                mirrors.append("settings.xml sets <offline>true</offline>")
    env["settings_mirrors"] = mirrors
    return env


def jdk_hint(travis, levels, env):
    """Prefer the JDK the original CI used; else the lowest installed JDK that supports the source level."""
    if travis and travis["jdk"]:
        return travis["jdk"][0]
    lvls = []
    for k, vs in levels.items():
        if k.endswith(("source", "target", "release", "java.version")):
            for v in vs:
                m = re.match(r"^(?:1\.)?(\d+)$", v)
                if m:
                    lvls.append(int(m.group(1)))
    want = max(lvls) if lvls else None
    if want is None:
        return ""
    if want <= 8:
        return "openjdk8" if any("8" in j for j in env["jdks"]) else ""
    return "jdk%d" % want


def build_command(project_dir, root_pom, travis, has_wrapper):
    if travis:
        for key in ("script", "install"):
            for c in travis["commands"].get(key, []):
                if re.search(r"\b(mvn|mvnw)\b", c):
                    return c
    mvn = "./mvnw" if has_wrapper else "mvn"
    f = "" if root_pom == "pom.xml" else " -f %s" % root_pom
    if travis:
        # Travis CI's default for a Maven project with no script/install override.
        return ("%s install -DskipTests=true -Dmaven.javadoc.skip=true -B -V%s && %s test -B%s"
                % (mvn, f, mvn, f))
    return "%s -B -e%s clean install" % (mvn, f)


def main():
    payload = json.load(sys.stdin)
    state = payload.get("currentState", {})
    project_dir = find_project_dir(state.get("project_dir", ""))
    poms = aggregator_poms(project_dir)
    facts = {"project_dir": project_dir, "root_pom_files": poms}
    if not poms:
        facts["error"] = "No POM found in %s or the usual roots; set project_dir to the folder holding the root pom." % project_dir
        print(json.dumps({"project_dir": project_dir, "project_facts": facts, "pom_findings": [],
                          "build_command": "mvn -B -e clean install", "jdk": "", "round": 0}))
        return
    # The aggregator is the root POM file with <modules>; prefer pom.xml when it has them.
    root_pom = "pom.xml" if "pom.xml" in poms else poms[0]
    for f in (["pom.xml"] if "pom.xml" in poms else []) + [p for p in poms if p != "pom.xml"]:
        r, _ = parse_pom(os.path.join(project_dir, f))
        if r is not None and r.find("modules") is not None:
            root_pom = f
            break
    travis = parse_travis(project_dir)
    if travis:
        for c in sum(travis["commands"].values(), []):
            m = re.search(r"\s-f\s+(\S+)", c)
            if m and os.path.isfile(os.path.join(project_dir, m.group(1))):
                root_pom = m.group(1)
                break
    reactor = collect_reactor(project_dir, root_pom)
    rel = lambda p: os.path.relpath(p, project_dir)
    parsed = [(p, r) for p, r, e in reactor if r is not None]
    findings = [{"pom": rel(p), "kind": "pom-unreadable", "detail": e} for p, r, e in reactor if e]

    props_all, managed = set(), {"deps": set(), "plugins": set()}
    has_bom = False
    for p, r in parsed:
        props_all |= {c.tag for c in r.findall("properties/*")}
        for d in r.findall("dependencyManagement/dependencies/dependency"):
            managed["deps"].add(gav(d))
            if text(d, "scope") == "import":
                has_bom = True
        for pl in r.findall("build/pluginManagement/plugins/plugin"):
            if text(pl, "version"):
                managed["plugins"].add(gav(pl))
        if r.find("parent") is not None and text(r, "parent/relativePath") is None:
            # an external parent (e.g. oss-parent, spring-boot-starter-parent) may manage versions we cannot see
            if not os.path.isfile(os.path.join(os.path.dirname(p), "..", "pom.xml")):
                has_bom = True
    modules = []
    for p, r in parsed:
        f, _ = lint_pom(p, r, rel(p), props_all, managed, has_bom)
        findings += f
        modules.append({
            "pom": rel(p),
            "artifactId": text(r, "artifactId"),
            "packaging": text(r, "packaging", "jar"),
            "parent": text(r, "parent/artifactId"),
            "version": text(r, "version", text(r, "parent/version")),
        })
    env = environment()
    levels = compiler_levels(parsed)
    has_wrapper = os.path.isfile(os.path.join(project_dir, "mvnw"))
    facts.update({
        "root_pom": root_pom,
        "modules": modules,
        "compiler_levels": levels,
        "profiles": profiles(parsed, rel),
        "travis": travis,
        "maven_wrapper": has_wrapper,
        "mvn_config": [f for f in (".mvn/maven.config", ".mvn/jvm.config") if os.path.isfile(os.path.join(project_dir, f))],
        "git_status": git_status(project_dir),
        "environment": env,
        "failure_report": state.get("failure_report", ""),
    })
    print(json.dumps({
        "project_dir": project_dir,
        "project_facts": facts,
        "pom_findings": findings,
        "build_command": build_command(project_dir, root_pom, travis, has_wrapper),
        "jdk": jdk_hint(travis, levels, env),
        "round": 0,
    }))


def git_status(d):
    try:
        r = subprocess.run(["git", "-C", d, "log", "-1", "--oneline"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15)
        s = subprocess.run(["git", "-C", d, "status", "--short"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15)
        return {"head": r.stdout.decode("utf-8", "replace").strip(), "dirty": s.stdout.decode("utf-8", "replace").splitlines()[:30]}
    except Exception:
        return {}


if __name__ == "__main__":
    main()

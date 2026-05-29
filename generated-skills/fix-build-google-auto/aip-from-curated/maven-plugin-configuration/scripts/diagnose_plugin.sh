#!/usr/bin/env bash
# Parse a Maven build log and extract the failing plugin coordinates, goal,
# and the surrounding error context. Emits a single JSON object on stdout.
#
# Usage:
#   diagnose_plugin.sh <maven.log>
#   mvn ... | diagnose_plugin.sh -          # read from stdin
#
# Output schema:
#   {
#     "failed": true|false,
#     "plugin_group": "...",
#     "plugin_artifact": "...",
#     "plugin_version": "...",
#     "goal": "...",
#     "execution_id": "...",        // may be null
#     "module": "...",              // may be null
#     "error_lines": ["...", ...],  // up to 40 trailing [ERROR] lines
#     "hints": ["...", ...]         // matched categories from the playbook
#   }

set -euo pipefail

if [[ $# -lt 1 ]]; then
    echo "usage: $0 <maven.log|->" >&2
    exit 2
fi

src="$1"
if [[ "$src" == "-" ]]; then
    LOG_CONTENT="$(cat)"
else
    LOG_CONTENT="$(cat "$src")"
fi
export LOG_CONTENT

python3 - <<'PY'
import json
import os
import re
import sys

log = os.environ.get("LOG_CONTENT", "")

# `[ERROR] Failed to execute goal <g>:<a>:<v>:<goal> (<exec-id>) on project <module>: ...`
fail_re = re.compile(
    r"\[ERROR\]\s+Failed to execute goal\s+"
    r"(?P<group>[\w.\-]+):(?P<artifact>[\w.\-]+):(?P<version>[\w.\-]+):(?P<goal>[\w.\-]+)"
    r"(?:\s*\((?P<exec>[^)]+)\))?"
    r"(?:\s+on project\s+(?P<module>[\w.\-]+))?",
    re.MULTILINE,
)

out = {
    "failed": False,
    "plugin_group": None,
    "plugin_artifact": None,
    "plugin_version": None,
    "goal": None,
    "execution_id": None,
    "module": None,
    "error_lines": [],
    "hints": [],
}

m = fail_re.search(log)
if m:
    out["failed"] = True
    out["plugin_group"] = m.group("group")
    out["plugin_artifact"] = m.group("artifact")
    out["plugin_version"] = m.group("version")
    out["goal"] = m.group("goal")
    out["execution_id"] = m.group("exec")
    out["module"] = m.group("module")

errors = [line for line in log.splitlines() if line.startswith("[ERROR]")]
out["error_lines"] = errors[-40:]

hint_map = [
    (r"maven-compiler-plugin", "compiler"),
    (r"maven-surefire-plugin", "surefire"),
    (r"maven-failsafe-plugin", "failsafe"),
    (r"maven-jar-plugin", "jar"),
    (r"maven-shade-plugin", "shade"),
    (r"maven-assembly-plugin", "assembly"),
    (r"spring-boot-maven-plugin", "spring-boot"),
    (r"maven-enforcer-plugin", "enforcer"),
    (r"maven-checkstyle-plugin", "checkstyle"),
    (r"spotbugs-maven-plugin", "spotbugs"),
    (r"maven-pmd-plugin", "pmd"),
    (r"jacoco-maven-plugin", "jacoco"),
    (r"versions-maven-plugin", "versions"),
    (r"maven-release-plugin", "release"),
    (r"build-helper-maven-plugin", "build-helper"),
    (r"exec-maven-plugin", "exec"),
]
hints = set()
artifact = out["plugin_artifact"] or ""
joined_err = "\n".join(errors)
for pattern, hint in hint_map:
    if re.search(pattern, artifact) or re.search(pattern, joined_err):
        hints.add(hint)

msg_map = [
    (r"cannot find symbol.*AutoValue_|AutoFactory_|Auto[A-Z]\w*_", "annotation-processor"),
    (r"invalid target release|release version \d+ not supported", "compiler-release-mismatch"),
    (r"No tests were executed", "test-include-pattern"),
    (r"forked VM terminated without properly saying goodbye|OutOfMemoryError", "fork-heap"),
    (r"Invalid signature file digest", "shade-signatures"),
    (r"Unable to find main class", "missing-main-class"),
    (r"Dependency convergence", "dependency-convergence"),
    (r"Banned Dependencies", "banned-dependency"),
    (r"Detected Maven Version", "maven-version"),
]
for pattern, hint in msg_map:
    if re.search(pattern, joined_err, re.IGNORECASE):
        hints.add(hint)

out["hints"] = sorted(hints)

json.dump(out, sys.stdout, indent=2)
sys.stdout.write("\n")
PY

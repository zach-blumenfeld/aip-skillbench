"""verify-static: re-scan after manual refactors; verify_passed is true when no blocking issue remains."""
import sys

sys.dont_write_bytecode = True  # keep the skill folder free of __pycache__

import sb3lib  # noqa: E402


def main():
    state, cfg = sb3lib.read_payload()
    root = sb3lib.project_root(state)
    inv, issues = sb3lib.scan(root, cfg, state.get("waived_issues"))
    blocking = [i for i in issues if i["severity"] == "blocking"]
    checks = {
        "boot_version": [p["boot_version"] for p in inv["poms"]],
        "java_version": [p["java_version"] for p in inv["poms"]],
        "enable_method_security_present": inv["enable_method_security_present"],
        "method_security_annotations": inv["method_security_annotations"],
        "security_filter_chain_present": inv["security_filter_chain_present"],
        "restclient_present": inv["restclient_present"],
        "resttemplate_files": inv["resttemplate_files"],
        "files_with_javax_ee": inv["files_with_javax_ee"],
        "jakarta_persistence_imports": inv["jakarta_persistence_imports"],
        "entity_files": inv["entity_files"],
    }
    sb3lib.emit({
        "verify_passed": not blocking,
        "remaining_issues": issues,
        "remaining_issue_counts": sb3lib.summarize(issues),
        "static_checks": checks,
        "inventory": inv,
    })


if __name__ == "__main__":
    main()

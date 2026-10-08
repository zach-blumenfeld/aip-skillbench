"""scan-project: inventory a Spring Boot 2.x project and list every migration issue before any edit."""
import sys

sys.dont_write_bytecode = True  # keep the skill folder free of __pycache__

import sb3lib  # noqa: E402


def main():
    state, cfg = sb3lib.read_payload()
    root = sb3lib.project_root(state)
    inv, issues = sb3lib.scan(root, cfg)
    sb3lib.emit({
        "project_dir": root,
        "inventory": inv,
        "initial_issues": issues,
        "initial_issue_counts": sb3lib.summarize(issues),
        "targets": {"boot": cfg["target_boot_version"], "java": cfg["target_java_version"], "jjwt": cfg["jjwt_version"]},
    })


if __name__ == "__main__":
    main()

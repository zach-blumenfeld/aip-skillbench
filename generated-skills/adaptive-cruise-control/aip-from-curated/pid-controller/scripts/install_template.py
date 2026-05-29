#!/usr/bin/env python3
"""Install the reference PID controller template at a target path.

Usage:
    python scripts/install_template.py [target_path]

Defaults to `./pid_controller.py` in the current working directory.
Refuses to overwrite an existing file unless `--force` is passed.
"""

import argparse
import shutil
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", nargs="?", default="pid_controller.py",
                        help="Destination path (default: ./pid_controller.py)")
    parser.add_argument("--force", action="store_true",
                        help="Overwrite an existing file at the target path")
    args = parser.parse_args()

    template = Path(__file__).resolve().parent.parent / "assets" / "pid_controller.py"
    if not template.exists():
        print(f"ERROR: template missing at {template}", file=sys.stderr)
        return 1

    target = Path(args.target).resolve()
    if target.exists() and not args.force:
        print(f"ERROR: {target} already exists. Re-run with --force to overwrite.",
              file=sys.stderr)
        return 1

    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(template, target)
    print(f"Installed PID template -> {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

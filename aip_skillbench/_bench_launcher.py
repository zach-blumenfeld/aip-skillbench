"""Run benchflow's `bench` CLI with aip-skillbench patches applied.

The user-facing `bench` entry point runs in a subprocess from our CLI, which
means `import aip_skillbench` (and the benchflow patches it installs) never
fires in that subprocess. This launcher imports aip_skillbench first, then
delegates to benchflow's typer app — invoked as:

    python -m aip_skillbench._bench_launcher eval create --tasks-dir … …
"""

from __future__ import annotations

import aip_skillbench  # noqa: F401  # triggers benchflow monkey-patching
from benchflow.cli.main import app


def main() -> None:
    app()


if __name__ == "__main__":
    main()

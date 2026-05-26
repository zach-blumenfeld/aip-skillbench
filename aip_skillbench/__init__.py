__version__ = "0.1.0"

# Apply benchflow patches at package import time so every CLI entry point
# gets them. See aip_skillbench/_benchflow_patch.py for what it does and why.
from aip_skillbench import _benchflow_patch  # noqa: F401, E402

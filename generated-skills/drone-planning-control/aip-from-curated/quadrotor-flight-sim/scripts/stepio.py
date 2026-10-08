"""Shared helpers for the step scripts: stdin/stdout JSON and locating the simulator modules."""
import json
import os
import sys

PACK_LIB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "quadsim")


def read_input():
    data = json.load(sys.stdin)
    return data.get("currentState", {}), data.get("assets", {})


def emit(obj):
    def default(o):
        try:
            import numpy as np
            if isinstance(o, np.ndarray):
                return o.tolist()
            if isinstance(o, np.generic):
                return o.item()
        except ImportError:
            pass
        raise TypeError(f"not JSON serialisable: {type(o)}")
    sys.stdout.write(json.dumps(obj, default=default))
    sys.stdout.flush()


def fail(msg):
    emit({"error": msg})
    sys.exit(1)


def use_lib(workdir=None):
    """Import the simulator from workdir when it holds an (possibly adapted) installed copy,
    otherwise from the pack's own scripts/quadsim."""
    lib = workdir if workdir and os.path.isfile(os.path.join(workdir, "simulate.py")) else PACK_LIB
    sys.path.insert(0, lib)
    return lib

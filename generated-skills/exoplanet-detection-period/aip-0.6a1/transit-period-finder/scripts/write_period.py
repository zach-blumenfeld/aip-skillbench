"""Write a period chosen by the client (rescue path) in the required format."""
import numpy as np

from lc_common import emit, fail, read_state, write_period


def main():
    state = read_state()
    p = float(state["rescue_period_days"])
    if not (np.isfinite(p) and p > 0):
        fail(f"non-physical period {p}")
    emit({"rescue_period_text": write_period(state["output_path"], p)})


if __name__ == "__main__":
    main()

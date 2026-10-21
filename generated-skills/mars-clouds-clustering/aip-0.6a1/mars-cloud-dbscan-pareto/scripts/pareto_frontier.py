"""Filter grid results to F1 > min_f1, keep every Pareto-optimal point (maximize F1,
minimize delta; exact ties are all kept since neither dominates the other), round, and
write the frontier CSV with columns F1,delta,min_samples,epsilon,shape_weight."""
import os

import numpy as np
import pandas as pd
from paretoset import paretoset

from mcc_common import emit, fail, load_config, read_payload


def non_dominated(f1, delta):
    """Manual dominance check: j dominates i if j is >= on F1, <= on delta, strictly better on one."""
    ge = f1[None, :] >= f1[:, None]
    le = delta[None, :] <= delta[:, None]
    strict = (f1[None, :] > f1[:, None]) | (delta[None, :] < delta[:, None])
    return ~(ge & le & strict).any(axis=1)


def main():
    state, assets = read_payload()
    cfg = load_config(assets)
    path = state["grid_results_csv"]
    if not os.path.isfile(path):
        fail(f"grid results not found: {path}")
    res = pd.read_csv(path)
    keep = res[(res["F1"] > cfg["min_f1"]) & res["delta"].notna()].reset_index(drop=True)

    cols = cfg["output_columns"]
    if keep.empty:
        front = pd.DataFrame(columns=cols)
    else:
        mask = np.asarray(paretoset(keep[["F1", "delta"]], sense=["max", "min"], distinct=False))
        manual = non_dominated(keep["F1"].to_numpy(), keep["delta"].to_numpy())
        if not np.array_equal(mask, manual):
            fail("paretoset and the manual dominance check disagree; refusing to write an unverified frontier")
        front = keep[mask].sort_values(["F1", "delta"], ascending=[False, True]).copy()
        front["F1"] = front["F1"].round(cfg["f1_decimals"])
        front["delta"] = front["delta"].round(cfg["delta_decimals"])
        front["shape_weight"] = front["shape_weight"].round(cfg["shape_weight_decimals"])
        front["min_samples"] = front["min_samples"].astype(int)
        if np.allclose(front["epsilon"], front["epsilon"].round()):
            front["epsilon"] = front["epsilon"].round().astype(int)
        front = front[cols]

    out = state["output_csv"]
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    front.to_csv(out, index=False)
    emit({
        "n_frontier": int(len(front)),
        "n_passing_min_f1": int(len(keep)),
        "frontier_rows": front.to_dict(orient="records"),
        "frontier_status": "found" if len(front) else "empty",
    })


if __name__ == "__main__":
    main()

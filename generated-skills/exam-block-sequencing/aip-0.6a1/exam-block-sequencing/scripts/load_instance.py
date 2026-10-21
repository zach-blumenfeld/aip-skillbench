"""Step load-instance: load and validate the sequencing instance; surface the overlap wording."""
import os

import seqcore as sc


def main():
    st = sc.read_stdin()
    data_dir = st["data_dir"]
    weights = sc.normalize_weights(st["weights"])
    inst = sc.load_instance(data_dir)
    files = sorted(os.listdir(data_dir))
    readme = ""
    for name in ("README.md", "readme.md", "README.txt"):
        path = os.path.join(data_dir, name)
        if os.path.isfile(path):
            with open(path) as f:
                readme = f.read()
            break
    if not readme:
        readme = "(no README in data_dir; decide the overlap rule from the task statement)"
    st_ = inst["starts"]
    lab = inst["labels"]
    summary = {
        "n_blocks": inst["n"],
        "n_slots": inst["n"],
        "slot_order": inst["slots"],
        "slot_order_source": inst["slot_source"],
        "virtual_blocks": inst["virtual"],
        "large_blocks": inst["large"],
        "early_slots": [inst["slots"][p] for p in inst["early"]],
        "frontload_active": inst["frontload_active"],
        "start_slots": {k: [inst["slots"][p] for p in v] for k, v in st_.items()},
        "pair_rows": inst["pair_rows"],
        "triplet_rows": inst["triplet_rows"],
        "files": files,
        "warnings": inst["warnings"],
        "blocks": lab,
    }
    sc.emit({"instance_summary": summary, "overlap_text": readme, "objective_weights": weights})


if __name__ == "__main__":
    main()

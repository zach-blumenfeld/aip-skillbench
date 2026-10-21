"""Validate the two annotation CSVs and the search space before the grid search.

Hard problems (missing file/column, no expert images, bad search space) exit non-zero.
Soft anomalies are listed in data_report.warnings and set data_status to "warnings".
"""
import re

from mcc_common import emit, fail, group_points, load_config, load_points, read_payload, resolve_search_space

VARIANT_RE = re.compile(r"(_log|_contrast_stretch_0_\d+)(?=\.png$)")


def col_range(df, col):
    return [float(df[col].min()), float(df[col].max())] if len(df) else None


def main():
    state, assets = read_payload()
    cfg = load_config(assets)
    cit, cit_raw, cit_bad = load_points(state["citsci_csv"], cfg, "citizen-science")
    exp, exp_raw, exp_bad = load_points(state["expert_csv"], cfg, "expert")
    space = resolve_search_space(state.get("search_space"), cfg)
    if exp.empty:
        fail("expert file has no usable rows; there is nothing to evaluate against")

    cit_imgs, exp_imgs = group_points(cit, cfg), group_points(exp, cfg)
    exp_keys, cit_keys = set(exp_imgs), set(cit_imgs)
    no_cit = sorted(exp_keys - cit_keys)
    cit_only = sorted(cit_keys - exp_keys)
    variant_keys = sorted(k for k in exp_keys | cit_keys if VARIANT_RE.search(k))

    warnings = []
    if cit_bad or exp_bad:
        warnings.append(f"dropped rows with missing/non-numeric x, y or empty image key: citsci={cit_bad}, expert={exp_bad}")
    if no_cit:
        warnings.append(f"{len(no_cit)} of {len(exp_keys)} expert images have no citizen-science points (they score F1=0, delta=NaN)")
    if cit_only:
        warnings.append(f"{len(cit_only)} citizen-science images are absent from the expert file (ignored)")
    if variant_keys:
        warnings.append(f"{len(variant_keys)} image keys carry a variant suffix (_log/_contrast_stretch); keys should be base filenames")
    if len(no_cit) > 0.5 * len(exp_keys):
        warnings.append("fewer than half the expert images match a citizen-science image: check the image key / file pairing")

    sizes = [len(v) for v in cit_imgs.values()]
    report = {
        "citsci_rows": cit_raw, "citsci_rows_used": len(cit),
        "expert_rows": exp_raw, "expert_rows_used": len(exp),
        "expert_images": len(exp_keys), "citsci_images": len(cit_keys),
        "expert_images_without_citsci": len(no_cit), "citsci_images_not_in_expert": len(cit_only),
        "examples_without_citsci": no_cit[:5], "examples_not_in_expert": cit_only[:5],
        "examples_variant_keys": variant_keys[:5],
        "citsci_points_per_image": {"min": min(sizes) if sizes else 0, "max": max(sizes) if sizes else 0},
        "citsci_x_range": col_range(cit, cfg["x_col"]), "citsci_y_range": col_range(cit, cfg["y_col"]),
        "expert_x_range": col_range(exp, cfg["x_col"]), "expert_y_range": col_range(exp, cfg["y_col"]),
        "n_combinations": len(space["min_samples"]) * len(space["epsilon"]) * len(space["shape_weight"]),
        "warnings": warnings,
    }
    emit({"data_report": report, "resolved_search_space": space,
          "data_status": "warnings" if warnings else "clean"})


if __name__ == "__main__":
    main()

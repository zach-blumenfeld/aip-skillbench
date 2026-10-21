"""Start step: parse and sanity-check data.json; summarize it for the rule-reading decision."""
import rebalance_core as rc


def main():
    state = rc.read_stdin()
    try:
        inst = rc.load_instance(state["data_path"])
    except Exception as exc:
        rc.fail(f"cannot load {state.get('data_path')}: {exc}")
    if inst["distance_metric"] != "great_circle_miles":
        rc.fail(f"unsupported distance_metric {inst['distance_metric']!r}; "
                "this skill computes great-circle miles only")
    if float(state["earth_radius_miles"]) <= 0:
        rc.fail("earth_radius_miles must be positive")
    st = inst["stations"]
    rc.emit({"instance_summary": {
        "station_count": len(st),
        "vehicle_count": inst["vehicle_count"],
        "vehicle_capacity": inst["vehicle_capacity"],
        "penalty_weight": inst["penalty_weight"],
        "distance_metric": inst["distance_metric"],
        "target_sign_convention": inst["sign_convention"],
        "total_pickup_target": sum(s["target"] for s in st if s["target"] > 0),
        "total_dropoff_target": -sum(s["target"] for s in st if s["target"] < 0),
        "pickup_targets_above_initial_bikes": [s["id"] for s in st if s["target"] > s["initial"]],
        "dropoff_targets_above_free_docks": [s["id"] for s in st
                                             if -s["target"] > s["capacity"] - s["initial"]],
    }})


if __name__ == "__main__":
    main()

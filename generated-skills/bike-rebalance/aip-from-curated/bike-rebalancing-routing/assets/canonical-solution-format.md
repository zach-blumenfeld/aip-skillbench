```json
{
  "objective": 8.83,               // travel_distance + penalty_cost (unrounded)
  "travel_distance": 6.33,         // great-circle, data's metric/radius, all vehicles
  "penalty_cost": 2.5,             // penalty_weight * total_deviation
  "total_deviation": 5,            // sum_i |achieved_i - target_i| (or shortfall only)
  "penalty_weight": 0.5,
  "distance_metric": "great_circle_miles", "earth_radius": 3960.0,
  "vehicles": [
    {"vehicle_id": 1,
     "route": ["depot_start", 150, 302, "depot_end"],      // original station IDs
     "stops": [{"station_id": 150, "pickup": 13, "dropoff": 0, "net_pickup": 13, "load_after": 13}],
     "distance": 1.23, "start_load": 0, "end_load": 13, "total_pickup": 13, "total_dropoff": 0}
  ],
  "stations": [
    {"station_id": 150, "target": 13, "achieved": 13,   // data's sign convention
     "net_pickup": 13, "deviation": 0, "initial_bikes": 17, "final_bikes": 4, "station_capacity": 31}
  ],
  "solver": {"name": "SCIP", "status": "optimal", "gap": 0.0, "time_seconds": 41.2, ...},
  "assumptions": {"vehicles_must_be_used": true, "split_service_allowed": true, ...}
}
```

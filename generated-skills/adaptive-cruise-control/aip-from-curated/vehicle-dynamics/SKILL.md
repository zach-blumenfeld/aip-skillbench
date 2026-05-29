---
name: vehicle-dynamics
description: Use this skill when simulating vehicle motion, calculating safe following distances, time-to-collision, speed/position updates, or implementing vehicle state machines for cruise control modes.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a2/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Vehicle motion primitives for adaptive cruise control simulation in SI units:
  discrete-time kinematic updates (speed, position, inter-vehicle distance),
  the time-headway safe-following-distance formula, time-to-collision with the
  receding-vehicle edge case, physical acceleration clamping, and the
  cruise/follow/emergency mode state machine. Import and call the functions in
  `scripts/vehicle_dynamics.py` rather than re-deriving — the formulas and
  edge cases (non-negative speed, None for receding TTC, mode precedence) are
  pre-baked.

trigger_when:
  - Simulating vehicle motion over discrete timesteps in a cruise-control task.
  - Computing safe following distance from speed and time headway.
  - Computing time-to-collision between ego and lead vehicle.
  - Constraining a proposed acceleration to physical limits.
  - Implementing a cruise / follow / emergency mode state machine.
  - Building or reviewing adaptive cruise control logic.

steps:
  - name: update-kinematics
    description: >
      One simulation tick of kinematic state. Call `update_speed`,
      `update_position`, and (when a lead vehicle is present) `update_distance`
      from `scripts/vehicle_dynamics.py`. `update_speed` clamps the result to
      >= 0 — do not add a second clamp.
    script: scripts/vehicle_dynamics.py
    inputs:
      - name: current_speed
        type: float
        description: Ego speed at start of tick (m/s).
      - name: current_position
        type: float
        description: Ego position at start of tick (m).
      - name: current_distance
        type: float
        nullable: true
        description: Distance to lead vehicle (m); null when no lead is present.
      - name: acceleration
        type: float
        description: Acceleration applied this tick (m/s^2). Clamp first via clamp-acceleration.
      - name: lead_speed
        type: float
        nullable: true
        description: Lead vehicle speed (m/s); null when no lead is present.
      - name: dt
        type: float
        description: Timestep length (s).
    outputs:
      - name: new_speed
        type: float
      - name: new_position
        type: float
      - name: new_distance
        type: float
        nullable: true
        description: Updated distance to lead; null when no lead is present.

  - name: compute-safe-distance
    description: >
      Time-headway model — `safe_following_distance(speed, time_headway,
      min_distance)`. Returns the gap the ego should keep at the given speed.
    script: scripts/vehicle_dynamics.py
    inputs:
      - name: speed
        type: float
        description: Current ego speed (m/s).
      - name: time_headway
        type: float
        description: Desired time gap to lead (s).
      - name: min_distance
        type: float
        description: Minimum gap held at standstill (m).
    outputs:
      - name: safe_distance
        type: float

  - name: compute-ttc
    description: >
      Time-to-collision — `time_to_collision(distance, ego_speed, lead_speed)`.
      Returns None when ego is not approaching (relative speed <= 0). Treat
      None as "no collision risk this tick"; do not coerce to 0 or infinity.
    script: scripts/vehicle_dynamics.py
    inputs:
      - name: distance
        type: float
        description: Current gap to lead (m).
      - name: ego_speed
        type: float
      - name: lead_speed
        type: float
    outputs:
      - name: ttc
        type: float
        nullable: true
        description: Seconds until contact; None when not approaching.

  - name: clamp-acceleration
    description: >
      Constrain a requested acceleration to physical limits —
      `clamp_acceleration(accel, max_accel, max_decel)`. `max_decel` is the
      most-negative value allowed (e.g. -8.0); `max_accel` is the largest
      positive value (e.g. +2.5). Always clamp before passing to
      update-kinematics.
    script: scripts/vehicle_dynamics.py
    inputs:
      - name: accel
        type: float
        description: Requested acceleration (m/s^2).
      - name: max_accel
        type: float
        description: Positive acceleration limit (m/s^2).
      - name: max_decel
        type: float
        description: Negative deceleration limit (m/s^2), e.g. -8.0.
    outputs:
      - name: clamped_accel
        type: float

  - name: select-mode
    description: >
      Pick operating mode — `determine_mode(lead_present, ttc, ttc_threshold)`.
      Precedence: no-lead -> 'cruise', then low-TTC -> 'emergency', else
      'follow'. The no-lead branch wins even if the (irrelevant) TTC would
      otherwise be low. Use the mode to choose which acceleration policy to
      run.
    script: scripts/vehicle_dynamics.py
    inputs:
      - name: lead_present
        type: boolean
      - name: ttc
        type: float
        nullable: true
        description: Output of compute-ttc.
      - name: ttc_threshold
        type: float
        description: TTC below which emergency mode engages (s).
    outputs:
      - name: mode
        type: string
        description: One of 'cruise', 'follow', 'emergency'.

scenarios:
  - need: Single simulation tick with a lead vehicle present.
    context: >
      Have ego_speed, lead_speed, current gap, dt, and a proposed acceleration
      from the controller.
    action: >
      clamp-acceleration -> compute-ttc -> select-mode -> apply mode-specific
      policy if needed -> update-kinematics. Carry the new (speed, position,
      distance) tuple into the next tick.
    outcome: >
      State advances consistently with the source formulas; speed never goes
      negative; mode transitions follow the documented precedence.

  - need: No lead vehicle in sensor range.
    context: lead_present=false; lead_speed and current_distance are null.
    action: >
      select-mode returns 'cruise' immediately (TTC inputs are irrelevant).
      Skip compute-ttc and the distance update; only update_speed and
      update_position run.
    outcome: Ego cruises at the controller's setpoint; no spurious emergency trips.

anti_patterns:
  - Letting speed go negative. `update_speed` already clamps to >= 0; do not skip the function or add a second clamp that masks bugs in the controller.
  - Coercing a None TTC to 0 or to a large sentinel. None means "not approaching" — branch on it explicitly when picking mode or computing risk.
  - Skipping `clamp_acceleration` and passing the controller's raw acceleration into `update_speed`. Produces unrealistic step changes and breaks the physical-limits contract.
  - Re-implementing `determine_mode` with a different branch order. The no-lead check must run before the TTC check; otherwise a stale TTC value can trigger a spurious 'emergency' when there is no lead.
  - Updating distance when no lead is present. `update_distance` assumes both ego and lead speeds; call it only when `lead_present` is true.
```

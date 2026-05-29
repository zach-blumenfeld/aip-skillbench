---
name: vehicle-dynamics
description: Use this skill when simulating vehicle motion, calculating safe following distances, time-to-collision, speed/position updates, or implementing vehicle state machines for cruise control modes.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a3
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a3/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Reference library of discrete-time kinematic primitives for adaptive
  cruise control simulations: speed and position updates, inter-vehicle
  distance updates, time-headway safe-distance target, time-to-collision,
  acceleration clamping, and the cruise/follow/emergency mode selector.
  Each primitive is a small deterministic function; the procedure documents
  the agent-facing API surface of `scripts/vehicle_dynamics.py`. Call only
  the primitives the current control step needs — steps are independent.
  SI units throughout: meters, seconds, m/s, m/s^2.

trigger_when:
  - Simulating vehicle motion over discrete timesteps.
  - Computing a safe following distance from a time-headway policy.
  - Computing time-to-collision (TTC) against a lead vehicle.
  - Updating ego speed, position, or gap to a lead vehicle for one timestep.
  - Clamping a commanded acceleration to physical accel/decel limits.
  - Selecting a cruise-control mode (cruise / follow / emergency) from sensor state.
  - Implementing or wiring up an adaptive-cruise-control state machine.

do_not_use_when:
  - Modeling continuous-time dynamics, lateral control, or steering — this skill is longitudinal-only, discrete-time.
  - Doing path planning, perception, or sensor fusion — out of scope.
  - Tuning controller gains (PID, MPC) — this skill supplies primitives, not a controller.

steps:
  - name: safe-following-distance
    description: >
      Compute the time-headway safe-distance target for the ego vehicle.
      Call `safe_following_distance(speed, time_headway, min_distance)`
      in `scripts/vehicle_dynamics.py`. Returns `speed * time_headway + min_distance`.
    script: scripts/vehicle_dynamics.py
    inputs:
      - name: speed
        type: float
        description: Ego speed in m/s.
      - name: time_headway
        type: float
        description: Desired time gap to the lead vehicle in seconds.
      - name: min_distance
        type: float
        description: Minimum standstill gap in meters.
    outputs:
      - name: safe_distance
        type: float
        description: Target following distance in meters.

  - name: time-to-collision
    description: >
      Compute time-to-collision against a lead vehicle. Call
      `time_to_collision(distance, ego_speed, lead_speed)` in
      `scripts/vehicle_dynamics.py`. Returns `None` when the ego is not
      approaching (`ego_speed <= lead_speed`); callers must handle the
      `None` case before comparing against a threshold.
    script: scripts/vehicle_dynamics.py
    inputs:
      - name: distance
        type: float
        description: Current gap to lead vehicle in meters.
      - name: ego_speed
        type: float
        description: Ego speed in m/s.
      - name: lead_speed
        type: float
        description: Lead-vehicle speed in m/s.
    outputs:
      - name: ttc
        type: float
        nullable: true
        description: Seconds to collision at current relative velocity, or null if not approaching.

  - name: clamp-acceleration
    description: >
      Constrain a commanded acceleration to physical limits. Call
      `clamp_acceleration(accel, max_accel, max_decel)` in
      `scripts/vehicle_dynamics.py`. `max_decel` is the most-negative
      permitted value (e.g., -3.0), not its magnitude.
    script: scripts/vehicle_dynamics.py
    inputs:
      - name: accel
        type: float
        description: Commanded acceleration in m/s^2.
      - name: max_accel
        type: float
        description: Maximum permitted acceleration in m/s^2 (positive).
      - name: max_decel
        type: float
        description: Maximum permitted deceleration in m/s^2 (negative; e.g., -3.0).
    outputs:
      - name: clamped_accel
        type: float
        description: Acceleration in m/s^2, within [max_decel, max_accel].

  - name: update-speed
    description: >
      Advance ego speed one timestep. Call
      `update_speed(current_speed, acceleration, dt)` in
      `scripts/vehicle_dynamics.py`. Result is clipped to be non-negative
      (the vehicle does not reverse).
    script: scripts/vehicle_dynamics.py
    inputs:
      - name: current_speed
        type: float
        description: Speed at start of step in m/s.
      - name: acceleration
        type: float
        description: Applied acceleration in m/s^2 (clamp first via `clamp-acceleration`).
      - name: dt
        type: float
        description: Timestep in seconds.
    outputs:
      - name: new_speed
        type: float
        description: Speed at end of step in m/s, never negative.

  - name: update-position
    description: >
      Advance ego position one timestep. Call
      `update_position(current_position, speed, dt)` in
      `scripts/vehicle_dynamics.py`.
    script: scripts/vehicle_dynamics.py
    inputs:
      - name: current_position
        type: float
        description: Position at start of step in meters.
      - name: speed
        type: float
        description: Speed during the step in m/s.
      - name: dt
        type: float
        description: Timestep in seconds.
    outputs:
      - name: new_position
        type: float
        description: Position at end of step in meters.

  - name: update-following-distance
    description: >
      Advance the gap to a lead vehicle one timestep, using relative speed.
      Call `update_following_distance(current_distance, ego_speed, lead_speed, dt)`
      in `scripts/vehicle_dynamics.py`. Gap shrinks when the ego is faster,
      grows when slower.
    script: scripts/vehicle_dynamics.py
    inputs:
      - name: current_distance
        type: float
        description: Gap at start of step in meters.
      - name: ego_speed
        type: float
        description: Ego speed in m/s.
      - name: lead_speed
        type: float
        description: Lead-vehicle speed in m/s.
      - name: dt
        type: float
        description: Timestep in seconds.
    outputs:
      - name: new_distance
        type: float
        description: Gap at end of step in meters.

  - name: determine-mode
    description: >
      Select cruise-control operating mode for the current step. Call
      `determine_mode(lead_present, ttc, ttc_threshold)` in
      `scripts/vehicle_dynamics.py`. Returns one of `cruise`, `follow`,
      or `emergency`. Pass `ttc` from `time-to-collision`; the function
      handles a `None` TTC (treats it as not-approaching, so never
      escalates to emergency on that signal alone).
    script: scripts/vehicle_dynamics.py
    inputs:
      - name: lead_present
        type: boolean
        description: Whether a lead vehicle is detected.
      - name: ttc
        type: float
        nullable: true
        description: Time-to-collision in seconds, or null if not approaching.
      - name: ttc_threshold
        type: float
        description: Emergency-mode TTC threshold in seconds.
    outputs:
      - name: mode
        type: string
        description: One of `cruise`, `follow`, `emergency`.

anti_patterns:
  - Comparing TTC against a threshold without first handling the `None` (not-approaching) case — comparisons against `None` raise in Python 3.
  - Passing `max_decel` as a positive magnitude — `clamp_acceleration` expects the signed lower bound (e.g., `-3.0`, not `3.0`).
  - Letting speed go negative after an `update_speed` call — the primitive already clamps, do not re-add a negative branch in caller code.
  - Mixing units — every primitive is SI (m, s, m/s, m/s^2); converting at the boundary, not mid-pipeline.
  - Escalating to `emergency` mode whenever there is a lead vehicle — `emergency` requires TTC below threshold; default to `follow` otherwise.
```

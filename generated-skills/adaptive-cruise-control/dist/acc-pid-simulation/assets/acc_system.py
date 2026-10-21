"""Adaptive Cruise Control: mode selection + PID speed/distance control.

Requires: Python >= 3.8; pid_controller.py in the same folder.

config is the nested dict loaded from vehicle_params.yaml, e.g.
config['acc_settings']['set_speed'], config['vehicle']['max_acceleration'].
Gains come from config['pid_speed'] / config['pid_distance']; simulation.py
overrides those with tuning_results.yaml before constructing this class.

Modes:
  cruise    - no lead vehicle (lead_speed or distance is None/NaN):
              a = PID_speed(set_speed - ego_speed)
  emergency - lead present and TTC < emergency_ttc_threshold:
              a = max_deceleration (full braking)
  follow    - lead present otherwise:
              e_d = distance - (ego_speed * time_headway + min_distance)
              a = PID_distance(e_d) + PID_speed(lead_speed - ego_speed),
              capped by the cruise term kp_speed*(set_speed - ego_speed) so
              following never pushes ego above set_speed.
The command is clamped to [max_deceleration, max_acceleration]; both PIDs are
reset on every mode change so stale integral/derivative state does not leak.
"""

import math

from pid_controller import PIDController


def _missing(x):
    return x is None or (isinstance(x, float) and math.isnan(x))


class AdaptiveCruiseControl:
    def __init__(self, config):
        vehicle = config.get('vehicle', {})
        acc = config.get('acc_settings', {})
        self.set_speed = float(acc.get('set_speed', 30.0))
        self.time_headway = float(acc.get('time_headway', 1.5))
        self.min_distance = float(acc.get('min_distance', 10.0))
        self.ttc_threshold = float(acc.get('emergency_ttc_threshold', 3.0))
        self.max_accel = float(vehicle.get('max_acceleration', 3.0))
        self.max_decel = float(vehicle.get('max_deceleration', -8.0))
        if self.max_decel > 0:  # tolerate a positive magnitude in the yaml
            self.max_decel = -self.max_decel

        ps = config.get('pid_speed', {}) or {}
        pdist = config.get('pid_distance', {}) or {}
        self.pid_speed = PIDController(ps.get('kp', 0.1), ps.get('ki', 0.0), ps.get('kd', 0.0))
        self.pid_distance = PIDController(pdist.get('kp', 0.1), pdist.get('ki', 0.0), pdist.get('kd', 0.0))
        self.mode = None

    def reset(self):
        self.pid_speed.reset()
        self.pid_distance.reset()
        self.mode = None

    def safe_distance(self, ego_speed):
        return ego_speed * self.time_headway + self.min_distance

    @staticmethod
    def time_to_collision(distance, ego_speed, lead_speed):
        """distance / closing speed; None when not approaching."""
        if _missing(distance) or _missing(lead_speed):
            return None
        closing = ego_speed - lead_speed
        if closing <= 0:
            return None
        return distance / closing

    def _clamp(self, a):
        return max(self.max_decel, min(a, self.max_accel))

    def compute(self, ego_speed, lead_speed, distance, dt):
        """Return (acceleration_cmd, mode, distance_error).

        distance_error is None in cruise mode.
        """
        ego_speed = float(ego_speed)
        lead_present = not (_missing(lead_speed) or _missing(distance))

        if not lead_present:
            mode = 'cruise'
        else:
            ttc = self.time_to_collision(distance, ego_speed, lead_speed)
            mode = 'emergency' if (ttc is not None and ttc < self.ttc_threshold) else 'follow'

        if mode != self.mode:
            self.pid_speed.reset()
            self.pid_distance.reset()
            self.mode = mode

        distance_error = None
        if mode == 'cruise':
            err = self.set_speed - ego_speed
            raw = self.pid_speed.compute(err, dt)
            accel = self._clamp(raw)
            if raw != accel and (raw > accel) == (err > 0):
                self.pid_speed.integral -= err * dt  # anti-windup
        elif mode == 'emergency':
            distance_error = float(distance) - self.safe_distance(ego_speed)
            accel = self.max_decel
        else:
            distance_error = float(distance) - self.safe_distance(ego_speed)
            v_err = float(lead_speed) - ego_speed
            raw = (self.pid_distance.compute(distance_error, dt)
                   + self.pid_speed.compute(v_err, dt))
            cruise_cap = self.pid_speed.kp * (self.set_speed - ego_speed)
            raw = min(raw, cruise_cap)
            accel = self._clamp(raw)
            saturated_high = raw > self.max_accel or raw >= cruise_cap
            saturated_low = raw < self.max_decel
            if saturated_high:
                if distance_error > 0:
                    self.pid_distance.integral -= distance_error * dt
                if v_err > 0:
                    self.pid_speed.integral -= v_err * dt
            elif saturated_low:
                if distance_error < 0:
                    self.pid_distance.integral -= distance_error * dt
                if v_err < 0:
                    self.pid_speed.integral -= v_err * dt

        return float(accel), mode, distance_error

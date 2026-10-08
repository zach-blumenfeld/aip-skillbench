"""Adaptive Cruise Control: mode logic + speed and distance PID loops.

Modes (state machine):
  cruise    - no lead vehicle detected: track set_speed with the speed PID.
  follow    - lead detected, TTC >= threshold (or not approaching): track the
              time-headway safe distance with the distance PID (error = distance
              - (ego_speed*time_headway + min_distance); D term = lead - ego),
              never faster than the speed PID allows (command = min of the two).
  emergency - lead detected and TTC < emergency_ttc_threshold: full braking
              at max_deceleration.
All commands are clamped to [max_deceleration, max_acceleration].
"""
import math

from pid_controller import PIDController


def safe_following_distance(speed, time_headway, min_distance):
    return speed * time_headway + min_distance


def time_to_collision(distance, ego_speed, lead_speed):
    """Seconds until collision at current speeds; None if not approaching."""
    relative_speed = ego_speed - lead_speed
    if relative_speed <= 0:
        return None
    return distance / relative_speed


def clamp_acceleration(accel, max_accel, max_decel):
    return max(max_decel, min(accel, max_accel))


def determine_mode(lead_present, ttc, ttc_threshold):
    if not lead_present:
        return 'cruise'
    if ttc is not None and ttc < ttc_threshold:
        return 'emergency'
    return 'follow'


def _missing(x):
    return x is None or (isinstance(x, float) and math.isnan(x))


class AdaptiveCruiseControl:
    def __init__(self, config):
        vehicle = config['vehicle']
        acc = config['acc_settings']
        self.max_accel = float(vehicle['max_acceleration'])
        self.max_decel = float(vehicle['max_deceleration'])  # negative number
        self.set_speed = float(acc['set_speed'])
        self.time_headway = float(acc['time_headway'])
        self.min_distance = float(acc['min_distance'])
        self.ttc_threshold = float(acc['emergency_ttc_threshold'])
        ps, pd_ = config['pid_speed'], config['pid_distance']
        self.speed_pid = PIDController(ps['kp'], ps['ki'], ps['kd'],
                                       self.max_decel, self.max_accel)
        self.distance_pid = PIDController(pd_['kp'], pd_['ki'], pd_['kd'],
                                          self.max_decel, self.max_accel)
        self.mode = None
        self.last_ttc = None

    def reset(self):
        self.speed_pid.reset()
        self.distance_pid.reset()
        self.mode = None
        self.last_ttc = None

    def compute(self, ego_speed, lead_speed, distance, dt):
        """Return (acceleration_cmd, mode, distance_error).

        lead_speed / distance are None or NaN when no lead vehicle is detected;
        distance_error is then None. The step's time-to-collision (None when
        no lead or not approaching) is left in self.last_ttc.
        """
        lead_present = not (_missing(lead_speed) or _missing(distance))
        ttc = time_to_collision(distance, ego_speed, lead_speed) if lead_present else None
        mode = determine_mode(lead_present, ttc, self.ttc_threshold)
        if mode != self.mode:
            # Fresh state for the loop(s) becoming active: no stale integral or
            # derivative kick across a mode switch.
            if mode == 'cruise':
                self.speed_pid.reset()
            elif mode == 'follow':
                self.speed_pid.reset()
                self.distance_pid.reset()
        self.mode = mode
        self.last_ttc = ttc

        distance_error = None
        if lead_present:
            distance_error = distance - safe_following_distance(
                ego_speed, self.time_headway, self.min_distance)

        if mode == 'cruise':
            accel = self.speed_pid.compute(self.set_speed - ego_speed, dt)
        elif mode == 'follow':
            a_speed = self.speed_pid.compute(self.set_speed - ego_speed, dt)
            # D term on the gap rate (lead - ego), not on the error: see PIDController.compute.
            a_dist = self.distance_pid.compute(distance_error, dt,
                                               derivative=lead_speed - ego_speed)
            if a_dist <= a_speed:
                accel = a_dist
                self.speed_pid.rollback_integral()
            else:
                accel = a_speed
                self.distance_pid.rollback_integral()
        else:  # emergency
            accel = self.max_decel
        accel = clamp_acceleration(accel, self.max_accel, self.max_decel)
        return accel, mode, distance_error

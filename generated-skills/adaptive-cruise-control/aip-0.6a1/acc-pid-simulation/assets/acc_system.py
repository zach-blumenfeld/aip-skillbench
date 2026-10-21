"""Adaptive Cruise Control: cruise / follow / emergency modes on top of two PID loops."""
import math

from pid_controller import PIDController


def _missing(value):
    return value is None or (isinstance(value, float) and math.isnan(value))


def safe_following_distance(speed, time_headway, min_distance):
    """Time-headway spacing policy: desired gap = speed * headway + standstill gap."""
    return speed * time_headway + min_distance


def time_to_collision(distance, ego_speed, lead_speed):
    """Seconds until collision at current speeds; None when not closing in."""
    if _missing(distance) or _missing(lead_speed):
        return None
    relative_speed = ego_speed - lead_speed
    if relative_speed <= 0:
        return None
    return distance / relative_speed


class AdaptiveCruiseControl:
    """config is the nested dict loaded from vehicle_params.yaml."""

    def __init__(self, config):
        acc = config['acc_settings']
        vehicle = config['vehicle']
        self.set_speed = float(acc['set_speed'])
        self.time_headway = float(acc['time_headway'])
        self.min_distance = float(acc['min_distance'])
        self.ttc_threshold = float(acc['emergency_ttc_threshold'])
        self.max_accel = float(vehicle['max_acceleration'])
        self.max_decel = float(vehicle['max_deceleration'])

        speed_gains = config.get('pid_speed', {'kp': 0.1, 'ki': 0.01, 'kd': 0.0})
        distance_gains = config.get('pid_distance', {'kp': 0.1, 'ki': 0.01, 'kd': 0.0})
        self.speed_pid = PIDController(speed_gains['kp'], speed_gains['ki'], speed_gains['kd'],
                                       output_min=self.max_decel, output_max=self.max_accel)
        self.distance_pid = PIDController(distance_gains['kp'], distance_gains['ki'], distance_gains['kd'],
                                          output_min=self.max_decel, output_max=self.max_accel)
        self.mode = None

    def reset(self):
        self.speed_pid.reset()
        self.distance_pid.reset()
        self.mode = None

    def safe_distance(self, ego_speed):
        return safe_following_distance(ego_speed, self.time_headway, self.min_distance)

    def determine_mode(self, lead_present, ttc):
        if not lead_present:
            return 'cruise'
        if ttc is not None and ttc < self.ttc_threshold:
            return 'emergency'
        return 'follow'

    def clamp(self, accel):
        return max(self.max_decel, min(accel, self.max_accel))

    def compute(self, ego_speed, lead_speed, distance, dt):
        """Return (acceleration_cmd, mode, distance_error).

        distance_error = distance - safe_distance(ego_speed) (positive: gap larger than
        desired); None in cruise mode.
        """
        lead_present = not _missing(lead_speed) and not _missing(distance)
        ttc = time_to_collision(distance, ego_speed, lead_speed) if lead_present else None
        mode = self.determine_mode(lead_present, ttc)

        speed_error = self.set_speed - ego_speed
        distance_error = distance - self.safe_distance(ego_speed) if lead_present else None

        if mode != self.mode:
            # Fresh loops on every mode change; priming prev_error avoids a derivative kick.
            self.speed_pid.reset()
            self.distance_pid.reset()
            self.speed_pid.prev_error = speed_error
            if distance_error is not None:
                self.distance_pid.prev_error = distance_error
            self.mode = mode

        if mode == 'cruise':
            accel = self.speed_pid.compute(speed_error, dt)
        elif mode == 'emergency':
            accel = self.max_decel
        else:
            accel_speed = self.speed_pid.compute(speed_error, dt)
            accel_distance = self.distance_pid.compute(distance_error, dt)
            accel = min(accel_speed, accel_distance)  # never exceed set speed, never close the gap

        accel = self.clamp(accel)
        return float(accel), mode, (None if distance_error is None else float(distance_error))

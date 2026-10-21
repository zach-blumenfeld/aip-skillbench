"""Discrete-time PID controller used by the Adaptive Cruise Control system."""


class PIDController:
    """output = kp*e + ki*integral(e) + kd*de/dt, with optional output clamping.

    Anti-windup: conditional integration. When the unclamped output is saturated
    and the error would push it further into saturation, the integral is frozen.
    An optional integral_limit additionally clamps the accumulated integral.
    """

    def __init__(self, kp, ki, kd, output_min=None, output_max=None, integral_limit=None):
        self.kp = float(kp)
        self.ki = float(ki)
        self.kd = float(kd)
        self.output_min = output_min
        self.output_max = output_max
        self.integral_limit = integral_limit
        self.integral = 0.0
        self.prev_error = 0.0

    def reset(self):
        """Clear controller state."""
        self.integral = 0.0
        self.prev_error = 0.0

    def compute(self, error, dt):
        """Compute the control output for this error over timestep dt (seconds)."""
        error = float(error)
        p_term = self.kp * error

        candidate = self.integral + error * dt if dt > 0 else self.integral
        if self.integral_limit is not None:
            candidate = max(-self.integral_limit, min(candidate, self.integral_limit))

        derivative = (error - self.prev_error) / dt if dt > 0 else 0.0
        d_term = self.kd * derivative
        self.prev_error = error

        unclamped = p_term + self.ki * candidate + d_term
        saturated_high = self.output_max is not None and unclamped > self.output_max and error > 0
        saturated_low = self.output_min is not None and unclamped < self.output_min and error < 0
        if not (saturated_high or saturated_low):
            self.integral = candidate

        output = p_term + self.ki * self.integral + d_term
        if self.output_min is not None:
            output = max(output, self.output_min)
        if self.output_max is not None:
            output = min(output, self.output_max)
        return float(output)

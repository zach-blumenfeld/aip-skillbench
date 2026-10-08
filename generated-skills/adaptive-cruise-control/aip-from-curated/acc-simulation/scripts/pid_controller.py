"""Discrete-time PID controller with output clamping and anti-windup.

Control law: output = Kp*error + Ki*integral(error) + Kd*derivative(error),
error = setpoint - measured. Anti-windup is conditional integration: when the
clamped output is saturated and the error would push it further into
saturation, the integral is not accumulated.
"""


class PIDController:
    def __init__(self, kp, ki, kd, output_min=None, output_max=None,
                 integral_limit=None):
        self.kp = float(kp)
        self.ki = float(ki)
        self.kd = float(kd)
        self.output_min = output_min
        self.output_max = output_max
        self.integral_limit = integral_limit
        self.integral = 0.0
        self.prev_error = 0.0
        self._saved_integral = 0.0

    def reset(self):
        """Clear controller state (call when this loop becomes active)."""
        self.integral = 0.0
        self.prev_error = 0.0

    def compute(self, error, dt, derivative=None):
        """Compute the control output for this error and timestep.

        derivative: optional measured rate of the error. Pass it when the error
        contains a term that depends on the controller's own output (the ACC gap
        error contains -headway*ego_speed): differentiating that term feeds the
        previous command back with gain kd*headway and makes the loop chatter.
        """
        self._saved_integral = self.integral
        p_term = self.kp * error

        if derivative is None:
            derivative = (error - self.prev_error) / dt if dt > 0 else 0.0
        self.prev_error = error
        d_term = self.kd * derivative

        candidate = self.integral + error * dt
        if self.integral_limit is not None:
            candidate = max(-self.integral_limit, min(candidate, self.integral_limit))
        unclamped = p_term + self.ki * candidate + d_term
        # Conditional integration: skip accumulation while saturated in the
        # direction the error is pushing.
        saturated_high = self.output_max is not None and unclamped > self.output_max and error > 0
        saturated_low = self.output_min is not None and unclamped < self.output_min and error < 0
        if not (saturated_high or saturated_low):
            self.integral = candidate
        return self._clamp(p_term + self.ki * self.integral + d_term)

    def rollback_integral(self):
        """Undo the last integral update (used when this loop's output was not applied)."""
        self.integral = self._saved_integral

    def _clamp(self, value):
        if self.output_min is not None:
            value = max(value, self.output_min)
        if self.output_max is not None:
            value = min(value, self.output_max)
        return value

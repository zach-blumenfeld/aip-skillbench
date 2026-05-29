"""Discrete-time PID controller with anti-windup, output clamping, and derivative filtering.

Reference implementation. Drop in as `pid_controller.py` and instantiate per control loop.
Constructor positional signature is `(kp, ki, kd)`; the saturation/anti-windup knobs are
keyword-only with safe defaults (no clamping when unset).
"""


class PIDController:
    """Discrete-time PID controller.

    Control law: u = Kp * e + Ki * integral(e dt) + Kd * de/dt

    Features:
      - Integral clamping for anti-windup (set `integral_max`).
      - Output saturation (set `output_min` / `output_max`).
      - Low-pass filter on the derivative term (alpha = 0.2) to reduce noise sensitivity.
      - Safe first-step behavior: derivative is zero until two samples are seen.
    """

    def __init__(self, kp, ki, kd, output_min=None, output_max=None, integral_max=None):
        self.kp = kp
        self.ki = ki
        self.kd = kd
        self.output_min = output_min
        self.output_max = output_max
        self.integral_max = integral_max

        self.integral = 0.0
        self.prev_error = None
        self.prev_derivative = 0.0

    def reset(self):
        """Clear integrator and derivative state. Call on mode changes or setpoint jumps."""
        self.integral = 0.0
        self.prev_error = None
        self.prev_derivative = 0.0

    def compute(self, error, dt):
        """Return the control output for the current error and timestep.

        `error` is conventionally `setpoint - measured`.
        `dt` must be > 0; returns 0.0 on a zero/negative timestep.
        """
        if dt <= 0:
            return 0.0

        p_term = self.kp * error

        self.integral += error * dt
        if self.integral_max is not None:
            self.integral = max(-self.integral_max, min(self.integral_max, self.integral))
        i_term = self.ki * self.integral

        if self.prev_error is not None:
            raw_derivative = (error - self.prev_error) / dt
            alpha = 0.2
            derivative = alpha * raw_derivative + (1 - alpha) * self.prev_derivative
            self.prev_derivative = derivative
        else:
            derivative = 0.0
        d_term = self.kd * derivative
        self.prev_error = error

        output = p_term + i_term + d_term

        if self.output_min is not None:
            output = max(self.output_min, output)
        if self.output_max is not None:
            output = min(self.output_max, output)

        return output

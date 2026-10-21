"""Discrete-time PID controller.

Requires: Python >= 3.8 (standard library only).

Control law: output = kp*e + ki*integral(e) + kd*de/dt
  - integral accumulates error*dt every call
  - derivative = (error - prev_error) / dt (0 when dt <= 0)
Optional output_min/output_max clamp the output and switch on conditional
integration (anti-windup): the integral is not grown while the output is
saturated in the direction the error pushes.
"""


class PIDController:
    def __init__(self, kp, ki, kd, output_min=None, output_max=None):
        self.kp = float(kp)
        self.ki = float(ki)
        self.kd = float(kd)
        self.output_min = output_min
        self.output_max = output_max
        self.integral = 0.0
        self.prev_error = 0.0

    def reset(self):
        """Clear controller state (integral and previous error)."""
        self.integral = 0.0
        self.prev_error = 0.0

    def compute(self, error, dt):
        """Return the control output for this error and timestep."""
        error = float(error)
        p_term = self.kp * error

        prev_integral = self.integral
        self.integral += error * dt
        i_term = self.ki * self.integral

        derivative = (error - self.prev_error) / dt if dt > 0 else 0.0
        d_term = self.kd * derivative
        self.prev_error = error

        output = p_term + i_term + d_term

        # Clamp and apply conditional-integration anti-windup.
        if self.output_max is not None and output > self.output_max:
            if error > 0:
                self.integral = prev_integral
            output = self.output_max
        elif self.output_min is not None and output < self.output_min:
            if error < 0:
                self.integral = prev_integral
            output = self.output_min

        return float(output)

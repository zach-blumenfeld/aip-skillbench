#!/usr/bin/env python3
"""Emit a reference PID controller implementation to a target file path.

The body matches the canonical discrete-time form taught by this skill:
P + I (rectangular accumulation) + D (backward difference), with optional
output clamping. Anti-windup is left to the caller — see SKILL.md.
"""

import argparse
from pathlib import Path

TEMPLATE = '''"""PID (Proportional-Integral-Derivative) controller."""


class PIDController:
    def __init__(self, kp, ki, kd, output_min=None, output_max=None):
        self.kp = kp
        self.ki = ki
        self.kd = kd
        self.output_min = output_min
        self.output_max = output_max
        self.integral = 0.0
        self.prev_error = 0.0

    def reset(self):
        """Clear controller state."""
        self.integral = 0.0
        self.prev_error = 0.0

    def compute(self, error, dt):
        """Compute control output given error and timestep."""
        p_term = self.kp * error

        self.integral += error * dt
        i_term = self.ki * self.integral

        derivative = (error - self.prev_error) / dt if dt > 0 else 0.0
        d_term = self.kd * derivative
        self.prev_error = error

        output = p_term + i_term + d_term

        if self.output_min is not None:
            output = max(output, self.output_min)
        if self.output_max is not None:
            output = min(output, self.output_max)

        return output
'''


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Write the reference PIDController class to <path>."
    )
    parser.add_argument("path", help="Destination .py file (parent dirs are created).")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite the destination if it already exists.",
    )
    args = parser.parse_args()

    out = Path(args.path)
    if out.exists() and not args.force:
        raise SystemExit(f"refusing to overwrite existing file: {out} (pass --force)")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(TEMPLATE)
    print(str(out))


if __name__ == "__main__":
    main()

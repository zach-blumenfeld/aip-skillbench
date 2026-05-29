"""Vehicle dynamics primitives for cruise-control simulation.

Each function is a self-contained deterministic primitive an agent calls
when implementing adaptive-cruise-control logic. Discrete-time kinematics,
time-headway following model, time-to-collision, acceleration clamping, and
the cruise/follow/emergency mode selector.

All quantities are SI units: meters, seconds, m/s, m/s^2.
"""

from __future__ import annotations

from typing import Optional


def update_speed(current_speed: float, acceleration: float, dt: float) -> float:
    """Discrete-time speed update; speed cannot go negative."""
    new_speed = current_speed + acceleration * dt
    return max(0.0, new_speed)


def update_position(current_position: float, speed: float, dt: float) -> float:
    """Discrete-time position update."""
    return current_position + speed * dt


def update_following_distance(
    current_distance: float,
    ego_speed: float,
    lead_speed: float,
    dt: float,
) -> float:
    """Update gap to a lead vehicle from relative speed."""
    relative_speed = ego_speed - lead_speed
    return current_distance - relative_speed * dt


def safe_following_distance(
    speed: float,
    time_headway: float,
    min_distance: float,
) -> float:
    """Time-headway safe-distance target: speed * headway + standstill gap."""
    return speed * time_headway + min_distance


def time_to_collision(
    distance: float,
    ego_speed: float,
    lead_speed: float,
) -> Optional[float]:
    """Time to collision at current velocities; None if not approaching."""
    relative_speed = ego_speed - lead_speed
    if relative_speed <= 0:
        return None
    return distance / relative_speed


def clamp_acceleration(accel: float, max_accel: float, max_decel: float) -> float:
    """Constrain a commanded acceleration to physical limits.

    max_decel is the most-negative permitted value (e.g., -3.0).
    """
    return max(max_decel, min(accel, max_accel))


def determine_mode(
    lead_present: bool,
    ttc: Optional[float],
    ttc_threshold: float,
) -> str:
    """Pick operating mode: 'cruise', 'follow', or 'emergency'.

    - No lead vehicle -> 'cruise'.
    - Lead present and TTC below threshold -> 'emergency'.
    - Otherwise -> 'follow'.
    """
    if not lead_present:
        return "cruise"
    if ttc is not None and ttc < ttc_threshold:
        return "emergency"
    return "follow"

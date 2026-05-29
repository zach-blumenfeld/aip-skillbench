"""Vehicle dynamics primitives for adaptive cruise control simulation.

Importable module — call the functions directly from agent code.
All formulas use SI units (meters, seconds, meters/second, meters/second^2).
"""
from __future__ import annotations

from typing import Optional


def update_speed(current_speed: float, acceleration: float, dt: float) -> float:
    """Discrete-time speed update, clamped to non-negative.

    Speed cannot go below zero — physical vehicles do not reverse here.
    """
    new_speed = current_speed + acceleration * dt
    return max(0.0, new_speed)


def update_position(current_position: float, speed: float, dt: float) -> float:
    """Discrete-time position update."""
    return current_position + speed * dt


def update_distance(
    current_distance: float, ego_speed: float, lead_speed: float, dt: float
) -> float:
    """Distance to lead vehicle after one timestep.

    Shrinks when ego is faster than lead, grows when ego is slower.
    """
    relative_speed = ego_speed - lead_speed
    return current_distance - relative_speed * dt


def safe_following_distance(
    speed: float, time_headway: float, min_distance: float
) -> float:
    """Time-headway model: speed * headway + standstill minimum.

    Args:
        speed: Current ego speed (m/s).
        time_headway: Desired time gap to lead (seconds).
        min_distance: Minimum gap held at standstill (meters).
    """
    return speed * time_headway + min_distance


def time_to_collision(
    distance: float, ego_speed: float, lead_speed: float
) -> Optional[float]:
    """Seconds until contact at current relative speed.

    Returns None when ego is NOT approaching (relative speed <= 0). Callers
    must handle None explicitly — do not coerce to 0 or to a large sentinel.
    """
    relative_speed = ego_speed - lead_speed
    if relative_speed <= 0:
        return None
    return distance / relative_speed


def clamp_acceleration(
    accel: float, max_accel: float, max_decel: float
) -> float:
    """Constrain acceleration to physical limits.

    Args:
        accel: Requested acceleration (m/s^2).
        max_accel: Largest positive acceleration allowed (e.g. +2.5).
        max_decel: Most-negative deceleration allowed (e.g. -8.0).
    """
    return max(max_decel, min(accel, max_accel))


def determine_mode(
    lead_present: bool, ttc: Optional[float], ttc_threshold: float
) -> str:
    """Pick operating mode from current conditions.

    Precedence (in order): no-lead -> cruise, low-TTC -> emergency, else follow.
    Returns one of: 'cruise', 'follow', 'emergency'.
    """
    if not lead_present:
        return 'cruise'
    if ttc is not None and ttc < ttc_threshold:
        return 'emergency'
    return 'follow'

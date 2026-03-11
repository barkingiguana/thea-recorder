"""Human-like mouse movement based on the minimum-jerk trajectory model.

The minimum-jerk model (Flash & Hogan, 1985) produces the trajectory that
minimises the integral of squared jerk (rate of change of acceleration)
over the movement duration.  This matches empirically-observed human
point-to-point reaching movements.

On top of the smooth minimum-jerk base trajectory, this module adds:

- **Bezier perturbation**: slight lateral curvature so the path isn't
  perfectly straight (humans don't move in ruler-straight lines).
- **Overshoot and correction**: on fast or long movements the cursor
  overshoots slightly, then curves back to the target.
- **Motor noise**: small random displacements modelling hand tremor,
  scaling with speed (signal-dependent noise, per Harris & Wolpert 1998).
- **Fitts's Law duration**: when no explicit duration is given, the
  movement time is estimated from the distance and target size using
  Fitts's Law (Fitts 1954).

All randomness uses a configurable seed for reproducibility in tests.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field


@dataclass
class MotionConfig:
    """Tuning parameters for human-like mouse movement.

    Adjust these to make movements look faster/slower, more/less precise,
    or more/less wobbly.
    """

    #: Minimum movement duration in seconds (prevents impossibly fast moves).
    min_duration: float = 0.15

    #: Maximum movement duration in seconds.
    max_duration: float = 2.0

    #: Fitts's Law coefficient *a* (intercept, seconds).
    #: Affects the base time for any movement.
    fitts_a: float = 0.05

    #: Fitts's Law coefficient *b* (slope, seconds/bit).
    #: Higher = slower movements for a given distance.
    fitts_b: float = 0.12

    #: Default target width in pixels for Fitts's Law when the caller
    #: doesn't specify a target size.
    default_target_width: float = 20.0

    #: How much the path curves laterally, as a fraction of distance.
    #: 0 = straight line, 0.15 = moderate curve.
    curvature: float = 0.12

    #: Overshoot magnitude as a fraction of distance.
    #: 0 = no overshoot.  Only applied when distance > overshoot_threshold.
    overshoot: float = 0.02

    #: Minimum distance (pixels) before overshoot kicks in.
    overshoot_threshold: float = 100.0

    #: Motor noise magnitude (pixels).  Actual noise scales with
    #: instantaneous speed: ``noise_magnitude * speed / max_speed``.
    noise_magnitude: float = 1.5

    #: Number of intermediate points to generate per second of movement.
    #: Higher = smoother but more xdotool calls.
    points_per_second: float = 120.0

    #: Random seed.  *None* means use system entropy.
    seed: int | None = None

    #: Internal RNG, initialised from *seed*.
    _rng: random.Random = field(init=False, repr=False)

    def __post_init__(self):
        self._rng = random.Random(self.seed)


def fitts_duration(distance: float, target_width: float, config: MotionConfig) -> float:
    """Estimate movement time using Fitts's Law.

    Fitts's Law: MT = a + b * log2(2D / W)

    where D is distance, W is target width, a and b are empirical
    constants.  We clamp the result to [min_duration, max_duration].
    """
    if distance < 1:
        return config.min_duration
    id_bits = math.log2(2 * distance / max(target_width, 1.0))
    mt = config.fitts_a + config.fitts_b * max(id_bits, 0)
    return max(config.min_duration, min(config.max_duration, mt))


def _minimum_jerk(t: float) -> float:
    """Minimum-jerk position profile for normalised time t in [0, 1].

    Returns a value in [0, 1] representing the fraction of the total
    displacement completed at time *t*.

    This is the closed-form solution: 10t³ - 15t⁴ + 6t⁵
    (Flash & Hogan, 1985).
    """
    t2 = t * t
    t3 = t2 * t
    return 10 * t3 - 15 * t2 * t2 + 6 * t2 * t3


def _minimum_jerk_velocity(t: float) -> float:
    """Normalised velocity (derivative of minimum-jerk position).

    Returns a value in [0, ~1.875] — the velocity profile is bell-shaped,
    peaking slightly before mid-movement.

    30t² - 60t³ + 30t⁴
    """
    t2 = t * t
    return 30 * t2 - 60 * t2 * t + 30 * t2 * t2


def generate_path(
    start: tuple[float, float],
    end: tuple[float, float],
    duration: float | None = None,
    target_width: float | None = None,
    config: MotionConfig | None = None,
) -> list[tuple[float, float, float]]:
    """Generate a human-like mouse path from *start* to *end*.

    Returns a list of ``(x, y, timestamp)`` tuples where *timestamp*
    is seconds from the start of the movement.  The first point is
    at ``t=0`` (the start position) and the last point is at
    ``t=duration`` (exactly the end position).

    Args:
        start: ``(x, y)`` starting pixel coordinates.
        end: ``(x, y)`` target pixel coordinates.
        duration: Movement time in seconds.  If *None*, estimated
            via Fitts's Law from the distance and target_width.
        target_width: Size of the target in pixels (for Fitts's Law).
            Defaults to ``config.default_target_width``.
        config: Tuning parameters.  Uses defaults if *None*.
    """
    if config is None:
        config = MotionConfig()
    rng = config._rng

    dx = end[0] - start[0]
    dy = end[1] - start[1]
    distance = math.hypot(dx, dy)

    tw = target_width if target_width is not None else config.default_target_width

    if duration is None:
        duration = fitts_duration(distance, tw, config)

    if distance < 1:
        return [(start[0], start[1], 0.0), (end[0], end[1], duration)]

    num_points = max(int(duration * config.points_per_second), 2)

    # --- Lateral curvature (Bezier-like perturbation) ---
    # Perpendicular unit vector to the movement direction.
    perp_x = -dy / distance
    perp_y = dx / distance

    # Random lateral offset for the mid-control point.
    curvature_px = config.curvature * distance * rng.gauss(0, 1)

    # --- Overshoot ---
    # On long/fast movements, overshoot past the target then correct.
    do_overshoot = (
        config.overshoot > 0
        and distance > config.overshoot_threshold
    )
    if do_overshoot:
        overshoot_px = config.overshoot * distance * (0.5 + rng.random())
        # Direction of overshoot: along the movement vector plus slight lateral.
        os_dx = dx / distance
        os_dy = dy / distance
        os_lateral = rng.gauss(0, 0.3)
        overshoot_target = (
            end[0] + overshoot_px * (os_dx + os_lateral * perp_x),
            end[1] + overshoot_px * (os_dy + os_lateral * perp_y),
        )
        # The overshoot peak occurs at about 85% of the movement.
        overshoot_peak_t = 0.85 + rng.gauss(0, 0.03)
    else:
        overshoot_target = end
        overshoot_peak_t = 1.0

    points: list[tuple[float, float, float]] = []

    # Peak velocity (for noise scaling).
    peak_velocity = _minimum_jerk_velocity(0.5)

    for i in range(num_points + 1):
        t_norm = i / num_points  # 0..1
        t_sec = t_norm * duration

        # Base position from minimum-jerk profile.
        s = _minimum_jerk(t_norm)

        # Interpolate start -> end with minimum-jerk timing.
        base_x = start[0] + dx * s
        base_y = start[1] + dy * s

        # Add lateral curvature: peaks at mid-movement (sin curve).
        curve_amount = math.sin(math.pi * t_norm)
        base_x += perp_x * curvature_px * curve_amount
        base_y += perp_y * curvature_px * curve_amount

        # Add overshoot: push past the target near the peak,
        # then correct back smoothly.
        if do_overshoot and t_norm > 0.6:
            os_offset_x = overshoot_target[0] - end[0]
            os_offset_y = overshoot_target[1] - end[1]
            if t_norm < overshoot_peak_t:
                # Approaching overshoot peak — ease in with squared blend.
                blend = (t_norm - 0.6) / (overshoot_peak_t - 0.6)
                blend = blend * blend
                base_x += os_offset_x * blend
                base_y += os_offset_y * blend
            else:
                # Correcting back from overshoot — ease out.
                blend = (t_norm - overshoot_peak_t) / (1.0 - overshoot_peak_t)
                blend = min(blend, 1.0)
                remaining = 1.0 - blend
                base_x += os_offset_x * remaining
                base_y += os_offset_y * remaining

        # Add motor noise (signal-dependent: scales with velocity).
        v = _minimum_jerk_velocity(t_norm)
        noise_scale = config.noise_magnitude * (v / max(peak_velocity, 0.001))
        noise_x = rng.gauss(0, noise_scale) if noise_scale > 0.1 else 0
        noise_y = rng.gauss(0, noise_scale) if noise_scale > 0.1 else 0

        points.append((base_x + noise_x, base_y + noise_y, t_sec))

    # Ensure exact start and end positions (no noise on endpoints).
    points[0] = (start[0], start[1], 0.0)
    points[-1] = (end[0], end[1], duration)

    return points

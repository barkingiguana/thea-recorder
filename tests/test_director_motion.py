"""Tests for the minimum-jerk mouse movement model."""

import math

import pytest

from thea.director.motion import (
    MotionConfig,
    fitts_duration,
    generate_path,
    _minimum_jerk,
    _minimum_jerk_velocity,
)


class TestMinimumJerk:
    """Tests for the minimum-jerk position profile."""

    def test_starts_at_zero(self):
        assert _minimum_jerk(0.0) == 0.0

    def test_ends_at_one(self):
        assert _minimum_jerk(1.0) == pytest.approx(1.0)

    def test_midpoint_is_half(self):
        # The minimum-jerk profile passes through 0.5 at t=0.5.
        assert _minimum_jerk(0.5) == pytest.approx(0.5)

    def test_monotonically_increasing(self):
        values = [_minimum_jerk(t / 100) for t in range(101)]
        for i in range(1, len(values)):
            assert values[i] >= values[i - 1]

    def test_smooth_s_curve(self):
        # Early and late should be slower than middle.
        early = _minimum_jerk(0.1)
        mid = _minimum_jerk(0.5)
        late = _minimum_jerk(0.9)
        assert early < 0.5
        assert mid == pytest.approx(0.5)
        assert late > 0.5

    def test_quarter_points(self):
        q1 = _minimum_jerk(0.25)
        q3 = _minimum_jerk(0.75)
        # Quarter points should be symmetric around 0.5
        assert q1 == pytest.approx(1.0 - q3, abs=1e-10)


class TestMinimumJerkVelocity:
    """Tests for the velocity profile (derivative of minimum-jerk)."""

    def test_zero_at_start(self):
        assert _minimum_jerk_velocity(0.0) == pytest.approx(0.0)

    def test_zero_at_end(self):
        assert _minimum_jerk_velocity(1.0) == pytest.approx(0.0)

    def test_peak_near_middle(self):
        # Velocity peaks around t=0.5.
        velocities = [_minimum_jerk_velocity(t / 100) for t in range(101)]
        peak_idx = velocities.index(max(velocities))
        assert 40 <= peak_idx <= 60

    def test_bell_shaped(self):
        # Velocity at midpoint should be higher than at quarter points.
        v_quarter = _minimum_jerk_velocity(0.25)
        v_mid = _minimum_jerk_velocity(0.5)
        v_three_quarter = _minimum_jerk_velocity(0.75)
        assert v_mid > v_quarter
        assert v_mid > v_three_quarter

    def test_peak_value(self):
        # Analytical peak of 30t² - 60t³ + 30t⁴ is 1.875 at t=0.5.
        assert _minimum_jerk_velocity(0.5) == pytest.approx(1.875)


class TestFittsDuration:
    def test_short_distance_uses_min_duration(self):
        config = MotionConfig(min_duration=0.1)
        assert fitts_duration(0.5, 20.0, config) == 0.1

    def test_longer_distance_longer_duration(self):
        config = MotionConfig(seed=42)
        short = fitts_duration(100, 20.0, config)
        long = fitts_duration(1000, 20.0, config)
        assert long > short

    def test_larger_target_shorter_duration(self):
        config = MotionConfig(seed=42)
        small_target = fitts_duration(500, 10.0, config)
        large_target = fitts_duration(500, 100.0, config)
        assert large_target < small_target

    def test_respects_max_duration(self):
        config = MotionConfig(max_duration=1.5)
        d = fitts_duration(100000, 1.0, config)
        assert d <= 1.5

    def test_respects_min_duration(self):
        config = MotionConfig(min_duration=0.2)
        d = fitts_duration(10, 1000.0, config)
        assert d >= 0.2


class TestGeneratePath:
    """Tests for the full path generation."""

    def test_starts_at_start(self):
        path = generate_path((100, 200), (500, 600), duration=0.5, config=MotionConfig(seed=42))
        assert path[0][0] == 100
        assert path[0][1] == 200
        assert path[0][2] == 0.0

    def test_ends_at_end(self):
        path = generate_path((100, 200), (500, 600), duration=0.5, config=MotionConfig(seed=42))
        assert path[-1][0] == 500
        assert path[-1][1] == 600

    def test_end_timestamp_matches_duration(self):
        path = generate_path((0, 0), (100, 100), duration=0.3, config=MotionConfig(seed=42))
        assert path[-1][2] == pytest.approx(0.3)

    def test_timestamps_monotonically_increase(self):
        path = generate_path((0, 0), (500, 500), duration=0.5, config=MotionConfig(seed=42))
        for i in range(1, len(path)):
            assert path[i][2] >= path[i - 1][2]

    def test_reasonable_number_of_points(self):
        config = MotionConfig(points_per_second=100, seed=42)
        path = generate_path((0, 0), (500, 500), duration=0.5, config=config)
        # 0.5 seconds * 100 points/sec = 50 points + 1 (start)
        assert len(path) == 51

    def test_zero_distance_returns_two_points(self):
        path = generate_path((100, 200), (100, 200), duration=0.1, config=MotionConfig(seed=42))
        assert len(path) == 2
        assert path[0][:2] == (100, 200)
        assert path[1][:2] == (100, 200)

    def test_path_stays_near_line(self):
        """Path points should be within reasonable distance of the direct line."""
        config = MotionConfig(curvature=0.1, noise_magnitude=1.0, seed=42)
        start = (0.0, 0.0)
        end = (1000.0, 0.0)
        path = generate_path(start, end, duration=0.5, config=config)

        for x, y, _ in path:
            # Should stay within 15% of the distance from the line.
            assert abs(y) < 150, f"Point ({x}, {y}) too far from line"

    def test_curvature_zero_stays_straight(self):
        """With zero curvature and noise, path should be nearly straight."""
        config = MotionConfig(curvature=0.0, noise_magnitude=0.0, overshoot=0.0, seed=42)
        path = generate_path((0.0, 0.0), (1000.0, 0.0), duration=0.5, config=config)

        for x, y, _ in path:
            assert abs(y) < 0.01, f"Expected y≈0 with zero curvature, got {y}"

    def test_reproducible_with_seed(self):
        config1 = MotionConfig(seed=123)
        config2 = MotionConfig(seed=123)
        path1 = generate_path((0, 0), (500, 500), duration=0.5, config=config1)
        path2 = generate_path((0, 0), (500, 500), duration=0.5, config=config2)
        assert path1 == path2

    def test_different_seeds_different_paths(self):
        config1 = MotionConfig(seed=1)
        config2 = MotionConfig(seed=2)
        path1 = generate_path((0, 0), (500, 500), duration=0.5, config=config1)
        path2 = generate_path((0, 0), (500, 500), duration=0.5, config=config2)
        # Endpoints are the same, but intermediate points differ.
        assert path1[0] == path2[0]
        assert path1[-1] == path2[-1]
        assert path1 != path2

    def test_auto_duration_via_fitts_law(self):
        """When duration is None, it should be estimated from distance."""
        config = MotionConfig(seed=42)
        path = generate_path((0, 0), (500, 500), config=config)
        duration = path[-1][2]
        assert config.min_duration <= duration <= config.max_duration

    def test_short_move_short_duration(self):
        config = MotionConfig(seed=42)
        short = generate_path((0, 0), (10, 10), config=config)
        long = generate_path((0, 0), (1000, 1000), config=config)
        assert short[-1][2] < long[-1][2]

    def test_overshoot_on_long_distance(self):
        """On long movements, the path should overshoot past the target."""
        config = MotionConfig(
            overshoot=0.05,
            overshoot_threshold=50,
            curvature=0.0,
            noise_magnitude=0.0,
            seed=42,
        )
        path = generate_path((0.0, 0.0), (1000.0, 0.0), duration=0.5, config=config)

        # Check if any point has x > 1000 (overshot the target).
        max_x = max(p[0] for p in path)
        assert max_x > 1000.0, f"Expected overshoot past x=1000, max was {max_x}"

    def test_no_overshoot_on_short_distance(self):
        """Short movements should not overshoot."""
        config = MotionConfig(
            overshoot=0.05,
            overshoot_threshold=500,
            curvature=0.0,
            noise_magnitude=0.0,
            seed=42,
        )
        path = generate_path((0.0, 0.0), (100.0, 0.0), duration=0.3, config=config)

        # No point should exceed the target by more than a tiny amount.
        max_x = max(p[0] for p in path)
        assert max_x <= 101.0, f"Short move shouldn't overshoot, max was {max_x}"

    def test_diagonal_movement(self):
        config = MotionConfig(seed=42)
        path = generate_path((0, 0), (300, 400), duration=0.3, config=config)
        assert path[0][:2] == (0, 0)
        assert path[-1][:2] == (300, 400)

    def test_negative_coordinates(self):
        """Should handle paths crossing through negative coords."""
        config = MotionConfig(seed=42, curvature=0.0, noise_magnitude=0.0, overshoot=0.0)
        path = generate_path((100.0, 100.0), (-100.0, -100.0), duration=0.3, config=config)
        assert path[-1][:2] == (-100.0, -100.0)

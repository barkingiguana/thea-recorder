"""Human-like mouse interaction.

Wraps xdotool mouse input with smooth, natural-looking movement
based on the minimum-jerk trajectory model.
"""

from __future__ import annotations

import time

from . import xdotool
from .motion import MotionConfig, generate_path


class Mouse:
    """Simulates human-like mouse interaction on an X11 display.

    Args:
        env: Environment dict with ``DISPLAY`` set.
        motion: Mouse movement configuration.  Uses defaults if *None*.
    """

    def __init__(self, env: dict, motion: MotionConfig | None = None):
        self._env = env
        self._motion = motion or MotionConfig()

    @property
    def motion(self) -> MotionConfig:
        """The current motion configuration."""
        return self._motion

    def position(self) -> tuple[int, int]:
        """Get the current mouse cursor position."""
        return xdotool.mouse_location(self._env)

    def move_to(
        self,
        x: int,
        y: int,
        *,
        duration: float | None = None,
        target_width: float | None = None,
    ) -> None:
        """Move the mouse cursor to ``(x, y)`` with human-like motion.

        The cursor follows a smooth, slightly curved path with natural
        acceleration and deceleration (minimum-jerk model).

        Args:
            x: Target X coordinate.
            y: Target Y coordinate.
            duration: Movement time in seconds.  *None* estimates from
                distance using Fitts's Law.
            target_width: Size of the target in pixels (affects duration
                estimation).  Larger targets are reached faster.
        """
        start = self.position()
        path = generate_path(
            start=(float(start[0]), float(start[1])),
            end=(float(x), float(y)),
            duration=duration,
            target_width=target_width,
            config=self._motion,
        )

        if len(path) < 2:
            xdotool.mouse_move(x, y, self._env)
            return

        t_start = time.monotonic()
        for px, py, t_target in path[1:]:
            # Sleep until this point's timestamp.
            now = time.monotonic() - t_start
            if t_target > now:
                time.sleep(t_target - now)
            xdotool.mouse_move(int(round(px)), int(round(py)), self._env)

    def click(
        self,
        x: int | None = None,
        y: int | None = None,
        *,
        button: int = 1,
        duration: float | None = None,
    ) -> None:
        """Move to ``(x, y)`` and click.

        If *x* and *y* are *None*, clicks at the current position.

        Args:
            x: Target X coordinate.
            y: Target Y coordinate.
            button: Mouse button (1=left, 2=middle, 3=right).
            duration: Movement time.  *None* for Fitts's Law estimation.
        """
        if x is not None and y is not None:
            self.move_to(x, y, duration=duration)
            # Small random delay between arriving and clicking (human pause).
            time.sleep(self._motion._rng.uniform(0.05, 0.15))
        xdotool.mouse_click(button, self._env)

    def double_click(
        self,
        x: int | None = None,
        y: int | None = None,
        *,
        duration: float | None = None,
    ) -> None:
        """Move to ``(x, y)`` and double-click."""
        if x is not None and y is not None:
            self.move_to(x, y, duration=duration)
            time.sleep(self._motion._rng.uniform(0.05, 0.12))
        xdotool.mouse_click(1, self._env)
        time.sleep(self._motion._rng.uniform(0.05, 0.10))
        xdotool.mouse_click(1, self._env)

    def right_click(
        self,
        x: int | None = None,
        y: int | None = None,
        *,
        duration: float | None = None,
    ) -> None:
        """Move to ``(x, y)`` and right-click."""
        self.click(x, y, button=3, duration=duration)

    def drag(
        self,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
        *,
        button: int = 1,
        duration: float | None = None,
    ) -> None:
        """Drag from one position to another.

        Moves to *start*, presses the button, moves to *end* with
        human-like motion, then releases.
        """
        self.move_to(start_x, start_y)
        time.sleep(self._motion._rng.uniform(0.05, 0.15))
        xdotool.mouse_down(button, self._env)
        time.sleep(self._motion._rng.uniform(0.05, 0.10))
        self.move_to(end_x, end_y, duration=duration)
        time.sleep(self._motion._rng.uniform(0.05, 0.10))
        xdotool.mouse_up(button, self._env)

    def scroll(self, clicks: int, *, x: int | None = None, y: int | None = None) -> None:
        """Scroll the mouse wheel.

        Args:
            clicks: Number of scroll clicks.  Positive = down, negative = up.
            x: Scroll at this X position (moves cursor first).
            y: Scroll at this Y position.
        """
        if x is not None and y is not None:
            self.move_to(x, y)
            time.sleep(0.05)

        button = 5 if clicks > 0 else 4  # 5=scroll down, 4=scroll up
        for _ in range(abs(clicks)):
            xdotool.mouse_click(button, self._env)
            time.sleep(self._motion._rng.uniform(0.05, 0.12))

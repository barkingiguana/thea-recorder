"""Window management for X11 displays.

Find, focus, move, resize, and arrange application windows.
Requires a window manager (e.g. openbox) running on the display.
"""

from __future__ import annotations

import math
import time

from . import xdotool


class Window:
    """A handle to an X11 window.

    Don't construct directly — use :meth:`Director.window` or
    :func:`find_window` to obtain a Window.

    Args:
        window_id: The X11 window ID (as a string).
        env: Environment dict with ``DISPLAY`` set.
    """

    def __init__(self, window_id: str, env: dict):
        self._id = window_id
        self._env = env

    @property
    def id(self) -> str:
        """The X11 window ID."""
        return self._id

    def focus(self) -> Window:
        """Activate and focus this window (raise to front).

        Returns self for chaining.
        """
        xdotool.window_activate(self._id, self._env)
        xdotool.window_focus(self._id, self._env)
        time.sleep(0.2)
        return self

    def move(self, x: int, y: int) -> Window:
        """Move the window to ``(x, y)``.  Returns self for chaining."""
        xdotool.window_move(self._id, x, y, self._env)
        return self

    def resize(self, width: int, height: int) -> Window:
        """Resize the window.  Returns self for chaining."""
        xdotool.window_resize(self._id, width, height, self._env)
        return self

    def minimize(self) -> Window:
        """Minimise the window.  Returns self for chaining."""
        xdotool.window_minimize(self._id, self._env)
        return self

    @property
    def geometry(self) -> tuple[int, int, int, int]:
        """Current geometry as ``(x, y, width, height)``."""
        return xdotool.window_get_geometry(self._id, self._env)


def find_window(
    name: str,
    env: dict,
    *,
    timeout: float = 10.0,
    poll_interval: float = 0.5,
) -> Window:
    """Wait for a window matching *name* to appear, then return it.

    Searches by window title (substring match).

    Args:
        name: Substring to match against window titles.
        env: Environment dict with ``DISPLAY`` set.
        timeout: Seconds to wait before raising RuntimeError.
        poll_interval: Seconds between search attempts.

    Raises:
        RuntimeError: If no matching window appears within *timeout*.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        ids = xdotool.window_search(name, env)
        if ids:
            return Window(ids[0], env)
        time.sleep(poll_interval)
    raise RuntimeError(f"Window matching {name!r} not found within {timeout}s")


def find_window_by_class(
    class_name: str,
    env: dict,
    *,
    timeout: float = 10.0,
    poll_interval: float = 0.5,
) -> Window:
    """Wait for a window with the given WM_CLASS to appear.

    Args:
        class_name: WM_CLASS to match (e.g. ``'chromium'``, ``'xterm'``).
        env: Environment dict with ``DISPLAY`` set.
        timeout: Seconds to wait.
        poll_interval: Seconds between attempts.

    Raises:
        RuntimeError: If no matching window appears within *timeout*.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        ids = xdotool.window_search_class(class_name, env)
        if ids:
            return Window(ids[0], env)
        time.sleep(poll_interval)
    raise RuntimeError(f"Window with class {class_name!r} not found within {timeout}s")


def tile(
    windows: list[Window],
    layout: str = "side-by-side",
    *,
    bounds: tuple[int, int, int, int] | None = None,
) -> None:
    """Arrange windows in a tiled layout.

    Args:
        windows: Windows to tile.
        layout: ``"side-by-side"`` (horizontal), ``"stacked"``
            (vertical), or ``"grid"``.
        bounds: ``(x, y, width, height)`` of the tiling area.
            If *None*, uses the first window's current position as
            origin and assumes a 1920x1080 area.
    """
    if not windows:
        return

    if bounds is None:
        bounds = (0, 0, 1920, 1080)

    bx, by, bw, bh = bounds
    n = len(windows)

    if layout == "side-by-side":
        tile_w = bw // n
        for i, win in enumerate(windows):
            win.move(bx + i * tile_w, by).resize(tile_w, bh)
    elif layout == "stacked":
        tile_h = bh // n
        for i, win in enumerate(windows):
            win.move(bx, by + i * tile_h).resize(bw, tile_h)
    elif layout == "grid":
        cols = math.ceil(math.sqrt(n))
        rows = math.ceil(n / cols)
        tile_w = bw // cols
        tile_h = bh // rows
        for i, win in enumerate(windows):
            col = i % cols
            row = i // cols
            win.move(bx + col * tile_w, by + row * tile_h).resize(tile_w, tile_h)
    else:
        raise ValueError(f"Unknown layout: {layout!r}")

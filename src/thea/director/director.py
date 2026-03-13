"""The Director: facade for display interaction.

Combines keyboard, mouse, and window management into a single
entry point.
"""

from __future__ import annotations

import os
import subprocess
import time

from .keyboard import Keyboard
from .motion import MotionConfig
from .mouse import Mouse
from .rhythm import RhythmConfig
from .window import Window, find_window, find_window_by_class, tile
from . import xdotool


class Director:
    """Orchestrates human-like interaction on an X11 display.

    The Director is the main entry point for thea-director.  It provides
    access to keyboard, mouse, and window management, and ensures a
    window manager is running (required for reliable window operations).

    Args:
        display: X11 display string (e.g. ``":99"``), or a dict with
            ``DISPLAY`` set (e.g. from ``Recorder.display_env``).
        motion: Mouse movement configuration.
        rhythm: Typing rhythm configuration.
        ensure_wm: If *True* (default), starts a minimal window manager
            (openbox) if one isn't already running on the display.
    """

    def __init__(
        self,
        display: str | dict,
        *,
        motion: MotionConfig | None = None,
        rhythm: RhythmConfig | None = None,
        ensure_wm: bool = True,
    ):
        if isinstance(display, dict):
            self._env = dict(display)
        else:
            self._env = {**os.environ, "DISPLAY": display}

        self._keyboard = Keyboard(self._env, rhythm)
        self._mouse = Mouse(self._env, motion)
        self._wm_proc: subprocess.Popen | None = None

        if ensure_wm:
            self._ensure_window_manager()

    def _ensure_window_manager(self) -> None:
        """Start openbox if no window manager is running.

        Detects an existing WM by checking if there's a window with
        the _NET_SUPPORTING_WM_CHECK property (EWMH standard).
        If not found, starts openbox in the background and waits for
        both ``_NET_SUPPORTING_WM_CHECK`` and ``_NET_SUPPORTED`` to
        confirm it is fully ready to manage windows.
        """
        result = subprocess.run(
            ["xprop", "-root", "_NET_SUPPORTING_WM_CHECK"],
            env=self._env,
            capture_output=True,
            text=True,
        )
        if "window id" in result.stdout.lower():
            return  # WM already running

        self._wm_proc = subprocess.Popen(
            ["openbox"],
            env=self._env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        # Poll until the WM advertises EWMH support.
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            result = subprocess.run(
                ["xprop", "-root", "_NET_SUPPORTING_WM_CHECK"],
                env=self._env,
                capture_output=True,
                text=True,
            )
            if "window id" in result.stdout.lower():
                break
            time.sleep(0.1)

        # Wait for _NET_SUPPORTED — confirms the WM is fully ready to
        # manage windows (not just that it has created its check window).
        while time.monotonic() < deadline:
            result = subprocess.run(
                ["xprop", "-root", "_NET_SUPPORTED"],
                env=self._env,
                capture_output=True,
                text=True,
            )
            if "_NET_SUPPORTED" in result.stdout and "no such atom" not in result.stdout.lower():
                break
            time.sleep(0.1)

        # Verify the WM can actually handle focus requests by launching a
        # throwaway window, focusing it, then killing it.  EWMH properties
        # appear before openbox is ready to manage focus (#36).
        self._verify_wm_focus_ready(deadline)

    def _verify_wm_focus_ready(self, deadline: float) -> None:
        """Launch a test window and verify focus works before returning.

        This catches the race where openbox advertises EWMH properties but
        cannot yet handle X_SetInputFocus requests (#36).
        """
        test_proc = subprocess.Popen(
            ["xterm", "-geometry", "1x1+0+0", "-e", "sleep 10"],
            env=self._env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            # Wait for the test window to appear.
            wid = None
            while time.monotonic() < deadline:
                result = subprocess.run(
                    ["xdotool", "search", "--pid", str(test_proc.pid)],
                    env=self._env,
                    capture_output=True,
                    text=True,
                )
                if result.returncode == 0 and result.stdout.strip():
                    wid = result.stdout.strip().split("\n")[0]
                    break
                time.sleep(0.1)

            if wid is None:
                return  # Could not find test window; skip verification.

            # Try to focus the test window — retry until it works.
            while time.monotonic() < deadline:
                result = subprocess.run(
                    ["xdotool", "windowactivate", "--sync", wid],
                    env=self._env,
                    capture_output=True,
                    text=True,
                )
                if result.returncode == 0:
                    break
                time.sleep(0.2)
        finally:
            test_proc.terminate()
            try:
                test_proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                test_proc.kill()

    @property
    def env(self) -> dict:
        """The environment dict with ``DISPLAY`` set."""
        return self._env

    @property
    def keyboard(self) -> Keyboard:
        """Human-like keyboard interaction."""
        return self._keyboard

    @property
    def mouse(self) -> Mouse:
        """Human-like mouse interaction."""
        return self._mouse

    def window(self, name: str, *, timeout: float = 10.0) -> Window:
        """Find a window by title (substring match) and return a handle.

        Waits up to *timeout* seconds for the window to appear.

        Args:
            name: Substring to match against window titles.
            timeout: Seconds to wait before raising RuntimeError.
        """
        return find_window(name, self._env, timeout=timeout)

    def window_by_class(self, class_name: str, *, timeout: float = 10.0) -> Window:
        """Find a window by WM_CLASS and return a handle.

        Args:
            class_name: WM_CLASS to match (e.g. ``'chromium'``).
            timeout: Seconds to wait.
        """
        return find_window_by_class(class_name, self._env, timeout=timeout)

    def tile(
        self,
        windows: list[Window],
        layout: str = "side-by-side",
        *,
        bounds: tuple[int, int, int, int] | None = None,
    ) -> None:
        """Arrange windows in a tiled layout.

        See :func:`window.tile` for layout options.
        """
        tile(windows, layout, bounds=bounds)

    def screenshot(
        self,
        output_path: str,
        *,
        region: tuple[int, int, int, int] | None = None,
    ) -> None:
        """Capture a screenshot of the display.

        Args:
            output_path: Path to save the PNG image.
            region: Optional ``(x, y, width, height)`` sub-region.
        """
        xdotool.screenshot(output_path, self._env, region=region)

    def cleanup(self) -> None:
        """Stop the window manager if we started one."""
        if self._wm_proc and self._wm_proc.poll() is None:
            self._wm_proc.terminate()
            try:
                self._wm_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._wm_proc.kill()
            self._wm_proc = None

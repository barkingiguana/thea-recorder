"""Low-level interface to xdotool.

This module provides thin wrappers around xdotool commands.  The higher-level
classes (Keyboard, Mouse, Window) use these to interact with the X11 display.

All functions take a *display_env* dict (environment with DISPLAY set).
"""

from __future__ import annotations

import os
import subprocess


def _run(args: list[str], env: dict) -> subprocess.CompletedProcess:
    """Run an xdotool command and return the result."""
    return subprocess.run(
        ["xdotool", *args],
        env=env,
        capture_output=True,
        text=True,
    )


def _run_checked(args: list[str], env: dict) -> subprocess.CompletedProcess:
    """Run an xdotool command, raising on failure."""
    result = _run(args, env)
    if result.returncode != 0:
        cmd = " ".join(["xdotool", *args])
        raise RuntimeError(
            f"xdotool failed (exit {result.returncode}): {cmd}\n"
            f"stderr: {result.stderr.strip()}"
        )
    return result


# -- Mouse -----------------------------------------------------------------

def mouse_move(x: int, y: int, env: dict) -> None:
    """Move the mouse cursor to (x, y) instantly."""
    _run_checked(["mousemove", "--sync", str(x), str(y)], env)


def mouse_click(button: int, env: dict) -> None:
    """Click a mouse button (1=left, 2=middle, 3=right)."""
    _run_checked(["click", str(button)], env)


def mouse_down(button: int, env: dict) -> None:
    """Press a mouse button down (without releasing)."""
    _run_checked(["mousedown", str(button)], env)


def mouse_up(button: int, env: dict) -> None:
    """Release a mouse button."""
    _run_checked(["mouseup", str(button)], env)


def mouse_location(env: dict) -> tuple[int, int]:
    """Get the current mouse cursor position."""
    result = _run_checked(["getmouselocation"], env)
    # Output: "x:123 y:456 screen:0 window:12345"
    parts = result.stdout.strip().split()
    x = int(parts[0].split(":")[1])
    y = int(parts[1].split(":")[1])
    return (x, y)


# -- Keyboard --------------------------------------------------------------

def key_press(key: str, env: dict) -> None:
    """Send a key press (press + release).  e.g. 'Return', 'ctrl+s'."""
    _run_checked(["key", "--clearmodifiers", key], env)


def key_down(key: str, env: dict) -> None:
    """Press a key down (without releasing)."""
    _run_checked(["keydown", key], env)


def key_up(key: str, env: dict) -> None:
    """Release a key."""
    _run_checked(["keyup", key], env)


def key_type_char(char: str, env: dict) -> None:
    """Type a single character using xdotool type."""
    _run_checked(["type", "--clearmodifiers", "--delay", "0", char], env)


# -- Window ----------------------------------------------------------------

def window_search(name: str, env: dict) -> list[str]:
    """Search for windows by name (substring match).  Returns window IDs."""
    result = _run(["search", "--name", name], env)
    if result.returncode != 0 or not result.stdout.strip():
        return []
    return result.stdout.strip().split("\n")


def window_search_class(class_name: str, env: dict) -> list[str]:
    """Search for windows by WM_CLASS.  Returns window IDs."""
    result = _run(["search", "--class", class_name], env)
    if result.returncode != 0 or not result.stdout.strip():
        return []
    return result.stdout.strip().split("\n")


def window_focus(window_id: str, env: dict) -> None:
    """Focus a window by ID."""
    _run_checked(["windowfocus", "--sync", window_id], env)


def window_activate(window_id: str, env: dict) -> None:
    """Activate (raise + focus) a window by ID."""
    _run_checked(["windowactivate", "--sync", window_id], env)


def window_move(window_id: str, x: int, y: int, env: dict) -> None:
    """Move a window to (x, y)."""
    _run_checked(["windowmove", "--sync", window_id, str(x), str(y)], env)


def window_resize(window_id: str, width: int, height: int, env: dict) -> None:
    """Resize a window."""
    _run_checked(["windowsize", "--sync", window_id, str(width), str(height)], env)


def window_minimize(window_id: str, env: dict) -> None:
    """Minimise a window."""
    _run_checked(["windowminimize", window_id], env)


def window_get_geometry(window_id: str, env: dict) -> tuple[int, int, int, int]:
    """Get window geometry: (x, y, width, height)."""
    result = _run_checked(["getwindowgeometry", "--shell", window_id], env)
    # Output lines: WINDOW=id, X=n, Y=n, WIDTH=n, HEIGHT=n, SCREEN=n
    values = {}
    for line in result.stdout.strip().split("\n"):
        if "=" in line:
            k, v = line.split("=", 1)
            values[k.strip()] = v.strip()
    return (
        int(values.get("X", 0)),
        int(values.get("Y", 0)),
        int(values.get("WIDTH", 0)),
        int(values.get("HEIGHT", 0)),
    )


def window_get_active(env: dict) -> str | None:
    """Get the currently active window ID, or None."""
    result = _run(["getactivewindow"], env)
    if result.returncode != 0 or not result.stdout.strip():
        return None
    return result.stdout.strip()


# -- Screenshot (via ImageMagick import) -----------------------------------

def screenshot(output_path: str, env: dict, region: tuple[int, int, int, int] | None = None) -> None:
    """Capture a screenshot of the display.

    Args:
        output_path: Path to save the image (PNG).
        env: Environment with DISPLAY set.
        region: Optional (x, y, width, height) to capture a sub-region.
    """
    if region:
        x, y, w, h = region
        geometry = f"{w}x{h}+{x}+{y}"
        cmd = ["import", "-window", "root", "-crop", geometry, output_path]
    else:
        cmd = ["import", "-window", "root", output_path]
    subprocess.run(cmd, env=env, check=True, capture_output=True)

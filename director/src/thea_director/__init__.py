"""thea-director: human-like display interaction for Thea recordings.

The Director orchestrates keyboard, mouse, and window interaction on
an X11 display.  It produces input that looks like a real human is
using the application — smooth mouse curves, natural typing rhythm,
and realistic pauses.

Thea records the display.  The Director directs the action on it.

Quick start::

    from thea_director import Director

    director = Director(":99")  # connect to display :99

    # Human-like keyboard
    director.keyboard.type("Hello, world!", wpm=65)
    director.keyboard.press("Return")

    # Human-like mouse
    director.mouse.click(500, 300)
    director.mouse.drag(100, 100, 500, 500)

    # Window management
    window = director.window("My App")
    window.focus()
    window.move(0, 0).resize(1280, 720)
"""

from .director import Director
from .keyboard import Keyboard
from .motion import MotionConfig
from .mouse import Mouse
from .rhythm import RhythmConfig
from .window import Window, find_window, find_window_by_class, tile

__all__ = [
    "Director",
    "Keyboard",
    "Mouse",
    "Window",
    "MotionConfig",
    "RhythmConfig",
    "find_window",
    "find_window_by_class",
    "tile",
]

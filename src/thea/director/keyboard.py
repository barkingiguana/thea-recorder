"""Human-like keyboard interaction.

Wraps xdotool key input with realistic typing rhythm derived from
the rhythm model.
"""

from __future__ import annotations

import time

from . import xdotool
from .rhythm import RhythmConfig, generate_delays


class Keyboard:
    """Simulates human-like keyboard input on an X11 display.

    Args:
        env: Environment dict with ``DISPLAY`` set.
        rhythm: Typing rhythm configuration.  Uses defaults if *None*.
    """

    def __init__(self, env: dict, rhythm: RhythmConfig | None = None):
        self._env = env
        self._rhythm = rhythm or RhythmConfig()

    @property
    def rhythm(self) -> RhythmConfig:
        """The current rhythm configuration."""
        return self._rhythm

    def type(self, text: str, *, wpm: float | None = None) -> None:
        """Type text with human-like rhythm.

        Each character is typed individually with inter-key delays that
        mimic a real typist (see :mod:`rhythm` for the model).

        Args:
            text: The string to type.
            wpm: Override the typing speed for this call.  *None* uses
                the configured default.
        """
        if not text:
            return

        config = self._rhythm
        if wpm is not None:
            # Create a temporary config with the overridden WPM.
            config = RhythmConfig(
                wpm=wpm,
                variance=self._rhythm.variance,
                shift_penalty=self._rhythm.shift_penalty,
                word_pause=self._rhythm.word_pause,
                fast_bigram_bonus=self._rhythm.fast_bigram_bonus,
                slow_bigram_penalty=self._rhythm.slow_bigram_penalty,
                pause_probability=self._rhythm.pause_probability,
                pause_duration=self._rhythm.pause_duration,
                min_delay=self._rhythm.min_delay,
                seed=self._rhythm.seed,
            )

        delays = generate_delays(text, config)

        for char, delay in zip(text, delays):
            time.sleep(delay)
            xdotool.key_type_char(char, self._env)

    def press(self, *keys: str) -> None:
        """Press one or more keys (e.g. ``'Return'``, ``'ctrl+s'``).

        Each key is pressed and released in sequence with a short
        delay between them.

        Args:
            keys: Key names as understood by xdotool (e.g. ``'Tab'``,
                ``'ctrl+shift+p'``, ``'F5'``).
        """
        for key in keys:
            xdotool.key_press(key, self._env)
            time.sleep(0.05)

    def hold(self, key: str) -> None:
        """Press a key down without releasing it.

        Use :meth:`release` to release it later.  Useful for
        Shift-selecting or keyboard shortcuts with held modifiers.
        """
        xdotool.key_down(key, self._env)

    def release(self, key: str) -> None:
        """Release a previously held key."""
        xdotool.key_up(key, self._env)

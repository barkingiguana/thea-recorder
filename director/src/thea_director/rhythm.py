"""Human-like typing rhythm model.

Generates inter-key delays that mimic a real typist.  The model accounts
for:

- **Words per minute (WPM)**: base typing speed.
- **Bigram frequency**: common letter pairs (th, er, in) are typed faster
  because the fingers are already in position.  Uncommon pairs (qz, xj)
  are slower.
- **Shifted characters**: uppercase letters, symbols like @#$ take longer
  because the typist must hold Shift.
- **Word boundaries**: a small pause after space (the typist is reading
  the next word).
- **Gaussian variance**: natural rhythm isn't metronomic — each keystroke
  has random timing variation.
- **Burst and pause**: occasionally the typist speeds up (burst) or
  pauses briefly (thinking).

All randomness uses a configurable seed for reproducibility in tests.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field


# Common English bigrams (letter pairs typed quickly due to finger position).
# Relative frequency ranking — the higher the score, the faster they're typed.
_FAST_BIGRAMS = {
    "th", "he", "in", "er", "an", "re", "on", "at", "en", "nd",
    "ti", "es", "or", "te", "of", "ed", "is", "it", "al", "ar",
    "st", "to", "nt", "ng", "se", "ha", "as", "ou", "io", "le",
    "ve", "co", "me", "de", "hi", "ri", "ro", "ic", "ne", "ea",
    "ra", "ce", "li", "ch", "ll", "be", "ma", "si", "om", "ur",
}

# Awkward bigrams (require hand repositioning or same-finger consecutive).
_SLOW_BIGRAMS = {
    "qw", "qz", "zx", "xc", "bf", "gb", "uj", "yh", "mj", "ki",
    "ws", "pl", "za", "sx", "dc", "fv", "gt", "hy", "ju", "ik",
}

_SHIFTED_CHARS = set('ABCDEFGHIJKLMNOPQRSTUVWXYZ!@#$%^&*()_+{}|:"<>?~')


@dataclass
class RhythmConfig:
    """Tuning parameters for human-like typing rhythm."""

    #: Target typing speed in words per minute.
    #: 40 = casual, 60 = moderate, 80 = fast, 100+ = expert.
    wpm: float = 65.0

    #: Standard deviation of inter-key delay as a fraction of base delay.
    #: 0.2 = ±20% variation.
    variance: float = 0.20

    #: Extra delay for shifted characters (fraction of base delay).
    shift_penalty: float = 0.4

    #: Extra delay after space (fraction of base delay).
    #: Models the pause between words as the typist reads ahead.
    word_pause: float = 0.3

    #: Speed boost for common bigrams (fraction of base delay to subtract).
    fast_bigram_bonus: float = 0.15

    #: Speed penalty for awkward bigrams (fraction of base delay to add).
    slow_bigram_penalty: float = 0.25

    #: Probability of a brief "thinking" pause on any given keystroke.
    pause_probability: float = 0.02

    #: Duration of a thinking pause in seconds (mean).
    pause_duration: float = 0.4

    #: Minimum inter-key delay in seconds (physical limit).
    min_delay: float = 0.03

    #: Random seed.  *None* means use system entropy.
    seed: int | None = None

    #: Internal RNG.
    _rng: random.Random = field(init=False, repr=False)

    def __post_init__(self):
        self._rng = random.Random(self.seed)


def base_delay(config: RhythmConfig) -> float:
    """Mean inter-key delay in seconds for the configured WPM.

    Standard: 1 word ≈ 5 characters.  So chars/second = WPM * 5 / 60.
    Delay = 1 / chars_per_second.
    """
    chars_per_second = config.wpm * 5.0 / 60.0
    return 1.0 / max(chars_per_second, 0.1)


def generate_delays(text: str, config: RhythmConfig | None = None) -> list[float]:
    """Generate a delay (in seconds) before each character in *text*.

    Returns a list the same length as *text*.  The first element is
    the delay before typing the first character (usually near zero
    or a small pre-typing pause).

    Args:
        text: The string to be typed.
        config: Typing rhythm parameters.  Uses defaults if *None*.
    """
    if config is None:
        config = RhythmConfig()
    if not text:
        return []

    rng = config._rng
    bd = base_delay(config)
    delays: list[float] = []

    prev_char = ""
    for i, char in enumerate(text):
        delay = bd

        # Gaussian variance.
        delay += rng.gauss(0, bd * config.variance)

        # Bigram adjustment.
        if prev_char:
            bigram = (prev_char + char).lower()
            if bigram in _FAST_BIGRAMS:
                delay -= bd * config.fast_bigram_bonus
            elif bigram in _SLOW_BIGRAMS:
                delay += bd * config.slow_bigram_penalty

        # Shifted character penalty.
        if char in _SHIFTED_CHARS:
            delay += bd * config.shift_penalty

        # Post-word pause.
        if prev_char == " ":
            delay += bd * config.word_pause

        # Random thinking pause.
        if rng.random() < config.pause_probability:
            delay += abs(rng.gauss(config.pause_duration, config.pause_duration * 0.3))

        delays.append(max(delay, config.min_delay))
        prev_char = char

    return delays

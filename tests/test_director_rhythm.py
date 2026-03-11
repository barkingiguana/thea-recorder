"""Tests for the human-like typing rhythm model."""

import pytest

from thea.director.rhythm import (
    RhythmConfig,
    base_delay,
    generate_delays,
    _FAST_BIGRAMS,
    _SLOW_BIGRAMS,
    _SHIFTED_CHARS,
)


class TestBaseDelay:
    def test_60_wpm(self):
        config = RhythmConfig(wpm=60)
        # 60 WPM = 300 chars/min = 5 chars/sec => 0.2s delay
        assert base_delay(config) == pytest.approx(0.2)

    def test_120_wpm(self):
        config = RhythmConfig(wpm=120)
        assert base_delay(config) == pytest.approx(0.1)

    def test_30_wpm(self):
        config = RhythmConfig(wpm=30)
        assert base_delay(config) == pytest.approx(0.4)

    def test_zero_wpm_clamped(self):
        config = RhythmConfig(wpm=0)
        # Should not crash; clamped to avoid division by zero.
        d = base_delay(config)
        assert d > 0


class TestGenerateDelays:
    def test_empty_string(self):
        assert generate_delays("") == []

    def test_length_matches_text(self):
        delays = generate_delays("hello", RhythmConfig(seed=42))
        assert len(delays) == 5

    def test_all_positive(self):
        delays = generate_delays("The quick brown fox", RhythmConfig(seed=42))
        for d in delays:
            assert d > 0

    def test_above_minimum(self):
        config = RhythmConfig(min_delay=0.05, seed=42)
        delays = generate_delays("test text", config)
        for d in delays:
            assert d >= 0.05

    def test_reproducible_with_seed(self):
        d1 = generate_delays("hello world", RhythmConfig(seed=42))
        d2 = generate_delays("hello world", RhythmConfig(seed=42))
        assert d1 == d2

    def test_different_seeds_different_delays(self):
        d1 = generate_delays("hello world", RhythmConfig(seed=1))
        d2 = generate_delays("hello world", RhythmConfig(seed=2))
        assert d1 != d2

    def test_faster_wpm_shorter_delays(self):
        slow = generate_delays("test", RhythmConfig(wpm=40, seed=42))
        fast = generate_delays("test", RhythmConfig(wpm=100, seed=42))
        assert sum(fast) < sum(slow)

    def test_shifted_chars_slower(self):
        """Uppercase letters should have longer delays than lowercase."""
        config = RhythmConfig(
            wpm=60, variance=0.0, shift_penalty=0.5,
            fast_bigram_bonus=0.0, slow_bigram_penalty=0.0,
            word_pause=0.0, pause_probability=0.0, seed=42,
        )
        lower_delays = generate_delays("aaaa", config)
        config2 = RhythmConfig(
            wpm=60, variance=0.0, shift_penalty=0.5,
            fast_bigram_bonus=0.0, slow_bigram_penalty=0.0,
            word_pause=0.0, pause_probability=0.0, seed=42,
        )
        upper_delays = generate_delays("AAAA", config2)
        # Each uppercase delay should be longer (shift penalty).
        for l, u in zip(lower_delays, upper_delays):
            assert u > l

    def test_word_pause_after_space(self):
        """Characters after space should have longer delays."""
        config = RhythmConfig(
            wpm=60, variance=0.0, word_pause=0.5,
            fast_bigram_bonus=0.0, slow_bigram_penalty=0.0,
            shift_penalty=0.0, pause_probability=0.0, seed=42,
        )
        delays = generate_delays("a b", config)
        # delays[2] is "b" which comes after " " (space)
        # delays[0] is "a" which starts the string (no prev char)
        assert delays[2] > delays[0]

    def test_fast_bigrams_faster(self):
        """Common bigrams like 'th' should be typed faster."""
        config = RhythmConfig(
            wpm=60, variance=0.0, fast_bigram_bonus=0.2,
            slow_bigram_penalty=0.0, shift_penalty=0.0,
            word_pause=0.0, pause_probability=0.0, seed=42,
        )
        # "th" is a fast bigram; delays[1] should be shorter.
        th_delays = generate_delays("th", config)

        config2 = RhythmConfig(
            wpm=60, variance=0.0, fast_bigram_bonus=0.2,
            slow_bigram_penalty=0.0, shift_penalty=0.0,
            word_pause=0.0, pause_probability=0.0, seed=42,
        )
        # "qz" is not a fast bigram.
        qz_delays = generate_delays("qz", config2)

        assert th_delays[1] < qz_delays[1]

    def test_slow_bigrams_slower(self):
        """Awkward bigrams like 'qz' should be typed slower."""
        config = RhythmConfig(
            wpm=60, variance=0.0, fast_bigram_bonus=0.0,
            slow_bigram_penalty=0.3, shift_penalty=0.0,
            word_pause=0.0, pause_probability=0.0, seed=42,
        )
        qz_delays = generate_delays("qz", config)

        config2 = RhythmConfig(
            wpm=60, variance=0.0, fast_bigram_bonus=0.0,
            slow_bigram_penalty=0.3, shift_penalty=0.0,
            word_pause=0.0, pause_probability=0.0, seed=42,
        )
        ab_delays = generate_delays("ab", config2)

        assert qz_delays[1] > ab_delays[1]

    def test_thinking_pauses_occur(self):
        """With high pause probability, some delays should be much longer."""
        config = RhythmConfig(
            wpm=60, pause_probability=1.0,
            pause_duration=0.5, seed=42,
        )
        delays = generate_delays("hello", config)
        # Every keystroke should have a thinking pause.
        bd = base_delay(config)
        for d in delays:
            assert d > bd * 1.5  # Pause should significantly increase delay

    def test_no_pauses_when_probability_zero(self):
        """With zero pause probability, no thinking pauses."""
        config = RhythmConfig(
            wpm=60, variance=0.0, pause_probability=0.0,
            fast_bigram_bonus=0.0, slow_bigram_penalty=0.0,
            shift_penalty=0.0, word_pause=0.0, seed=42,
        )
        delays = generate_delays("hello", config)
        bd = base_delay(config)
        for d in delays:
            assert d == pytest.approx(bd, abs=0.01)

    def test_single_character(self):
        delays = generate_delays("x", RhythmConfig(seed=42))
        assert len(delays) == 1
        assert delays[0] > 0

    def test_special_characters(self):
        """Should handle special characters without crashing."""
        delays = generate_delays("hello@world.com #123", RhythmConfig(seed=42))
        assert len(delays) == 20
        assert all(d > 0 for d in delays)


class TestBigramSets:
    def test_fast_bigrams_are_lowercase(self):
        for bg in _FAST_BIGRAMS:
            assert bg == bg.lower()
            assert len(bg) == 2

    def test_slow_bigrams_are_lowercase(self):
        for bg in _SLOW_BIGRAMS:
            assert bg == bg.lower()
            assert len(bg) == 2

    def test_no_overlap(self):
        assert _FAST_BIGRAMS.isdisjoint(_SLOW_BIGRAMS)


class TestShiftedChars:
    def test_uppercase_is_shifted(self):
        for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            assert c in _SHIFTED_CHARS

    def test_lowercase_is_not_shifted(self):
        for c in "abcdefghijklmnopqrstuvwxyz":
            assert c not in _SHIFTED_CHARS

    def test_common_symbols_are_shifted(self):
        for c in "!@#$%^&*()_+":
            assert c in _SHIFTED_CHARS

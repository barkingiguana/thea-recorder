"""Tests for the Keyboard class (mocked xdotool)."""

from unittest.mock import patch, call

import pytest

from thea.director.keyboard import Keyboard
from thea.director.rhythm import RhythmConfig


ENV = {"DISPLAY": ":99"}


class TestKeyboardInit:
    def test_default_rhythm(self):
        kb = Keyboard(ENV)
        assert isinstance(kb.rhythm, RhythmConfig)

    def test_custom_rhythm(self):
        config = RhythmConfig(wpm=100)
        kb = Keyboard(ENV, config)
        assert kb.rhythm.wpm == 100


class TestType:
    @patch("thea.director.keyboard.time.sleep")
    @patch("thea.director.keyboard.xdotool.key_type_char")
    def test_types_each_character(self, mock_type, mock_sleep):
        kb = Keyboard(ENV, RhythmConfig(seed=42))
        kb.type("hi")
        assert mock_type.call_count == 2
        mock_type.assert_any_call("h", ENV)
        mock_type.assert_any_call("i", ENV)

    @patch("thea.director.keyboard.time.sleep")
    @patch("thea.director.keyboard.xdotool.key_type_char")
    def test_sleeps_between_characters(self, mock_type, mock_sleep):
        kb = Keyboard(ENV, RhythmConfig(seed=42))
        kb.type("abc")
        assert mock_sleep.call_count == 3
        for c in mock_sleep.call_args_list:
            assert c[0][0] > 0

    @patch("thea.director.keyboard.time.sleep")
    @patch("thea.director.keyboard.xdotool.key_type_char")
    def test_empty_string_does_nothing(self, mock_type, mock_sleep):
        kb = Keyboard(ENV, RhythmConfig(seed=42))
        kb.type("")
        mock_type.assert_not_called()
        mock_sleep.assert_not_called()

    @patch("thea.director.keyboard.time.sleep")
    @patch("thea.director.keyboard.xdotool.key_type_char")
    def test_wpm_override(self, mock_type, mock_sleep):
        kb = Keyboard(ENV, RhythmConfig(wpm=60, seed=42))
        kb.type("ab", wpm=200)
        # Should still type both chars; the delays will be shorter.
        assert mock_type.call_count == 2

    @patch("thea.director.keyboard.time.sleep")
    @patch("thea.director.keyboard.xdotool.key_type_char")
    def test_wpm_override_preserves_other_settings(self, mock_type, mock_sleep):
        config = RhythmConfig(wpm=60, variance=0.1, shift_penalty=0.3, seed=42)
        kb = Keyboard(ENV, config)
        kb.type("A", wpm=120)
        # Should have called sleep with a value > 0.
        assert mock_sleep.call_count == 1
        assert mock_sleep.call_args[0][0] > 0


class TestPress:
    @patch("thea.director.keyboard.time.sleep")
    @patch("thea.director.keyboard.xdotool.key_press")
    def test_single_key(self, mock_press, mock_sleep):
        kb = Keyboard(ENV)
        kb.press("Return")
        mock_press.assert_called_once_with("Return", ENV)

    @patch("thea.director.keyboard.time.sleep")
    @patch("thea.director.keyboard.xdotool.key_press")
    def test_multiple_keys(self, mock_press, mock_sleep):
        kb = Keyboard(ENV)
        kb.press("ctrl+a", "Delete")
        assert mock_press.call_count == 2
        mock_press.assert_any_call("ctrl+a", ENV)
        mock_press.assert_any_call("Delete", ENV)

    @patch("thea.director.keyboard.time.sleep")
    @patch("thea.director.keyboard.xdotool.key_press")
    def test_delay_between_keys(self, mock_press, mock_sleep):
        kb = Keyboard(ENV)
        kb.press("a", "b", "c")
        assert mock_sleep.call_count == 3
        for c in mock_sleep.call_args_list:
            assert c[0][0] == 0.05


class TestHoldRelease:
    @patch("thea.director.keyboard.xdotool.key_down")
    def test_hold(self, mock_down):
        kb = Keyboard(ENV)
        kb.hold("Shift_L")
        mock_down.assert_called_once_with("Shift_L", ENV)

    @patch("thea.director.keyboard.xdotool.key_up")
    def test_release(self, mock_up):
        kb = Keyboard(ENV)
        kb.release("Shift_L")
        mock_up.assert_called_once_with("Shift_L", ENV)

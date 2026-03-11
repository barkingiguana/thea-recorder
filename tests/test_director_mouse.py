"""Tests for the Mouse class (mocked xdotool)."""

from unittest.mock import patch, call, MagicMock

import pytest

from thea.director.mouse import Mouse
from thea.director.motion import MotionConfig


ENV = {"DISPLAY": ":99"}


def _make_mouse(seed=42, **kwargs):
    return Mouse(ENV, MotionConfig(seed=seed, **kwargs))


class TestMouseInit:
    def test_default_motion(self):
        m = Mouse(ENV)
        assert isinstance(m.motion, MotionConfig)

    def test_custom_motion(self):
        config = MotionConfig(min_duration=0.5)
        m = Mouse(ENV, config)
        assert m.motion.min_duration == 0.5


class TestPosition:
    @patch("thea.director.mouse.xdotool.mouse_location", return_value=(100, 200))
    def test_returns_position(self, mock_loc):
        m = _make_mouse()
        assert m.position() == (100, 200)
        mock_loc.assert_called_once_with(ENV)


class TestMoveTo:
    @patch("thea.director.mouse.time.sleep")
    @patch("thea.director.mouse.time.monotonic")
    @patch("thea.director.mouse.xdotool.mouse_move")
    @patch("thea.director.mouse.xdotool.mouse_location", return_value=(0, 0))
    def test_moves_through_path_points(self, mock_loc, mock_move, mock_mono, mock_sleep):
        # Simulate time progressing fast so no sleeps needed.
        mock_mono.side_effect = [0.0] + [10.0] * 200
        m = _make_mouse()
        m.move_to(500, 500, duration=0.5)
        # Should have called mouse_move multiple times (path points).
        assert mock_move.call_count > 1
        # Last call should be near the target.
        last_call = mock_move.call_args_list[-1]
        assert last_call == call(500, 500, ENV)

    @patch("thea.director.mouse.time.sleep")
    @patch("thea.director.mouse.time.monotonic")
    @patch("thea.director.mouse.xdotool.mouse_move")
    @patch("thea.director.mouse.xdotool.mouse_location", return_value=(500, 500))
    def test_zero_distance_still_moves(self, mock_loc, mock_move, mock_mono, mock_sleep):
        mock_mono.side_effect = [0.0] + [10.0] * 50
        m = _make_mouse()
        m.move_to(500, 500, duration=0.1)
        # Should have at least one move call (for the zero-distance case).
        assert mock_move.call_count >= 1


class TestClick:
    @patch("thea.director.mouse.xdotool.mouse_click")
    @patch("thea.director.mouse.Mouse.move_to")
    @patch("thea.director.mouse.time.sleep")
    def test_click_at_position(self, mock_sleep, mock_move, mock_click):
        m = _make_mouse()
        m.click(100, 200)
        mock_move.assert_called_once_with(100, 200, duration=None)
        mock_click.assert_called_once_with(1, ENV)

    @patch("thea.director.mouse.xdotool.mouse_click")
    @patch("thea.director.mouse.Mouse.move_to")
    @patch("thea.director.mouse.time.sleep")
    def test_click_in_place(self, mock_sleep, mock_move, mock_click):
        m = _make_mouse()
        m.click()
        mock_move.assert_not_called()
        mock_click.assert_called_once_with(1, ENV)

    @patch("thea.director.mouse.xdotool.mouse_click")
    @patch("thea.director.mouse.Mouse.move_to")
    @patch("thea.director.mouse.time.sleep")
    def test_click_custom_button(self, mock_sleep, mock_move, mock_click):
        m = _make_mouse()
        m.click(50, 50, button=2)
        mock_click.assert_called_once_with(2, ENV)

    @patch("thea.director.mouse.xdotool.mouse_click")
    @patch("thea.director.mouse.Mouse.move_to")
    @patch("thea.director.mouse.time.sleep")
    def test_click_with_duration(self, mock_sleep, mock_move, mock_click):
        m = _make_mouse()
        m.click(100, 200, duration=0.3)
        mock_move.assert_called_once_with(100, 200, duration=0.3)


class TestDoubleClick:
    @patch("thea.director.mouse.xdotool.mouse_click")
    @patch("thea.director.mouse.Mouse.move_to")
    @patch("thea.director.mouse.time.sleep")
    def test_double_click(self, mock_sleep, mock_move, mock_click):
        m = _make_mouse()
        m.double_click(100, 200)
        mock_move.assert_called_once_with(100, 200, duration=None)
        assert mock_click.call_count == 2
        mock_click.assert_any_call(1, ENV)

    @patch("thea.director.mouse.xdotool.mouse_click")
    @patch("thea.director.mouse.Mouse.move_to")
    @patch("thea.director.mouse.time.sleep")
    def test_double_click_in_place(self, mock_sleep, mock_move, mock_click):
        m = _make_mouse()
        m.double_click()
        mock_move.assert_not_called()
        assert mock_click.call_count == 2


class TestRightClick:
    @patch("thea.director.mouse.xdotool.mouse_click")
    @patch("thea.director.mouse.Mouse.move_to")
    @patch("thea.director.mouse.time.sleep")
    def test_right_click(self, mock_sleep, mock_move, mock_click):
        m = _make_mouse()
        m.right_click(100, 200)
        mock_click.assert_called_once_with(3, ENV)


class TestDrag:
    @patch("thea.director.mouse.xdotool.mouse_up")
    @patch("thea.director.mouse.xdotool.mouse_down")
    @patch("thea.director.mouse.Mouse.move_to")
    @patch("thea.director.mouse.time.sleep")
    def test_drag(self, mock_sleep, mock_move, mock_down, mock_up):
        m = _make_mouse()
        m.drag(10, 20, 300, 400)
        # Moves to start, presses, moves to end, releases.
        assert mock_move.call_count == 2
        mock_move.assert_any_call(10, 20)
        mock_down.assert_called_once_with(1, ENV)
        mock_up.assert_called_once_with(1, ENV)

    @patch("thea.director.mouse.xdotool.mouse_up")
    @patch("thea.director.mouse.xdotool.mouse_down")
    @patch("thea.director.mouse.Mouse.move_to")
    @patch("thea.director.mouse.time.sleep")
    def test_drag_custom_button(self, mock_sleep, mock_move, mock_down, mock_up):
        m = _make_mouse()
        m.drag(0, 0, 100, 100, button=3)
        mock_down.assert_called_once_with(3, ENV)
        mock_up.assert_called_once_with(3, ENV)


class TestScroll:
    @patch("thea.director.mouse.xdotool.mouse_click")
    @patch("thea.director.mouse.Mouse.move_to")
    @patch("thea.director.mouse.time.sleep")
    def test_scroll_down(self, mock_sleep, mock_move, mock_click):
        m = _make_mouse()
        m.scroll(3)
        # Button 5 = scroll down, 3 clicks.
        assert mock_click.call_count == 3
        for c in mock_click.call_args_list:
            assert c == call(5, ENV)

    @patch("thea.director.mouse.xdotool.mouse_click")
    @patch("thea.director.mouse.Mouse.move_to")
    @patch("thea.director.mouse.time.sleep")
    def test_scroll_up(self, mock_sleep, mock_move, mock_click):
        m = _make_mouse()
        m.scroll(-2)
        assert mock_click.call_count == 2
        for c in mock_click.call_args_list:
            assert c == call(4, ENV)

    @patch("thea.director.mouse.xdotool.mouse_click")
    @patch("thea.director.mouse.Mouse.move_to")
    @patch("thea.director.mouse.time.sleep")
    def test_scroll_at_position(self, mock_sleep, mock_move, mock_click):
        m = _make_mouse()
        m.scroll(1, x=100, y=200)
        mock_move.assert_called_once_with(100, 200)
        mock_click.assert_called_once_with(5, ENV)

    @patch("thea.director.mouse.xdotool.mouse_click")
    @patch("thea.director.mouse.Mouse.move_to")
    @patch("thea.director.mouse.time.sleep")
    def test_scroll_without_position(self, mock_sleep, mock_move, mock_click):
        m = _make_mouse()
        m.scroll(1)
        mock_move.assert_not_called()

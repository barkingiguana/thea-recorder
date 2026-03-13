"""Tests for the Window class and window-finding functions (mocked xdotool)."""

import math
from unittest.mock import patch, call

import pytest

from thea.director.window import Window, find_window, find_window_by_class, tile


ENV = {"DISPLAY": ":99"}


class TestWindow:
    def test_id(self):
        w = Window("12345", ENV)
        assert w.id == "12345"

    @patch("thea.director.window.time.sleep")
    @patch("thea.director.window.xdotool.window_focus")
    @patch("thea.director.window.xdotool.window_activate")
    def test_focus(self, mock_activate, mock_focus, mock_sleep):
        w = Window("42", ENV)
        result = w.focus()
        mock_activate.assert_called_once_with("42", ENV)
        mock_focus.assert_called_once_with("42", ENV)
        assert result is w  # Chainable

    @patch("thea.director.window.xdotool.window_move")
    def test_move(self, mock_move):
        w = Window("42", ENV)
        result = w.move(100, 200)
        mock_move.assert_called_once_with("42", 100, 200, ENV)
        assert result is w

    @patch("thea.director.window.xdotool.window_resize")
    def test_resize(self, mock_resize):
        w = Window("42", ENV)
        result = w.resize(800, 600)
        mock_resize.assert_called_once_with("42", 800, 600, ENV)
        assert result is w

    @patch("thea.director.window.xdotool.window_minimize")
    def test_minimize(self, mock_min):
        w = Window("42", ENV)
        result = w.minimize()
        mock_min.assert_called_once_with("42", ENV)
        assert result is w

    @patch("thea.director.window.xdotool.window_get_geometry", return_value=(10, 20, 800, 600))
    def test_geometry(self, mock_geom):
        w = Window("42", ENV)
        assert w.geometry == (10, 20, 800, 600)
        mock_geom.assert_called_once_with("42", ENV)

    @patch("thea.director.window.xdotool.window_resize")
    @patch("thea.director.window.xdotool.window_move")
    def test_chaining(self, mock_move, mock_resize):
        w = Window("42", ENV)
        w.move(0, 0).resize(1024, 768)
        mock_move.assert_called_once()
        mock_resize.assert_called_once()

    @patch("thea.director.window.time.sleep")
    @patch("thea.director.window.xdotool.window_focus")
    @patch("thea.director.window.xdotool.window_activate")
    def test_focus_retries_on_badmatch(self, mock_activate, mock_focus, mock_sleep):
        mock_activate.side_effect = [
            RuntimeError("X Error: BadMatch (invalid parameter attributes)"),
            RuntimeError("X Error: BadMatch (invalid parameter attributes)"),
            None,
        ]
        w = Window("42", ENV)
        result = w.focus()
        assert result is w
        assert mock_activate.call_count == 3

    @patch("thea.director.window.time.sleep")
    @patch("thea.director.window.xdotool.window_focus")
    @patch("thea.director.window.xdotool.window_activate")
    def test_focus_raises_non_badmatch(self, mock_activate, mock_focus, mock_sleep):
        mock_activate.side_effect = RuntimeError("xdotool failed (exit 1)")
        w = Window("42", ENV)
        with pytest.raises(RuntimeError, match="xdotool failed"):
            w.focus()
        assert mock_activate.call_count == 1

    @patch("thea.director.window.time.sleep")
    @patch("thea.director.window.xdotool.window_focus")
    @patch("thea.director.window.xdotool.window_activate")
    def test_focus_raises_after_max_retries(self, mock_activate, mock_focus, mock_sleep):
        mock_activate.side_effect = RuntimeError("BadMatch")
        w = Window("42", ENV)
        with pytest.raises(RuntimeError, match="BadMatch"):
            w.focus()
        assert mock_activate.call_count == 5


class TestFindWindow:
    @patch("thea.director.window.time.sleep")
    @patch("thea.director.window.time.monotonic")
    @patch("thea.director.window.xdotool.window_search", return_value=["111"])
    def test_finds_immediately(self, mock_search, mock_mono, mock_sleep):
        mock_mono.side_effect = [0.0, 0.1]
        w = find_window("myapp", ENV)
        assert w.id == "111"
        mock_search.assert_called_once_with("myapp", ENV)

    @patch("thea.director.window.time.sleep")
    @patch("thea.director.window.time.monotonic")
    @patch("thea.director.window.xdotool.window_search")
    def test_retries_until_found(self, mock_search, mock_mono, mock_sleep):
        mock_search.side_effect = [[], [], ["222"]]
        mock_mono.side_effect = [0.0, 1.0, 2.0, 3.0]
        w = find_window("myapp", ENV, timeout=10.0)
        assert w.id == "222"
        assert mock_search.call_count == 3

    @patch("thea.director.window.time.sleep")
    @patch("thea.director.window.time.monotonic")
    @patch("thea.director.window.xdotool.window_search", return_value=[])
    def test_timeout_raises(self, mock_search, mock_mono, mock_sleep):
        mock_mono.side_effect = [0.0, 5.0, 11.0]
        with pytest.raises(RuntimeError, match="not found within"):
            find_window("missing", ENV, timeout=10.0)

    @patch("thea.director.window.time.sleep")
    @patch("thea.director.window.time.monotonic")
    @patch("thea.director.window.xdotool.window_search", return_value=["100", "200"])
    def test_returns_first_match(self, mock_search, mock_mono, mock_sleep):
        mock_mono.side_effect = [0.0, 0.1]
        w = find_window("multi", ENV)
        assert w.id == "100"


class TestFindWindowByClass:
    @patch("thea.director.window.time.sleep")
    @patch("thea.director.window.time.monotonic")
    @patch("thea.director.window.xdotool.window_search_class", return_value=["333"])
    def test_finds_by_class(self, mock_search, mock_mono, mock_sleep):
        mock_mono.side_effect = [0.0, 0.1]
        w = find_window_by_class("chromium", ENV)
        assert w.id == "333"
        mock_search.assert_called_once_with("chromium", ENV)

    @patch("thea.director.window.time.sleep")
    @patch("thea.director.window.time.monotonic")
    @patch("thea.director.window.xdotool.window_search_class", return_value=[])
    def test_timeout_raises(self, mock_search, mock_mono, mock_sleep):
        mock_mono.side_effect = [0.0, 11.0]
        with pytest.raises(RuntimeError, match="not found within"):
            find_window_by_class("nope", ENV, timeout=10.0)


class TestTile:
    def _win(self, wid):
        return Window(wid, ENV)

    def test_empty_list(self):
        tile([])  # Should not raise.

    @patch("thea.director.window.xdotool.window_resize")
    @patch("thea.director.window.xdotool.window_move")
    def test_side_by_side_two(self, mock_move, mock_resize):
        w1, w2 = self._win("1"), self._win("2")
        tile([w1, w2], "side-by-side", bounds=(0, 0, 1000, 500))
        mock_move.assert_any_call("1", 0, 0, ENV)
        mock_resize.assert_any_call("1", 500, 500, ENV)
        mock_move.assert_any_call("2", 500, 0, ENV)
        mock_resize.assert_any_call("2", 500, 500, ENV)

    @patch("thea.director.window.xdotool.window_resize")
    @patch("thea.director.window.xdotool.window_move")
    def test_stacked_two(self, mock_move, mock_resize):
        w1, w2 = self._win("1"), self._win("2")
        tile([w1, w2], "stacked", bounds=(0, 0, 800, 600))
        mock_move.assert_any_call("1", 0, 0, ENV)
        mock_resize.assert_any_call("1", 800, 300, ENV)
        mock_move.assert_any_call("2", 0, 300, ENV)
        mock_resize.assert_any_call("2", 800, 300, ENV)

    @patch("thea.director.window.xdotool.window_resize")
    @patch("thea.director.window.xdotool.window_move")
    def test_grid_four(self, mock_move, mock_resize):
        wins = [self._win(str(i)) for i in range(4)]
        tile(wins, "grid", bounds=(0, 0, 1000, 1000))
        # 4 windows: 2x2 grid, each 500x500.
        mock_move.assert_any_call("0", 0, 0, ENV)
        mock_move.assert_any_call("1", 500, 0, ENV)
        mock_move.assert_any_call("2", 0, 500, ENV)
        mock_move.assert_any_call("3", 500, 500, ENV)
        for w in ["0", "1", "2", "3"]:
            mock_resize.assert_any_call(w, 500, 500, ENV)

    @patch("thea.director.window.xdotool.window_resize")
    @patch("thea.director.window.xdotool.window_move")
    def test_default_bounds(self, mock_move, mock_resize):
        w = self._win("1")
        tile([w])
        # Default bounds: 1920x1080. Single window fills it.
        mock_move.assert_called_once_with("1", 0, 0, ENV)
        mock_resize.assert_called_once_with("1", 1920, 1080, ENV)

    def test_unknown_layout_raises(self):
        with pytest.raises(ValueError, match="Unknown layout"):
            tile([self._win("1")], "diagonal")

"""Tests for Director endpoints on the server."""

import json
from unittest.mock import patch, MagicMock, PropertyMock

import pytest

from thea.server import create_app


@pytest.fixture
def app():
    return create_app(output_dir="/tmp/test-recordings", enable_cors=False)


@pytest.fixture
def client(app):
    return app.test_client()


def _mock_director():
    """Create a mock Director with mouse, keyboard, and window methods."""
    d = MagicMock()
    d.mouse = MagicMock()
    d.mouse.position.return_value = (100, 200)
    d.keyboard = MagicMock()
    d.env = {"DISPLAY": ":99"}
    return d


class TestMouseMove:
    @patch("thea.recorder.Recorder.director", new_callable=PropertyMock)
    def test_move(self, mock_director_prop, client):
        d = _mock_director()
        mock_director_prop.return_value = d
        resp = client.post("/director/mouse/move", json={"x": 100, "y": 200})
        assert resp.status_code == 200
        d.mouse.move_to.assert_called_once_with(100, 200, duration=None, target_width=None)

    @patch("thea.recorder.Recorder.director", new_callable=PropertyMock)
    def test_move_with_duration(self, mock_director_prop, client):
        d = _mock_director()
        mock_director_prop.return_value = d
        resp = client.post("/director/mouse/move", json={"x": 50, "y": 50, "duration": 0.3})
        assert resp.status_code == 200
        d.mouse.move_to.assert_called_once_with(50, 50, duration=0.3, target_width=None)

    def test_move_missing_fields(self, client):
        resp = client.post("/director/mouse/move", json={"x": 100})
        assert resp.status_code == 400


class TestMouseClick:
    @patch("thea.recorder.Recorder.director", new_callable=PropertyMock)
    def test_click_at_position(self, mock_director_prop, client):
        d = _mock_director()
        mock_director_prop.return_value = d
        resp = client.post("/director/mouse/click", json={"x": 100, "y": 200})
        assert resp.status_code == 200
        d.mouse.click.assert_called_once_with(100, 200, button=1, duration=None)

    @patch("thea.recorder.Recorder.director", new_callable=PropertyMock)
    def test_click_in_place(self, mock_director_prop, client):
        d = _mock_director()
        mock_director_prop.return_value = d
        resp = client.post("/director/mouse/click", json={})
        assert resp.status_code == 200
        d.mouse.click.assert_called_once_with(None, None, button=1, duration=None)

    @patch("thea.recorder.Recorder.director", new_callable=PropertyMock)
    def test_click_custom_button(self, mock_director_prop, client):
        d = _mock_director()
        mock_director_prop.return_value = d
        resp = client.post("/director/mouse/click", json={"x": 10, "y": 20, "button": 2})
        assert resp.status_code == 200
        d.mouse.click.assert_called_once_with(10, 20, button=2, duration=None)


class TestMouseDoubleClick:
    @patch("thea.recorder.Recorder.director", new_callable=PropertyMock)
    def test_double_click(self, mock_director_prop, client):
        d = _mock_director()
        mock_director_prop.return_value = d
        resp = client.post("/director/mouse/double-click", json={"x": 100, "y": 200})
        assert resp.status_code == 200
        d.mouse.double_click.assert_called_once()


class TestMouseRightClick:
    @patch("thea.recorder.Recorder.director", new_callable=PropertyMock)
    def test_right_click(self, mock_director_prop, client):
        d = _mock_director()
        mock_director_prop.return_value = d
        resp = client.post("/director/mouse/right-click", json={"x": 100, "y": 200})
        assert resp.status_code == 200
        d.mouse.right_click.assert_called_once()


class TestMouseDrag:
    @patch("thea.recorder.Recorder.director", new_callable=PropertyMock)
    def test_drag(self, mock_director_prop, client):
        d = _mock_director()
        mock_director_prop.return_value = d
        resp = client.post("/director/mouse/drag", json={
            "start_x": 10, "start_y": 20, "end_x": 300, "end_y": 400
        })
        assert resp.status_code == 200
        d.mouse.drag.assert_called_once_with(10, 20, 300, 400, button=1, duration=None)

    def test_drag_missing_fields(self, client):
        resp = client.post("/director/mouse/drag", json={"start_x": 10})
        assert resp.status_code == 400


class TestMouseScroll:
    @patch("thea.recorder.Recorder.director", new_callable=PropertyMock)
    def test_scroll(self, mock_director_prop, client):
        d = _mock_director()
        mock_director_prop.return_value = d
        resp = client.post("/director/mouse/scroll", json={"clicks": 3})
        assert resp.status_code == 200
        d.mouse.scroll.assert_called_once_with(3, x=None, y=None)

    def test_scroll_missing_clicks(self, client):
        resp = client.post("/director/mouse/scroll", json={})
        assert resp.status_code == 400


class TestMousePosition:
    @patch("thea.recorder.Recorder.director", new_callable=PropertyMock)
    def test_position(self, mock_director_prop, client):
        d = _mock_director()
        mock_director_prop.return_value = d
        resp = client.get("/director/mouse/position")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data == {"x": 100, "y": 200}


class TestKeyboardType:
    @patch("thea.recorder.Recorder.director", new_callable=PropertyMock)
    def test_type(self, mock_director_prop, client):
        d = _mock_director()
        mock_director_prop.return_value = d
        resp = client.post("/director/keyboard/type", json={"text": "hello"})
        assert resp.status_code == 200
        d.keyboard.type.assert_called_once_with("hello", wpm=None)

    @patch("thea.recorder.Recorder.director", new_callable=PropertyMock)
    def test_type_with_wpm(self, mock_director_prop, client):
        d = _mock_director()
        mock_director_prop.return_value = d
        resp = client.post("/director/keyboard/type", json={"text": "fast", "wpm": 120})
        assert resp.status_code == 200
        d.keyboard.type.assert_called_once_with("fast", wpm=120)

    def test_type_missing_text(self, client):
        resp = client.post("/director/keyboard/type", json={})
        assert resp.status_code == 400


class TestKeyboardPress:
    @patch("thea.recorder.Recorder.director", new_callable=PropertyMock)
    def test_press(self, mock_director_prop, client):
        d = _mock_director()
        mock_director_prop.return_value = d
        resp = client.post("/director/keyboard/press", json={"keys": ["Return"]})
        assert resp.status_code == 200
        d.keyboard.press.assert_called_once_with("Return")

    @patch("thea.recorder.Recorder.director", new_callable=PropertyMock)
    def test_press_multiple(self, mock_director_prop, client):
        d = _mock_director()
        mock_director_prop.return_value = d
        resp = client.post("/director/keyboard/press", json={"keys": ["ctrl+a", "Delete"]})
        assert resp.status_code == 200
        d.keyboard.press.assert_called_once_with("ctrl+a", "Delete")

    def test_press_missing_keys(self, client):
        resp = client.post("/director/keyboard/press", json={})
        assert resp.status_code == 400


class TestKeyboardHoldRelease:
    @patch("thea.recorder.Recorder.director", new_callable=PropertyMock)
    def test_hold(self, mock_director_prop, client):
        d = _mock_director()
        mock_director_prop.return_value = d
        resp = client.post("/director/keyboard/hold", json={"key": "Shift_L"})
        assert resp.status_code == 200
        d.keyboard.hold.assert_called_once_with("Shift_L")

    @patch("thea.recorder.Recorder.director", new_callable=PropertyMock)
    def test_release(self, mock_director_prop, client):
        d = _mock_director()
        mock_director_prop.return_value = d
        resp = client.post("/director/keyboard/release", json={"key": "Shift_L"})
        assert resp.status_code == 200
        d.keyboard.release.assert_called_once_with("Shift_L")

    def test_hold_missing_key(self, client):
        resp = client.post("/director/keyboard/hold", json={})
        assert resp.status_code == 400

    def test_release_missing_key(self, client):
        resp = client.post("/director/keyboard/release", json={})
        assert resp.status_code == 400


class TestWindowFind:
    @patch("thea.recorder.Recorder.director", new_callable=PropertyMock)
    def test_find_by_name(self, mock_director_prop, client):
        d = _mock_director()
        mock_win = MagicMock()
        mock_win.id = "12345"
        d.window.return_value = mock_win
        mock_director_prop.return_value = d
        resp = client.post("/director/window/find", json={"name": "Firefox"})
        assert resp.status_code == 200
        assert resp.get_json()["window_id"] == "12345"
        d.window.assert_called_once_with("Firefox", timeout=10.0)

    @patch("thea.recorder.Recorder.director", new_callable=PropertyMock)
    def test_find_by_class(self, mock_director_prop, client):
        d = _mock_director()
        mock_win = MagicMock()
        mock_win.id = "99999"
        d.window_by_class.return_value = mock_win
        mock_director_prop.return_value = d
        resp = client.post("/director/window/find", json={"class": "chromium"})
        assert resp.status_code == 200
        assert resp.get_json()["window_id"] == "99999"

    @patch("thea.recorder.Recorder.director", new_callable=PropertyMock)
    def test_find_not_found(self, mock_director_prop, client):
        d = _mock_director()
        d.window.side_effect = RuntimeError("Window matching 'nope' not found within 1.0s")
        mock_director_prop.return_value = d
        resp = client.post("/director/window/find", json={"name": "nope", "timeout": 1.0})
        assert resp.status_code == 404

    def test_find_missing_fields(self, client):
        resp = client.post("/director/window/find", json={})
        assert resp.status_code == 400


class TestWindowOperations:
    @patch("thea.director.xdotool.window_focus")
    @patch("thea.director.xdotool.window_activate")
    @patch("thea.recorder.Recorder.director", new_callable=PropertyMock)
    def test_focus(self, mock_director_prop, mock_activate, mock_focus, client):
        d = _mock_director()
        mock_director_prop.return_value = d
        resp = client.post("/director/window/12345/focus")
        assert resp.status_code == 200

    @patch("thea.director.xdotool.window_move")
    @patch("thea.recorder.Recorder.director", new_callable=PropertyMock)
    def test_move(self, mock_director_prop, mock_move, client):
        d = _mock_director()
        mock_director_prop.return_value = d
        resp = client.post("/director/window/12345/move", json={"x": 0, "y": 0})
        assert resp.status_code == 200

    @patch("thea.director.xdotool.window_resize")
    @patch("thea.recorder.Recorder.director", new_callable=PropertyMock)
    def test_resize(self, mock_director_prop, mock_resize, client):
        d = _mock_director()
        mock_director_prop.return_value = d
        resp = client.post("/director/window/12345/resize", json={"width": 800, "height": 600})
        assert resp.status_code == 200

    @patch("thea.director.xdotool.window_minimize")
    @patch("thea.recorder.Recorder.director", new_callable=PropertyMock)
    def test_minimize(self, mock_director_prop, mock_minimize, client):
        d = _mock_director()
        mock_director_prop.return_value = d
        resp = client.post("/director/window/12345/minimize")
        assert resp.status_code == 200

    @patch("thea.director.xdotool.window_get_geometry", return_value=(10, 20, 800, 600))
    @patch("thea.recorder.Recorder.director", new_callable=PropertyMock)
    def test_geometry(self, mock_director_prop, mock_geom, client):
        d = _mock_director()
        mock_director_prop.return_value = d
        resp = client.get("/director/window/12345/geometry")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data == {"x": 10, "y": 20, "width": 800, "height": 600}

    def test_move_missing_fields(self, client):
        resp = client.post("/director/window/12345/move", json={"x": 0})
        assert resp.status_code == 400

    def test_resize_missing_fields(self, client):
        resp = client.post("/director/window/12345/resize", json={"width": 800})
        assert resp.status_code == 400


class TestWindowTile:
    @patch("thea.director.window.tile")
    @patch("thea.recorder.Recorder.director", new_callable=PropertyMock)
    def test_tile(self, mock_director_prop, mock_tile, client):
        d = _mock_director()
        mock_director_prop.return_value = d
        resp = client.post("/director/window/tile", json={
            "window_ids": ["111", "222"], "layout": "side-by-side"
        })
        assert resp.status_code == 200

    def test_tile_missing_ids(self, client):
        resp = client.post("/director/window/tile", json={})
        assert resp.status_code == 400

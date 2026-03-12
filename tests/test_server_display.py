"""Tests for display screenshot, streaming, and panel styling endpoints."""

import json
import os
from unittest.mock import Mock, patch, MagicMock

import pytest

from thea.server import create_app


@pytest.fixture
def app(tmp_path):
    with patch("thea.recorder.subprocess.Popen"), \
         patch("thea.recorder.subprocess.run"), \
         patch("thea.recorder.os.path.exists", return_value=True):
        app = create_app(output_dir=str(tmp_path), display=42)
        app.config["TESTING"] = True
        yield app


@pytest.fixture
def client(app):
    return app.test_client()


# ── Display screenshot ───────────────────────────────────────────────────


class TestDisplayScreenshot:
    def test_screenshot_requires_display(self, client):
        """Screenshot fails when display not started."""
        resp = client.get("/display/screenshot")
        assert resp.status_code in (409, 500)

    @patch("thea.recorder.subprocess.run")
    def test_screenshot_returns_jpeg(self, mock_run, client):
        """Screenshot returns JPEG bytes when display is running."""
        # Start the display first
        with patch("thea.recorder.subprocess.Popen") as mock_popen:
            mock_proc = Mock()
            mock_proc.poll.return_value = None
            mock_popen.return_value = mock_proc
            client.post("/display/start")

        # Mock ffmpeg screenshot
        fake_jpeg = b"\xff\xd8\xff\xe0JFIF_FAKE_JPEG"
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = fake_jpeg
        mock_run.return_value = mock_result

        resp = client.get("/display/screenshot")
        assert resp.status_code == 200
        assert resp.content_type == "image/jpeg"
        assert resp.data == fake_jpeg

    @patch("thea.recorder.subprocess.run")
    def test_screenshot_quality_param(self, mock_run, client):
        """Quality parameter is forwarded."""
        with patch("thea.recorder.subprocess.Popen") as mock_popen:
            mock_proc = Mock()
            mock_proc.poll.return_value = None
            mock_popen.return_value = mock_proc
            client.post("/display/start")

        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = b"JPEG"
        mock_run.return_value = mock_result

        resp = client.get("/display/screenshot?quality=50")
        assert resp.status_code == 200


# ── Display stream ───────────────────────────────────────────────────────


class TestDisplayStream:
    @patch("thea.recorder.subprocess.run")
    def test_stream_content_type(self, mock_run, client):
        """Stream returns multipart MJPEG content type."""
        with patch("thea.recorder.subprocess.Popen") as mock_popen:
            mock_proc = Mock()
            mock_proc.poll.return_value = None
            mock_popen.return_value = mock_proc
            client.post("/display/start")

        # Make screenshot return something then fail (to end the stream)
        fake_jpeg = b"\xff\xd8JPEG"
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = fake_jpeg
        error_result = Mock()
        error_result.returncode = 1
        error_result.stderr = b"err"
        mock_run.side_effect = [mock_result, RuntimeError("stop")]

        resp = client.get("/display/stream?fps=1")
        assert "multipart/x-mixed-replace" in resp.content_type


# ── Display view ─────────────────────────────────────────────────────────


class TestDisplayView:
    def test_view_returns_html(self, client):
        """View endpoint returns HTML page."""
        resp = client.get("/display/view")
        assert resp.status_code == 200
        assert "text/html" in resp.content_type
        html = resp.data.decode("utf-8")
        assert "<html" in html.lower()
        assert "display/stream" in html


# ── Recording screenshot ─────────────────────────────────────────────────


class TestRecordingScreenshot:
    def test_requires_time_param(self, client, tmp_path):
        """Missing 't' parameter returns 400."""
        # Create a dummy recording file
        (tmp_path / "demo.mp4").write_bytes(b"fake video")
        resp = client.get("/recordings/demo/screenshot")
        assert resp.status_code == 400
        assert "t" in resp.get_json()["error"]

    @patch("thea.recorder.Recorder.screenshot_from_video")
    def test_returns_jpeg(self, mock_extract, client, tmp_path):
        """Valid request returns JPEG frame."""
        fake_jpeg = b"\xff\xd8JPEG_FROM_VIDEO"
        mock_extract.return_value = fake_jpeg
        (tmp_path / "demo.mp4").write_bytes(b"fake video")

        resp = client.get("/recordings/demo/screenshot?t=5.0")
        assert resp.status_code == 200
        assert resp.content_type == "image/jpeg"
        assert resp.data == fake_jpeg
        mock_extract.assert_called_once()
        args = mock_extract.call_args
        assert args[0][1] == 5.0  # time_offset

    def test_recording_not_found(self, client):
        """Missing recording returns 404."""
        resp = client.get("/recordings/nonexistent/screenshot?t=1.0")
        assert resp.status_code == 404

    def test_invalid_recording_name(self, client):
        """Path traversal in name returns 400."""
        resp = client.get("/recordings/../etc/passwd/screenshot?t=1.0")
        assert resp.status_code in (400, 404)

    @patch("thea.recorder.Recorder.screenshot_from_video")
    def test_quality_param(self, mock_extract, client, tmp_path):
        """Quality parameter is passed through."""
        mock_extract.return_value = b"JPEG"
        (tmp_path / "demo.mp4").write_bytes(b"fake")

        resp = client.get("/recordings/demo/screenshot?t=0&quality=50")
        assert resp.status_code == 200
        args = mock_extract.call_args
        assert args[1]["quality"] == 50


# ── Panel bg_color and opacity ───────────────────────────────────────────


class TestPanelStyling:
    def test_add_panel_with_bg_color(self, client):
        """Panel can be created with bg_color."""
        resp = client.post("/panels", json={
            "name": "styled",
            "title": "Styled",
            "bg_color": "ff0000",
        })
        assert resp.status_code == 201

    def test_add_panel_with_opacity(self, client):
        """Panel can be created with opacity."""
        resp = client.post("/panels", json={
            "name": "transparent",
            "title": "Transparent",
            "opacity": 0.5,
        })
        assert resp.status_code == 201

    def test_add_panel_with_both(self, client):
        """Panel can be created with both bg_color and opacity."""
        resp = client.post("/panels", json={
            "name": "combo",
            "title": "Combo",
            "bg_color": "1a1a2e",
            "opacity": 0.8,
        })
        assert resp.status_code == 201

    def test_invalid_bg_color(self, client):
        """Invalid bg_color is rejected."""
        resp = client.post("/panels", json={
            "name": "bad",
            "title": "Bad",
            "bg_color": "not-a-hex",
        })
        assert resp.status_code == 400

    def test_invalid_opacity(self, client):
        """Out-of-range opacity is rejected."""
        resp = client.post("/panels", json={
            "name": "bad",
            "title": "Bad",
            "opacity": 1.5,
        })
        assert resp.status_code == 400


# ── Session-scoped display endpoints ────────────────────────────────────


class TestSessionDisplayEndpoints:
    def _create_session(self, client, name):
        with patch("thea.recorder.subprocess.Popen"), \
             patch("thea.recorder.subprocess.run"), \
             patch("thea.recorder.os.path.exists", return_value=True):
            resp = client.post("/sessions", json={"name": name})
            assert resp.status_code == 201
            return resp.get_json()

    def test_session_screenshot_endpoint_exists(self, client):
        self._create_session(client, "test_sess")
        resp = client.get("/sessions/test_sess/display/screenshot")
        # Will fail (display not started) but endpoint should exist (not 404)
        assert resp.status_code != 404

    def test_session_stream_endpoint_exists(self, client):
        self._create_session(client, "test_sess2")
        resp = client.get("/sessions/test_sess2/display/stream")
        assert resp.status_code != 404

    def test_session_view_returns_html(self, client):
        self._create_session(client, "test_sess3")
        resp = client.get("/sessions/test_sess3/display/view")
        assert resp.status_code == 200
        assert "text/html" in resp.content_type

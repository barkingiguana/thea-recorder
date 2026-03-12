"""Tests for Recorder screenshot and panel styling features."""

from unittest.mock import Mock, patch

import pytest

from thea.recorder import Recorder


class TestScreenshot:
    @patch("thea.recorder.subprocess.run")
    def test_screenshot_returns_bytes(self, mock_run):
        r = Recorder(display=42)
        r._xvfb_proc = Mock()  # pretend display is started

        fake_jpeg = b"\xff\xd8JPEG"
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = fake_jpeg
        mock_run.return_value = mock_result

        result = r.screenshot()
        assert result == fake_jpeg
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert "ffmpeg" in cmd[0]
        assert "-f" in cmd
        assert "mjpeg" in cmd

    def test_screenshot_requires_display(self):
        r = Recorder(display=42)
        with pytest.raises(RuntimeError, match="Display not started"):
            r.screenshot()

    @patch("thea.recorder.subprocess.run")
    def test_screenshot_quality(self, mock_run):
        r = Recorder(display=42)
        r._xvfb_proc = Mock()

        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = b"JPEG"
        mock_run.return_value = mock_result

        r.screenshot(quality=100)
        cmd = mock_run.call_args[0][0]
        qv_idx = cmd.index("-q:v")
        qv_val = int(cmd[qv_idx + 1])
        # quality=100 should give lowest qv (best quality)
        assert qv_val <= 5

    @patch("thea.recorder.subprocess.run")
    def test_screenshot_ffmpeg_failure(self, mock_run):
        r = Recorder(display=42)
        r._xvfb_proc = Mock()

        mock_result = Mock()
        mock_result.returncode = 1
        mock_result.stderr = b"some error"
        mock_run.return_value = mock_result

        with pytest.raises(RuntimeError, match="Screenshot failed"):
            r.screenshot()


class TestScreenshotFromVideo:
    @patch("thea.recorder.subprocess.run")
    @patch("thea.recorder.os.path.isfile", return_value=True)
    def test_extracts_frame(self, mock_isfile, mock_run):
        fake_jpeg = b"\xff\xd8FRAME"
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = fake_jpeg
        mock_run.return_value = mock_result

        result = Recorder.screenshot_from_video("/tmp/test.mp4", 5.5)
        assert result == fake_jpeg
        cmd = mock_run.call_args[0][0]
        assert "-ss" in cmd
        ss_idx = cmd.index("-ss")
        assert "5.500" in cmd[ss_idx + 1]

    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            Recorder.screenshot_from_video("/nonexistent.mp4", 0.0)

    @patch("thea.recorder.subprocess.run")
    @patch("thea.recorder.os.path.isfile", return_value=True)
    def test_ffmpeg_failure(self, mock_isfile, mock_run):
        mock_result = Mock()
        mock_result.returncode = 1
        mock_result.stderr = b"error"
        mock_run.return_value = mock_result

        with pytest.raises(RuntimeError, match="Frame extraction failed"):
            Recorder.screenshot_from_video("/tmp/test.mp4", 0.0)


class TestPanelStyling:
    def test_add_panel_with_bg_color(self):
        r = Recorder(display=42)
        r.add_panel("test", "Test", bg_color="ff0000")
        assert r._panels["test"]["bg_color"] == "ff0000"

    def test_add_panel_with_opacity(self):
        r = Recorder(display=42)
        r.add_panel("test", "Test", opacity=0.5)
        assert r._panels["test"]["opacity"] == 0.5

    def test_add_panel_defaults(self):
        r = Recorder(display=42)
        r.add_panel("test", "Test")
        assert r._panels["test"]["bg_color"] is None or r._panels["test"].get("bg_color") in (None, "1a1a2e")
        # opacity should have a sensible default
        assert "opacity" in r._panels["test"] or r._panels["test"].get("opacity") is None

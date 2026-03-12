"""Tests for display CLI commands: screenshot, stream-url, view-url, recording-screenshot."""

import json
from unittest.mock import patch, Mock

import pytest
from click.testing import CliRunner

from thea.cli import main


@pytest.fixture
def runner():
    return CliRunner()


class TestScreenshotCommand:
    @patch("thea.cli.urlopen")
    def test_screenshot_saves_file(self, mock_urlopen, runner, tmp_path):
        mock_resp = Mock()
        mock_resp.read.return_value = b"\xff\xd8JPEG"
        mock_urlopen.return_value = mock_resp

        output = str(tmp_path / "shot.jpg")
        result = runner.invoke(main, ["screenshot", "-o", output])
        assert result.exit_code == 0
        assert (tmp_path / "shot.jpg").exists()
        data = json.loads(result.output)
        assert data["path"] == output
        assert data["size"] == len(b"\xff\xd8JPEG")


class TestRecordingScreenshotCommand:
    @patch("thea.cli.urlopen")
    def test_saves_frame(self, mock_urlopen, runner, tmp_path):
        mock_resp = Mock()
        mock_resp.read.return_value = b"\xff\xd8FRAME"
        mock_urlopen.return_value = mock_resp

        output = str(tmp_path / "frame.jpg")
        result = runner.invoke(main, [
            "recording-screenshot", "--name", "demo",
            "--time", "5.0", "-o", output,
        ])
        assert result.exit_code == 0
        assert (tmp_path / "frame.jpg").exists()


class TestStreamUrlCommand:
    def test_prints_url(self, runner):
        result = runner.invoke(main, ["stream-url"])
        assert result.exit_code == 0
        assert "display/stream" in result.output
        assert "fps=5" in result.output

    def test_custom_fps(self, runner):
        result = runner.invoke(main, ["stream-url", "--fps", "10"])
        assert result.exit_code == 0
        assert "fps=10" in result.output


class TestViewUrlCommand:
    def test_prints_url(self, runner):
        result = runner.invoke(main, ["view-url"])
        assert result.exit_code == 0
        assert "display/view" in result.output


class TestAddPanelStyling:
    @patch("thea.cli.urlopen")
    def test_bg_color_option(self, mock_urlopen, runner):
        mock_resp = Mock()
        mock_resp.status = 201
        mock_resp.headers = {"Content-Type": "application/json"}
        mock_resp.read.return_value = json.dumps({"status": "created"}).encode()
        mock_urlopen.return_value = mock_resp

        result = runner.invoke(main, [
            "add-panel", "--name", "test", "--title", "Test",
            "--bg-color", "ff0000",
        ])
        assert result.exit_code == 0
        # Check the request body included bg_color
        call_args = mock_urlopen.call_args[0][0]
        body = json.loads(call_args.data.decode())
        assert body["bg_color"] == "ff0000"

    @patch("thea.cli.urlopen")
    def test_opacity_option(self, mock_urlopen, runner):
        mock_resp = Mock()
        mock_resp.status = 201
        mock_resp.headers = {"Content-Type": "application/json"}
        mock_resp.read.return_value = json.dumps({"status": "created"}).encode()
        mock_urlopen.return_value = mock_resp

        result = runner.invoke(main, [
            "add-panel", "--name", "test", "--title", "Test",
            "--opacity", "0.5",
        ])
        assert result.exit_code == 0
        call_args = mock_urlopen.call_args[0][0]
        body = json.loads(call_args.data.decode())
        assert body["opacity"] == 0.5

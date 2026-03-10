"""Tests for the CLI client commands.

Uses a real Flask test server on a random port to test the CLI HTTP client.
"""

import json
import os
import threading
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from thea.cli import main


@pytest.fixture
def mock_server(tmp_path):
    """Start a real Flask app on a random port for CLI testing."""
    with patch("thea.recorder.subprocess.Popen"), \
         patch("thea.recorder.subprocess.run"), \
         patch("thea.recorder.os.path.exists", return_value=True):
        from thea.server import create_app
        app = create_app(output_dir=str(tmp_path), display=42)
        app.config["TESTING"] = True

        # Create a test MP4 file
        (tmp_path / "test_video.mp4").write_bytes(b"FAKE_MP4_DATA")

        # Use Flask's test server via WSGI
        from werkzeug.serving import make_server
        server = make_server("127.0.0.1", 0, app)
        port = server.socket.getsockname()[1]
        url = f"http://127.0.0.1:{port}"

        thread = threading.Thread(target=server.serve_forever)
        thread.daemon = True
        thread.start()

        yield url, tmp_path

        server.shutdown()


@pytest.fixture
def runner():
    return CliRunner()


class TestServerFlag:
    def test_default_server(self, runner):
        # Without a server running, should show connection error
        result = runner.invoke(main, ["health"])
        assert result.exit_code != 0
        assert "cannot reach" in result.output or "Error" in result.output or result.exit_code != 0

    def test_custom_server_flag(self, runner, mock_server):
        url, _ = mock_server
        result = runner.invoke(main, ["--server", url, "health"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status"] == "ok"

    def test_env_var(self, runner, mock_server):
        url, _ = mock_server
        result = runner.invoke(main, ["health"], env={"THEA_URL": url})
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status"] == "ok"

    def test_unreachable_server(self, runner):
        result = runner.invoke(main, ["--server", "http://127.0.0.1:1", "health"])
        assert result.exit_code != 0
        assert "cannot reach" in result.stderr if result.stderr else "cannot reach" in result.output


class TestVersion:
    def test_version(self, runner, mock_server):
        url, _ = mock_server
        result = runner.invoke(main, ["--server", url, "version"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "version" in data


class TestDisplay:
    def test_start_display(self, runner, mock_server):
        url, _ = mock_server
        result = runner.invoke(main, ["--server", url, "start-display"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status"] == "started"

    def test_stop_display(self, runner, mock_server):
        url, _ = mock_server
        runner.invoke(main, ["--server", url, "start-display"])
        result = runner.invoke(main, ["--server", url, "stop-display"])
        assert result.exit_code == 0

    def test_start_display_conflict(self, runner, mock_server):
        url, _ = mock_server
        runner.invoke(main, ["--server", url, "start-display"])
        result = runner.invoke(main, ["--server", url, "start-display"])
        assert result.exit_code == 1
        assert "already" in result.output


class TestPanels:
    def test_add_panel(self, runner, mock_server):
        url, _ = mock_server
        result = runner.invoke(main, [
            "--server", url, "add-panel",
            "--name", "status", "--title", "Status", "--width", "120",
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["name"] == "status"

    def test_update_panel(self, runner, mock_server):
        url, _ = mock_server
        runner.invoke(main, ["--server", url, "add-panel", "--name", "log"])
        result = runner.invoke(main, [
            "--server", url, "update-panel",
            "--name", "log", "--text", "hello world",
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["text"] == "hello world"

    def test_remove_panel(self, runner, mock_server):
        url, _ = mock_server
        runner.invoke(main, ["--server", url, "add-panel", "--name", "temp"])
        result = runner.invoke(main, ["--server", url, "remove-panel", "--name", "temp"])
        assert result.exit_code == 0

    def test_update_missing_panel(self, runner, mock_server):
        url, _ = mock_server
        result = runner.invoke(main, [
            "--server", url, "update-panel",
            "--name", "nope", "--text", "fail",
        ])
        assert result.exit_code == 1
        assert "not found" in result.output


class TestRecording:
    def test_start_recording(self, runner, mock_server):
        url, _ = mock_server
        result = runner.invoke(main, [
            "--server", url, "start-recording", "--name", "test_scenario",
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status"] == "recording"

    def test_stop_recording(self, runner, mock_server):
        url, _ = mock_server
        runner.invoke(main, ["--server", url, "start-recording", "--name", "test"])
        result = runner.invoke(main, ["--server", url, "stop-recording"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["path"].endswith(".mp4")

    def test_stop_when_not_recording(self, runner, mock_server):
        url, _ = mock_server
        result = runner.invoke(main, ["--server", url, "stop-recording"])
        assert result.exit_code == 1

    def test_elapsed(self, runner, mock_server):
        url, _ = mock_server
        result = runner.invoke(main, ["--server", url, "elapsed"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "elapsed" in data


class TestFileCommands:
    def test_list_recordings(self, runner, mock_server):
        url, _ = mock_server
        result = runner.invoke(main, ["--server", url, "list-recordings"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert any(r["name"] == "test_video" for r in data)

    def test_download(self, runner, mock_server, tmp_path):
        url, _ = mock_server
        out_file = str(tmp_path / "downloaded.mp4")
        result = runner.invoke(main, [
            "--server", url, "download",
            "--name", "test_video", "--output", out_file,
        ])
        assert result.exit_code == 0
        assert os.path.exists(out_file)
        with open(out_file, "rb") as f:
            assert f.read() == b"FAKE_MP4_DATA"

    def test_download_not_found(self, runner, mock_server, tmp_path):
        url, _ = mock_server
        result = runner.invoke(main, [
            "--server", url, "download",
            "--name", "nope", "--output", str(tmp_path / "out.mp4"),
        ])
        assert result.exit_code == 1
        assert "not found" in result.output


class TestCleanup:
    def test_cleanup(self, runner, mock_server):
        url, _ = mock_server
        result = runner.invoke(main, ["--server", url, "cleanup"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status"] == "cleaned"


class TestOutputFlags:
    def test_quiet_flag(self, runner, mock_server):
        url, _ = mock_server
        result = runner.invoke(main, ["--server", url, "--quiet", "health"])
        assert result.exit_code == 0
        assert result.output == ""

    def test_pretty_flag(self, runner, mock_server):
        url, _ = mock_server
        result = runner.invoke(main, ["--server", url, "--pretty", "health"])
        assert result.exit_code == 0
        # Pretty output has indentation
        assert "  " in result.output
        data = json.loads(result.output)
        assert data["status"] == "ok"

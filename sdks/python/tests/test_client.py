"""Tests for RecorderClient — uses unittest.mock only, no network calls."""

from __future__ import annotations

import http.client
import io
import json
import os
import tempfile
import urllib.error
import urllib.request
from typing import Any
from unittest import mock

import pytest

from thea.client import RecorderClient, RecorderError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_response(body: Any = None, status: int = 200) -> mock.MagicMock:
    """Return an object that behaves like an ``http.client.HTTPResponse``."""
    if body is None:
        raw = b""
    elif isinstance(body, bytes):
        raw = body
    else:
        raw = json.dumps(body).encode("utf-8")

    resp = mock.MagicMock()
    resp.status = status
    resp.read.return_value = raw
    resp.__enter__ = mock.Mock(return_value=resp)
    resp.__exit__ = mock.Mock(return_value=False)
    return resp


def _http_error(
    status: int, body: dict[str, Any] | None = None
) -> urllib.error.HTTPError:
    """Build an ``HTTPError`` with a readable body."""
    raw = json.dumps(body or {}).encode("utf-8")
    err = urllib.error.HTTPError(
        url="http://localhost:8080/test",
        code=status,
        msg=http.client.responses.get(status, "Error"),
        hdrs=mock.MagicMock(),  # type: ignore[arg-type]
        fp=io.BytesIO(raw),
    )
    return err


@pytest.fixture()
def client() -> RecorderClient:
    return RecorderClient("http://localhost:8080")


# ---------------------------------------------------------------------------
# Constructor
# ---------------------------------------------------------------------------


class TestConstructor:
    def test_explicit_url(self) -> None:
        c = RecorderClient("http://host:1234")
        assert c.base_url == "http://host:1234"

    def test_url_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("THEA_URL", "http://env-host:9999")
        c = RecorderClient()
        assert c.base_url == "http://env-host:9999"

    def test_strips_trailing_slash(self) -> None:
        c = RecorderClient("http://host:1234/")
        assert c.base_url == "http://host:1234"

    def test_no_url_defaults_to_localhost(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("THEA_URL", raising=False)
        c = RecorderClient()
        assert c.base_url == "http://localhost:9123"

    def test_custom_timeout(self) -> None:
        c = RecorderClient("http://host:1234", timeout=5.0)
        assert c.timeout == 5.0


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------


class TestDisplay:
    @mock.patch("urllib.request.urlopen")
    def test_start_display(
        self, mock_urlopen: mock.MagicMock, client: RecorderClient
    ) -> None:
        mock_urlopen.return_value = _mock_response({"status": "started"}, 201)
        result = client.start_display()
        assert result == {"status": "started"}

        req = mock_urlopen.call_args[0][0]
        assert req.full_url == "http://localhost:8080/display/start"
        assert req.method == "POST"

    @mock.patch("urllib.request.urlopen")
    def test_stop_display(
        self, mock_urlopen: mock.MagicMock, client: RecorderClient
    ) -> None:
        mock_urlopen.return_value = _mock_response({"status": "stopped"})
        result = client.stop_display()
        assert result == {"status": "stopped"}


# ---------------------------------------------------------------------------
# Panels
# ---------------------------------------------------------------------------


class TestPanels:
    @mock.patch("urllib.request.urlopen")
    def test_add_panel(
        self, mock_urlopen: mock.MagicMock, client: RecorderClient
    ) -> None:
        mock_urlopen.return_value = _mock_response({"name": "code"}, 201)
        result = client.add_panel("code", "Source Code", 80)
        assert result["name"] == "code"

        req = mock_urlopen.call_args[0][0]
        assert req.full_url == "http://localhost:8080/panels"
        assert req.method == "POST"
        body = json.loads(req.data)
        assert body == {"name": "code", "title": "Source Code", "width": 80}

    @mock.patch("urllib.request.urlopen")
    def test_update_panel(
        self, mock_urlopen: mock.MagicMock, client: RecorderClient
    ) -> None:
        mock_urlopen.return_value = _mock_response({})
        client.update_panel("code", "hello world", focus_line=3)

        req = mock_urlopen.call_args[0][0]
        assert req.full_url == "http://localhost:8080/panels/code"
        assert req.method == "PUT"
        body = json.loads(req.data)
        assert body == {"text": "hello world", "focus_line": 3}

    @mock.patch("urllib.request.urlopen")
    def test_update_panel_no_focus(
        self, mock_urlopen: mock.MagicMock, client: RecorderClient
    ) -> None:
        mock_urlopen.return_value = _mock_response({})
        client.update_panel("code", "hello")

        body = json.loads(mock_urlopen.call_args[0][0].data)
        assert "focus_line" not in body

    @mock.patch("urllib.request.urlopen")
    def test_remove_panel(
        self, mock_urlopen: mock.MagicMock, client: RecorderClient
    ) -> None:
        mock_urlopen.return_value = _mock_response({})
        client.remove_panel("code")

        req = mock_urlopen.call_args[0][0]
        assert req.full_url == "http://localhost:8080/panels/code"
        assert req.method == "DELETE"

    @mock.patch("urllib.request.urlopen")
    def test_list_panels(
        self, mock_urlopen: mock.MagicMock, client: RecorderClient
    ) -> None:
        mock_urlopen.return_value = _mock_response({"panels": ["a", "b"]})
        result = client.list_panels()
        assert result == {"panels": ["a", "b"]}


# ---------------------------------------------------------------------------
# Recording
# ---------------------------------------------------------------------------


class TestRecording:
    @mock.patch("urllib.request.urlopen")
    def test_start_recording(
        self, mock_urlopen: mock.MagicMock, client: RecorderClient
    ) -> None:
        mock_urlopen.return_value = _mock_response({"name": "demo"}, 201)
        result = client.start_recording("demo")
        assert result["name"] == "demo"

        body = json.loads(mock_urlopen.call_args[0][0].data)
        assert body == {"name": "demo"}

    @mock.patch("urllib.request.urlopen")
    def test_stop_recording(
        self, mock_urlopen: mock.MagicMock, client: RecorderClient
    ) -> None:
        mock_urlopen.return_value = _mock_response(
            {"path": "/tmp/demo.mp4", "elapsed": 12.5, "name": "demo"}
        )
        result = client.stop_recording()
        assert result["elapsed"] == 12.5
        assert result["name"] == "demo"

    @mock.patch("urllib.request.urlopen")
    def test_recording_elapsed(
        self, mock_urlopen: mock.MagicMock, client: RecorderClient
    ) -> None:
        mock_urlopen.return_value = _mock_response({"elapsed": 7.3})
        result = client.recording_elapsed()
        assert result["elapsed"] == 7.3

    @mock.patch("urllib.request.urlopen")
    def test_recording_status(
        self, mock_urlopen: mock.MagicMock, client: RecorderClient
    ) -> None:
        mock_urlopen.return_value = _mock_response(
            {"recording": True, "name": "demo", "elapsed": 4.1}
        )
        result = client.recording_status()
        assert result["recording"] is True


# ---------------------------------------------------------------------------
# Recordings archive
# ---------------------------------------------------------------------------


class TestRecordingsArchive:
    @mock.patch("urllib.request.urlopen")
    def test_list_recordings(
        self, mock_urlopen: mock.MagicMock, client: RecorderClient
    ) -> None:
        data = [{"name": "a", "path": "/a.mp4", "size": 100, "created": "t"}]
        mock_urlopen.return_value = _mock_response(data)
        result = client.list_recordings()
        assert len(result) == 1
        assert result[0]["name"] == "a"

    @mock.patch("urllib.request.urlopen")
    def test_download_recording(
        self, mock_urlopen: mock.MagicMock, client: RecorderClient
    ) -> None:
        mp4_bytes = b"\x00\x00\x00\x1cftypisom"
        mock_urlopen.return_value = _mock_response(mp4_bytes)

        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            returned = client.download_recording("demo", tmp_path)
            assert returned == tmp_path
            with open(tmp_path, "rb") as fh:
                assert fh.read() == mp4_bytes
        finally:
            os.unlink(tmp_path)

    @mock.patch("urllib.request.urlopen")
    def test_recording_info(
        self, mock_urlopen: mock.MagicMock, client: RecorderClient
    ) -> None:
        info = {"name": "demo", "path": "/demo.mp4", "size": 500, "created": "t"}
        mock_urlopen.return_value = _mock_response(info)
        result = client.recording_info("demo")
        assert result["size"] == 500


# ---------------------------------------------------------------------------
# Health / cleanup
# ---------------------------------------------------------------------------


class TestHealthCleanup:
    @mock.patch("urllib.request.urlopen")
    def test_health(
        self, mock_urlopen: mock.MagicMock, client: RecorderClient
    ) -> None:
        mock_urlopen.return_value = _mock_response(
            {"status": "ok", "recording": False, "display": True, "panels": 0, "uptime": 123}
        )
        result = client.health()
        assert result["status"] == "ok"

    @mock.patch("urllib.request.urlopen")
    def test_cleanup(
        self, mock_urlopen: mock.MagicMock, client: RecorderClient
    ) -> None:
        mock_urlopen.return_value = _mock_response({"cleaned": 3})
        result = client.cleanup()
        assert result["cleaned"] == 3


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrors:
    @mock.patch("urllib.request.urlopen")
    def test_http_404(
        self, mock_urlopen: mock.MagicMock, client: RecorderClient
    ) -> None:
        mock_urlopen.side_effect = _http_error(404, {"error": "not found"})
        with pytest.raises(RecorderError, match="not found") as exc_info:
            client.recording_info("missing")
        assert exc_info.value.status == 404

    @mock.patch("urllib.request.urlopen")
    def test_http_409_conflict(
        self, mock_urlopen: mock.MagicMock, client: RecorderClient
    ) -> None:
        mock_urlopen.side_effect = _http_error(
            409, {"error": "recording already in progress"}
        )
        with pytest.raises(RecorderError, match="already in progress") as exc_info:
            client.start_recording("dup")
        assert exc_info.value.status == 409

    @mock.patch("urllib.request.urlopen")
    def test_connection_refused(
        self, mock_urlopen: mock.MagicMock, client: RecorderClient
    ) -> None:
        mock_urlopen.side_effect = urllib.error.URLError(
            ConnectionRefusedError("Connection refused")
        )
        with pytest.raises(RecorderError, match="Connection failed"):
            client.health()

    @mock.patch("urllib.request.urlopen")
    def test_timeout(
        self, mock_urlopen: mock.MagicMock, client: RecorderClient
    ) -> None:
        mock_urlopen.side_effect = TimeoutError()
        with pytest.raises(RecorderError, match="timed out"):
            client.health()

    def test_recorder_error_has_status(self) -> None:
        err = RecorderError("boom", status=500)
        assert err.status == 500
        assert str(err) == "boom"

    def test_recorder_error_default_status(self) -> None:
        err = RecorderError("boom")
        assert err.status is None


# ---------------------------------------------------------------------------
# wait_until_ready
# ---------------------------------------------------------------------------


class TestWaitUntilReady:
    @mock.patch("urllib.request.urlopen")
    def test_ready_immediately(
        self, mock_urlopen: mock.MagicMock, client: RecorderClient
    ) -> None:
        mock_urlopen.return_value = _mock_response({"status": "ok"})
        result = client.wait_until_ready(timeout=2)
        assert result["status"] == "ok"

    @mock.patch("time.sleep")
    @mock.patch("urllib.request.urlopen")
    def test_ready_after_retries(
        self,
        mock_urlopen: mock.MagicMock,
        mock_sleep: mock.MagicMock,
        client: RecorderClient,
    ) -> None:
        # Fail twice, succeed on third try.
        mock_urlopen.side_effect = [
            urllib.error.URLError("refused"),
            urllib.error.URLError("refused"),
            _mock_response({"status": "ok"}),
        ]
        result = client.wait_until_ready(timeout=30, interval=0.01)
        assert result["status"] == "ok"
        assert mock_sleep.call_count == 2

    @mock.patch("time.monotonic")
    @mock.patch("time.sleep")
    @mock.patch("urllib.request.urlopen")
    def test_timeout_expires(
        self,
        mock_urlopen: mock.MagicMock,
        mock_sleep: mock.MagicMock,
        mock_monotonic: mock.MagicMock,
        client: RecorderClient,
    ) -> None:
        mock_urlopen.side_effect = urllib.error.URLError("refused")
        # Simulate time progression: start=0, then 1, 2, 3 (exceeds timeout=2).
        mock_monotonic.side_effect = [0.0, 1.0, 2.0, 3.0]
        with pytest.raises(RecorderError, match="not ready after"):
            client.wait_until_ready(timeout=2, interval=0.5)


# ---------------------------------------------------------------------------
# Context managers
# ---------------------------------------------------------------------------


class TestRecordingContextManager:
    @mock.patch("urllib.request.urlopen")
    def test_happy_path(
        self, mock_urlopen: mock.MagicMock, client: RecorderClient
    ) -> None:
        mock_urlopen.side_effect = [
            _mock_response({"name": "demo"}, 201),
            _mock_response({"path": "/demo.mp4", "elapsed": 5.0, "name": "demo"}),
        ]
        with client.recording("demo") as info:
            assert info["name"] == "demo"

        assert info["_stop"]["elapsed"] == 5.0

    @mock.patch("urllib.request.urlopen")
    def test_stops_on_exception(
        self, mock_urlopen: mock.MagicMock, client: RecorderClient
    ) -> None:
        mock_urlopen.side_effect = [
            _mock_response({"name": "err"}, 201),
            _mock_response({"path": "/err.mp4", "elapsed": 1.0, "name": "err"}),
        ]
        with pytest.raises(ValueError, match="boom"):
            with client.recording("err") as info:
                raise ValueError("boom")

        # stop_recording must have been called despite exception
        assert mock_urlopen.call_count == 2
        stop_req = mock_urlopen.call_args_list[1][0][0]
        assert stop_req.full_url == "http://localhost:8080/recording/stop"


class TestPanelContextManager:
    @mock.patch("urllib.request.urlopen")
    def test_happy_path(
        self, mock_urlopen: mock.MagicMock, client: RecorderClient
    ) -> None:
        mock_urlopen.side_effect = [
            _mock_response({"name": "code"}, 201),
            _mock_response({}),  # update
            _mock_response({}),  # remove
        ]
        with client.panel("code", "Code", 80) as info:
            assert info["name"] == "code"
            client.update_panel("code", "x = 1")

        # remove_panel must have been called
        assert mock_urlopen.call_count == 3
        remove_req = mock_urlopen.call_args_list[2][0][0]
        assert remove_req.full_url == "http://localhost:8080/panels/code"
        assert remove_req.method == "DELETE"

    @mock.patch("urllib.request.urlopen")
    def test_removes_on_exception(
        self, mock_urlopen: mock.MagicMock, client: RecorderClient
    ) -> None:
        mock_urlopen.side_effect = [
            _mock_response({"name": "p"}, 201),
            _mock_response({}),  # remove
        ]
        with pytest.raises(RuntimeError):
            with client.panel("p", "P", 60):
                raise RuntimeError("oops")

        assert mock_urlopen.call_count == 2
        remove_req = mock_urlopen.call_args_list[1][0][0]
        assert remove_req.method == "DELETE"

"""Tests for the HTTP server (Flask app).

Uses Flask's test client with the Recorder mocked so no Xvfb/ffmpeg needed.
"""

import json
import os
import threading
from unittest.mock import Mock, patch, PropertyMock

import pytest

from thea.server import create_app


@pytest.fixture
def app(tmp_path):
    """Create a test app with mocked subprocess calls."""
    with patch("thea.recorder.subprocess.Popen"), \
         patch("thea.recorder.subprocess.run"), \
         patch("thea.recorder.os.path.exists", return_value=True), \
         patch("thea.recorder.Recorder._start_window_manager"):
        app = create_app(output_dir=str(tmp_path), display=42)
        app.config["TESTING"] = True
        yield app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def app_cors(tmp_path):
    with patch("thea.recorder.subprocess.Popen"), \
         patch("thea.recorder.subprocess.run"), \
         patch("thea.recorder.os.path.exists", return_value=True), \
         patch("thea.recorder.Recorder._start_window_manager"):
        app = create_app(output_dir=str(tmp_path), display=42, enable_cors=True)
        app.config["TESTING"] = True
        yield app


@pytest.fixture
def cors_client(app_cors):
    return app_cors.test_client()


# ── Health ────────────────────────────────────────────────────────────────

class TestHealth:
    def test_health_ok(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "ok"
        assert data["display"] == ":42"
        assert isinstance(data["uptime"], float)
        assert data["recording"] is False
        assert data["panels"] == []

    def test_health_shows_panels(self, client):
        client.post("/panels", json={"name": "status", "title": "Status"})
        resp = client.get("/health")
        assert "status" in resp.get_json()["panels"]


# ── Display ───────────────────────────────────────────────────────────────

class TestDisplay:
    def test_start_display(self, client):
        resp = client.post("/display/start")
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["status"] == "started"
        assert data["display"] == ":42"

    def test_start_display_conflict(self, client):
        client.post("/display/start")
        resp = client.post("/display/start")
        assert resp.status_code == 409
        assert "already started" in resp.get_json()["error"]

    def test_stop_display(self, client):
        client.post("/display/start")
        resp = client.post("/display/stop")
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "stopped"

    def test_stop_display_when_not_started(self, client):
        resp = client.post("/display/stop")
        assert resp.status_code == 200


# ── Panels ────────────────────────────────────────────────────────────────

class TestPanels:
    def test_create_panel(self, client):
        resp = client.post("/panels", json={"name": "status", "title": "Status", "width": 120})
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["name"] == "status"
        assert data["title"] == "Status"
        assert data["width"] == 120

    def test_create_panel_minimal(self, client):
        resp = client.post("/panels", json={"name": "log"})
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["title"] == ""
        assert data["width"] is None

    def test_create_panel_missing_name(self, client):
        resp = client.post("/panels", json={"title": "Oops"})
        assert resp.status_code == 400
        assert "name" in resp.get_json()["error"]

    def test_create_panel_empty_name(self, client):
        resp = client.post("/panels", json={"name": ""})
        assert resp.status_code == 400

    def test_create_panel_negative_width_treated_as_auto(self, client):
        resp = client.post("/panels", json={"name": "neg", "width": -5})
        assert resp.status_code == 201
        assert resp.get_json()["width"] is None

    def test_create_panel_width_zero_treated_as_auto(self, client):
        resp = client.post("/panels", json={"name": "zero", "width": 0})
        assert resp.status_code == 201
        assert resp.get_json()["width"] is None

    def test_create_panel_width_string(self, client):
        resp = client.post("/panels", json={"name": "bad", "width": "wide"})
        assert resp.status_code == 400

    def test_list_panels(self, client):
        client.post("/panels", json={"name": "a", "title": "A"})
        client.post("/panels", json={"name": "b", "title": "B", "width": 200})
        resp = client.get("/panels")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) == 2
        assert data[0]["name"] == "a"
        assert data[1]["width"] == 200

    def test_list_panels_empty(self, client):
        resp = client.get("/panels")
        assert resp.get_json() == []

    def test_update_panel(self, client):
        client.post("/panels", json={"name": "log"})
        resp = client.put("/panels/log", json={"text": "hello world", "focus_line": 3})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["name"] == "log"
        assert data["text"] == "hello world"

    def test_update_panel_not_found(self, client):
        resp = client.put("/panels/missing", json={"text": "hello"})
        assert resp.status_code == 404
        assert "not found" in resp.get_json()["error"]

    def test_update_panel_empty_text(self, client):
        client.post("/panels", json={"name": "log"})
        resp = client.put("/panels/log", json={})
        assert resp.status_code == 200
        assert resp.get_json()["text"] == ""

    def test_delete_panel(self, client):
        client.post("/panels", json={"name": "temp"})
        resp = client.delete("/panels/temp")
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "removed"

    def test_delete_panel_not_found(self, client):
        resp = client.delete("/panels/missing")
        assert resp.status_code == 404

    def test_re_create_panel(self, client):
        client.post("/panels", json={"name": "x", "title": "Old"})
        client.post("/panels", json={"name": "x", "title": "New"})
        resp = client.get("/panels")
        panels = resp.get_json()
        assert len(panels) == 1
        assert panels[0]["title"] == "New"


# ── Recording ────────────────────────────────────────────────────────────

class TestRecording:
    def test_start_recording(self, client):
        resp = client.post("/recording/start", json={"name": "my_scenario"})
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["status"] == "recording"
        assert data["name"] == "my_scenario"

    def test_start_recording_missing_name(self, client):
        resp = client.post("/recording/start", json={})
        assert resp.status_code == 400
        assert "name" in resp.get_json()["error"]

    def test_start_recording_empty_name(self, client):
        resp = client.post("/recording/start", json={"name": ""})
        assert resp.status_code == 400

    def test_start_recording_conflict(self, client):
        client.post("/recording/start", json={"name": "first"})
        resp = client.post("/recording/start", json={"name": "second"})
        assert resp.status_code == 409
        assert "already recording" in resp.get_json()["error"]

    def test_stop_recording(self, client):
        client.post("/recording/start", json={"name": "test"})
        resp = client.post("/recording/stop")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["path"].endswith(".mp4")
        assert "elapsed" in data
        assert data["name"] == "test"

    def test_stop_recording_when_not_recording(self, client):
        resp = client.post("/recording/stop")
        assert resp.status_code == 409
        assert "not recording" in resp.get_json()["error"]

    def test_recording_elapsed(self, client):
        resp = client.get("/recording/elapsed")
        assert resp.status_code == 200
        assert resp.get_json()["elapsed"] == 0.0

    def test_recording_elapsed_while_recording(self, client):
        client.post("/recording/start", json={"name": "test"})
        resp = client.get("/recording/elapsed")
        assert resp.get_json()["elapsed"] >= 0.0
        # Verify recording is actually tracked (recording_start is set)
        assert client.application._recorder._recording_start is not None

    def test_recording_status_not_recording(self, client):
        resp = client.get("/recording/status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["recording"] is False
        assert data["name"] is None

    def test_recording_status_while_recording(self, client):
        client.post("/recording/start", json={"name": "active"})
        resp = client.get("/recording/status")
        data = resp.get_json()
        assert data["recording"] is True
        assert data["name"] == "active"
        assert data["elapsed"] >= 0.0

    def test_full_lifecycle(self, client):
        client.post("/recording/start", json={"name": "lifecycle"})
        resp = client.post("/recording/stop")
        assert resp.status_code == 200

        # Can start a new recording
        resp = client.post("/recording/start", json={"name": "second"})
        assert resp.status_code == 201


# ── File Access ──────────────────────────────────────────────────────────

class TestFileAccess:
    @pytest.fixture(autouse=True)
    def _create_test_files(self, app, tmp_path):
        """Create some fake MP4 files for download tests."""
        self.output_dir = tmp_path
        # Create a fake MP4 file
        mp4 = tmp_path / "test_scenario.mp4"
        mp4.write_bytes(b"\x00" * 1024 + b"VIDEO_DATA" + b"\x00" * 1024)
        self.test_file = mp4

    def test_list_recordings(self, client):
        resp = client.get("/recordings")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) == 1
        assert data[0]["name"] == "test_scenario"
        assert data[0]["size"] > 0
        assert "created" in data[0]

    def test_list_recordings_empty(self, client, tmp_path):
        # Remove the test file
        os.unlink(self.test_file)
        resp = client.get("/recordings")
        assert resp.get_json() == []

    def test_download_recording(self, client):
        resp = client.get("/recordings/test_scenario")
        assert resp.status_code == 200
        assert resp.content_type == "video/mp4"
        assert len(resp.data) == 2058  # 1024 + 10 + 1024

    def test_download_recording_not_found(self, client):
        resp = client.get("/recordings/nonexistent")
        assert resp.status_code == 404
        assert "not found" in resp.get_json()["error"]

    def test_download_with_range_header(self, client):
        resp = client.get("/recordings/test_scenario", headers={"Range": "bytes=1024-1033"})
        assert resp.status_code == 206
        assert resp.data == b"VIDEO_DATA"
        assert "Content-Range" in resp.headers
        assert resp.headers["Content-Range"] == "bytes 1024-1033/2058"

    def test_download_range_from_start(self, client):
        resp = client.get("/recordings/test_scenario", headers={"Range": "bytes=0-9"})
        assert resp.status_code == 206
        assert len(resp.data) == 10

    def test_download_range_open_end(self, client):
        resp = client.get("/recordings/test_scenario", headers={"Range": "bytes=2048-"})
        assert resp.status_code == 206
        assert len(resp.data) == 10  # 2058 - 2048

    def test_download_range_invalid(self, client):
        resp = client.get("/recordings/test_scenario", headers={"Range": "bytes=9999-"})
        assert resp.status_code == 416

    def test_download_range_malformed(self, client):
        resp = client.get("/recordings/test_scenario", headers={"Range": "invalid"})
        assert resp.status_code == 416

    def test_recording_info(self, client):
        resp = client.get("/recordings/test_scenario/info")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["name"] == "test_scenario"
        assert data["size"] == 2058
        assert "created" in data
        assert "path" in data

    def test_recording_info_not_found(self, client):
        resp = client.get("/recordings/missing/info")
        assert resp.status_code == 404

    def test_path_traversal_rejected(self, client):
        resp = client.get("/recordings/../../../etc/passwd")
        # Flask may normalise the path, but our check should catch it
        assert resp.status_code in (400, 404)

    def test_path_traversal_double_dot(self, client):
        resp = client.get("/recordings/..%2F..%2Fetc%2Fpasswd")
        assert resp.status_code in (400, 404)

    def test_info_path_traversal(self, client):
        resp = client.get("/recordings/../evil/info")
        assert resp.status_code in (400, 404)


# ── Cleanup ──────────────────────────────────────────────────────────────

class TestCleanup:
    def test_cleanup(self, client):
        client.post("/panels", json={"name": "temp"})
        resp = client.post("/cleanup")
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "cleaned"

        # Panels should be gone
        resp = client.get("/panels")
        assert resp.get_json() == []

    def test_cleanup_idempotent(self, client):
        client.post("/cleanup")
        resp = client.post("/cleanup")
        assert resp.status_code == 200

    def test_cleanup_while_recording(self, client):
        client.post("/recording/start", json={"name": "active"})
        resp = client.post("/cleanup")
        assert resp.status_code == 200

        # Should no longer be recording
        resp = client.get("/recording/status")
        assert resp.get_json()["recording"] is False


# ── CORS ─────────────────────────────────────────────────────────────────

class TestCORS:
    def test_cors_headers_present(self, cors_client):
        resp = cors_client.get("/health")
        assert resp.headers.get("Access-Control-Allow-Origin") == "*"

    def test_cors_preflight(self, cors_client):
        resp = cors_client.options("/panels")
        assert resp.status_code == 204
        assert "Access-Control-Allow-Methods" in resp.headers

    def test_no_cors_by_default(self, client):
        resp = client.get("/health")
        assert "Access-Control-Allow-Origin" not in resp.headers


# ── Concurrent Access ────────────────────────────────────────────────────

class TestConcurrency:
    def test_concurrent_panel_updates(self, app):
        client = app.test_client()
        client.post("/panels", json={"name": "shared"})

        errors = []

        def update(text):
            try:
                resp = client.put("/panels/shared", json={"text": text})
                if resp.status_code != 200:
                    errors.append(f"Status {resp.status_code} for {text}")
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=update, args=(f"update-{i}",)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Errors during concurrent updates: {errors}"


# ── Malformed Requests ───────────────────────────────────────────────────

class TestMalformedRequests:
    def test_panels_no_json_body(self, client):
        resp = client.post("/panels", data="not json", content_type="text/plain")
        assert resp.status_code == 400

    def test_recording_no_json_body(self, client):
        resp = client.post("/recording/start", data="", content_type="text/plain")
        assert resp.status_code == 400

    def test_panels_wrong_method(self, client):
        resp = client.patch("/panels")
        assert resp.status_code == 405

    def test_update_panel_no_body(self, client):
        client.post("/panels", json={"name": "x"})
        resp = client.put("/panels/x")
        assert resp.status_code == 200  # Empty text is fine

    def test_nonexistent_route(self, client):
        resp = client.get("/nonexistent")
        assert resp.status_code == 404


class TestLayoutValidation:
    def test_validate_layout_no_panels(self, client):
        resp = client.get("/validate-layout")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["valid"] is True
        assert data["warnings"] == []

    def test_validate_layout_with_panels(self, client):
        client.post("/panels", json={"name": "status", "width": 120})
        client.post("/panels", json={"name": "log"})
        resp = client.get("/validate-layout")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["valid"] is True

    def test_validate_layout_overallocated_bar(self, client):
        client.post("/panels", json={"name": "huge", "height": 500})
        resp = client.get("/validate-layout")
        data = resp.get_json()
        assert data["valid"] is False
        assert any("allocated" in w for w in data["warnings"])

    def test_add_panel_with_height(self, client):
        resp = client.post("/panels", json={"name": "short", "height": 100})
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["height"] == 100

    def test_add_panel_invalid_height_type(self, client):
        resp = client.post("/panels", json={"name": "bad", "height": "tall"})
        assert resp.status_code == 400

    def test_add_panel_negative_height(self, client):
        resp = client.post("/panels", json={"name": "bad", "height": -10})
        assert resp.status_code == 400

    def test_add_panel_returns_warnings(self, client):
        resp = client.post("/panels", json={"name": "huge", "height": 500})
        data = resp.get_json()
        assert "warnings" in data
        assert any("allocated" in w for w in data["warnings"])

    def test_start_recording_returns_warnings(self, client):
        client.post("/panels", json={"name": "huge", "height": 500})
        resp = client.post("/recording/start", json={"name": "test"})
        data = resp.get_json()
        assert "warnings" in data

    def test_testcard_returns_svg(self, client):
        resp = client.get("/testcard")
        assert resp.status_code == 200
        assert resp.content_type == "image/svg+xml; charset=utf-8"
        assert b"<svg" in resp.data

    def test_testcard_with_panels(self, client):
        client.post("/panels", json={"name": "status", "width": 120})
        resp = client.get("/testcard")
        assert b"status" in resp.data

    def test_session_validate_layout(self, client):
        client.post("/sessions", json={"name": "test_sess"})
        resp = client.get("/sessions/test_sess/validate-layout")
        assert resp.status_code == 200

    def test_session_testcard(self, client):
        client.post("/sessions", json={"name": "test_sess"})
        resp = client.get("/sessions/test_sess/testcard")
        assert resp.status_code == 200
        assert b"<svg" in resp.data

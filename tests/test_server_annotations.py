"""Tests for the recording annotation endpoints."""

from unittest.mock import patch, Mock

import pytest

from thea.server import create_app


@pytest.fixture
def app(tmp_path):
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


def _start_recording(client, name="demo"):
    with patch("thea.recorder.subprocess.Popen") as mock_popen, \
         patch("thea.recorder.Recorder._start_window_manager"):
        mock_proc = Mock()
        mock_proc.poll.return_value = None
        mock_proc.returncode = 0
        mock_proc.stderr.read.return_value = b""
        mock_popen.return_value = mock_proc
        client.post("/display/start")
        resp = client.post("/recording/start", json={"name": name})
        assert resp.status_code == 201


class TestAnnotationsEndpoint:
    def test_add_annotation(self, client):
        _start_recording(client)
        resp = client.post("/recording/annotations", json={
            "label": "login_started",
        })
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["label"] == "login_started"
        assert "time" in data
        assert data["time"] >= 0

    def test_add_annotation_with_time(self, client):
        _start_recording(client)
        resp = client.post("/recording/annotations", json={
            "label": "step_1",
            "time": 5.5,
        })
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["label"] == "step_1"
        assert data["time"] == 5.5

    def test_add_annotation_with_details(self, client):
        _start_recording(client)
        resp = client.post("/recording/annotations", json={
            "label": "assertion_failed",
            "details": "Expected 200 got 404",
        })
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["details"] == "Expected 200 got 404"

    def test_add_annotation_requires_label(self, client):
        _start_recording(client)
        resp = client.post("/recording/annotations", json={})
        assert resp.status_code == 400
        assert "label" in resp.get_json()["error"]

    def test_add_annotation_empty_label(self, client):
        _start_recording(client)
        resp = client.post("/recording/annotations", json={"label": "  "})
        assert resp.status_code == 400

    def test_add_annotation_invalid_time(self, client):
        _start_recording(client)
        resp = client.post("/recording/annotations", json={
            "label": "test",
            "time": -1,
        })
        assert resp.status_code == 400

    def test_add_annotation_not_recording(self, client):
        resp = client.post("/recording/annotations", json={
            "label": "test",
        })
        assert resp.status_code == 409

    def test_list_annotations(self, client):
        _start_recording(client)
        client.post("/recording/annotations", json={"label": "a"})
        client.post("/recording/annotations", json={"label": "b", "time": 3.0})

        resp = client.get("/recording/annotations")
        assert resp.status_code == 200
        annotations = resp.get_json()
        assert len(annotations) == 2
        assert annotations[0]["label"] == "a"
        assert annotations[1]["label"] == "b"
        assert annotations[1]["time"] == 3.0

    def test_list_annotations_not_recording(self, client):
        resp = client.get("/recording/annotations")
        assert resp.status_code == 409

    def test_annotations_in_stop_result(self, client):
        _start_recording(client)
        client.post("/recording/annotations", json={"label": "step_1", "time": 1.0})
        client.post("/recording/annotations", json={"label": "step_2", "time": 2.0})

        with patch("thea.recorder.Recorder.stop_recording", return_value="/tmp/demo.mp4"), \
             patch("thea.recorder.Recorder.recording_elapsed", new_callable=lambda: property(lambda self: 5.0)):
            resp = client.post("/recording/stop")

        assert resp.status_code == 200
        data = resp.get_json()
        assert "annotations" in data
        assert len(data["annotations"]) == 2
        assert data["annotations"][0]["label"] == "step_1"

    def test_annotations_cleared_after_stop(self, client):
        _start_recording(client)
        client.post("/recording/annotations", json={"label": "first_run"})

        # Stop the recording
        resp = client.post("/recording/stop")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data.get("annotations", [])) == 1

        # Start a new recording — annotations should be empty
        _start_recording(client, name="second")
        resp = client.get("/recording/annotations")
        assert resp.status_code == 200
        assert resp.get_json() == []

    def test_annotation_emits_event(self, client):
        _start_recording(client)
        client.post("/recording/annotations", json={"label": "marker"})

        resp = client.get("/events")
        events = resp.get_json()
        annotated = [e for e in events if e["event"] == "recording.annotated"]
        assert len(annotated) == 1
        assert annotated[0]["details"]["label"] == "marker"

    def test_annotations_without_recording_omitted_from_stop(self, client):
        """Stop result should not include 'annotations' key when there are none."""
        _start_recording(client)

        with patch("thea.recorder.Recorder.stop_recording", return_value="/tmp/demo.mp4"), \
             patch("thea.recorder.Recorder.recording_elapsed", new_callable=lambda: property(lambda self: 5.0)):
            resp = client.post("/recording/stop")

        data = resp.get_json()
        assert "annotations" not in data


class TestSessionAnnotations:
    def _create_session(self, client, name):
        with patch("thea.recorder.subprocess.Popen"), \
             patch("thea.recorder.subprocess.run"), \
             patch("thea.recorder.os.path.exists", return_value=True):
            return client.post("/sessions", json={"name": name})

    def _start_session_recording(self, client, session_name, rec_name="demo"):
        with patch("thea.recorder.subprocess.Popen") as mock_popen, \
             patch("thea.recorder.Recorder._start_window_manager"):
            mock_proc = Mock()
            mock_proc.poll.return_value = None
            mock_popen.return_value = mock_proc
            client.post(f"/sessions/{session_name}/display/start")
            resp = client.post(f"/sessions/{session_name}/recording/start", json={"name": rec_name})
            assert resp.status_code == 201

    def test_session_annotations(self, client):
        self._create_session(client, "alice")
        self._start_session_recording(client, "alice")

        resp = client.post("/sessions/alice/recording/annotations", json={
            "label": "login",
        })
        assert resp.status_code == 201

        resp = client.get("/sessions/alice/recording/annotations")
        assert resp.status_code == 200
        assert len(resp.get_json()) == 1

    def test_session_annotations_isolated(self, client):
        self._create_session(client, "alice")
        self._create_session(client, "bob")
        self._start_session_recording(client, "alice")
        self._start_session_recording(client, "bob")

        client.post("/sessions/alice/recording/annotations", json={"label": "alice_marker"})
        client.post("/sessions/bob/recording/annotations", json={"label": "bob_marker"})

        alice_resp = client.get("/sessions/alice/recording/annotations")
        bob_resp = client.get("/sessions/bob/recording/annotations")

        alice_annotations = alice_resp.get_json()
        bob_annotations = bob_resp.get_json()

        assert len(alice_annotations) == 1
        assert alice_annotations[0]["label"] == "alice_marker"
        assert len(bob_annotations) == 1
        assert bob_annotations[0]["label"] == "bob_marker"

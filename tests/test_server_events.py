"""Tests for the event log and dashboard endpoints."""

import json
from unittest.mock import patch, Mock

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


class TestEventsEndpoint:
    def test_events_initially_empty(self, client):
        resp = client.get("/events")
        assert resp.status_code == 200
        assert resp.get_json() == []

    def test_events_after_display_start(self, client):
        with patch("thea.recorder.subprocess.Popen") as mock_popen:
            mock_proc = Mock()
            mock_proc.poll.return_value = None
            mock_popen.return_value = mock_proc
            client.post("/display/start")

        resp = client.get("/events")
        events = resp.get_json()
        assert len(events) >= 1
        assert events[0]["event"] == "display.started"
        assert "time" in events[0]
        assert "elapsed" in events[0]
        assert events[0]["details"]["display"] == ":42"

    def test_events_after_panel_create(self, client):
        client.post("/panels", json={"name": "test", "title": "Test"})

        resp = client.get("/events")
        events = resp.get_json()
        panel_events = [e for e in events if e["event"] == "panel.created"]
        assert len(panel_events) == 1
        assert panel_events[0]["details"]["name"] == "test"

    def test_events_after_panel_update(self, client):
        client.post("/panels", json={"name": "test", "title": "Test"})
        client.put("/panels/test", json={"text": "hello"})

        resp = client.get("/events")
        events = resp.get_json()
        update_events = [e for e in events if e["event"] == "panel.updated"]
        assert len(update_events) == 1

    def test_events_after_panel_delete(self, client):
        client.post("/panels", json={"name": "test", "title": "Test"})
        client.delete("/panels/test")

        resp = client.get("/events")
        events = resp.get_json()
        remove_events = [e for e in events if e["event"] == "panel.removed"]
        assert len(remove_events) == 1

    def test_events_after_recording_start_stop(self, client):
        with patch("thea.recorder.subprocess.Popen") as mock_popen:
            mock_proc = Mock()
            mock_proc.poll.return_value = None
            mock_popen.return_value = mock_proc
            client.post("/display/start")
            client.post("/recording/start", json={"name": "demo"})

        resp = client.get("/events")
        events = resp.get_json()
        rec_events = [e for e in events if e["event"] == "recording.started"]
        assert len(rec_events) == 1
        assert rec_events[0]["details"]["name"] == "demo"

    def test_events_since_filter(self, client):
        client.post("/panels", json={"name": "a", "title": "A"})
        client.post("/panels", json={"name": "b", "title": "B"})

        resp = client.get("/events")
        events = resp.get_json()
        first_elapsed = events[0]["elapsed"]

        resp2 = client.get(f"/events?since={first_elapsed}")
        filtered = resp2.get_json()
        assert len(filtered) < len(events)

    def test_cleanup_event(self, client):
        client.post("/cleanup")

        resp = client.get("/events")
        events = resp.get_json()
        cleanup_events = [e for e in events if e["event"] == "cleanup"]
        assert len(cleanup_events) == 1


class TestSessionEvents:
    def _create_session(self, client, name):
        with patch("thea.recorder.subprocess.Popen"), \
             patch("thea.recorder.subprocess.run"), \
             patch("thea.recorder.os.path.exists", return_value=True):
            return client.post("/sessions", json={"name": name})

    def test_session_events_endpoint(self, client):
        self._create_session(client, "alice")
        resp = client.get("/sessions/alice/events")
        assert resp.status_code == 200
        events = resp.get_json()
        # Session creation event
        assert any(e["event"] == "session.created" for e in events)

    def test_session_events_isolated(self, client):
        self._create_session(client, "alice")
        self._create_session(client, "bob")

        # Default events shouldn't have session.created (those go to their own sessions)
        resp = client.get("/events")
        default_events = resp.get_json()
        session_creates_in_default = [e for e in default_events if e["event"] == "session.created"]
        assert len(session_creates_in_default) == 0

    def test_session_not_found(self, client):
        resp = client.get("/sessions/nonexistent/events")
        assert resp.status_code == 404


class TestDashboard:
    def test_dashboard_returns_html(self, client):
        resp = client.get("/dashboard")
        assert resp.status_code == 200
        assert "text/html" in resp.content_type
        html = resp.data.decode("utf-8")
        assert "Thea Dashboard" in html
        assert "/sessions" in html
        assert "/events" in html

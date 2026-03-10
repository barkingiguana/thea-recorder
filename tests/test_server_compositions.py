"""Unit tests for the /compositions server endpoints."""

from unittest.mock import patch

import pytest

from thea.server import create_app


@pytest.fixture
def app(tmp_path):
    return create_app(output_dir=str(tmp_path), display=99)


@pytest.fixture
def client(app):
    app.config["TESTING"] = True
    return app.test_client()


class TestCompositionsCreate:
    def test_missing_name(self, client):
        resp = client.post("/compositions", json={"recordings": ["a"]})
        assert resp.status_code == 400
        assert "name" in resp.get_json()["error"]

    def test_missing_recordings(self, client):
        resp = client.post("/compositions", json={"name": "test"})
        assert resp.status_code == 400
        assert "recordings" in resp.get_json()["error"]

    def test_empty_recordings(self, client):
        resp = client.post("/compositions", json={"name": "test", "recordings": []})
        assert resp.status_code == 400

    def test_invalid_layout(self, client):
        resp = client.post("/compositions", json={
            "name": "test", "recordings": ["a"], "layout": "diagonal",
        })
        assert resp.status_code == 400
        assert "layout" in resp.get_json()["error"]

    @patch("thea.composer.CompositionManager.create")
    def test_success(self, mock_create, client):
        from thea.composer import CompositionResult
        mock_create.return_value = CompositionResult(name="demo", status="rendering")

        resp = client.post("/compositions", json={
            "name": "demo",
            "recordings": ["a", "b"],
            "layout": "row",
            "labels": True,
            "highlights": [
                {"recording": "a", "time": 1.0, "duration": 2.0},
            ],
        })
        assert resp.status_code == 202
        data = resp.get_json()
        assert data["name"] == "demo"
        assert data["status"] == "rendering"

        # Verify the spec passed to create
        call_spec = mock_create.call_args[0][0]
        assert call_spec.recordings == ["a", "b"]
        assert len(call_spec.highlights) == 1

    @patch("thea.composer.CompositionManager.create")
    def test_duplicate_returns_409(self, mock_create, client):
        mock_create.side_effect = ValueError("already exists")
        resp = client.post("/compositions", json={
            "name": "dup", "recordings": ["a"],
        })
        assert resp.status_code == 409

    def test_invalid_highlight_missing_time(self, client):
        resp = client.post("/compositions", json={
            "name": "test",
            "recordings": ["a"],
            "highlights": [{"recording": "a"}],
        })
        assert resp.status_code == 400
        assert "highlight" in resp.get_json()["error"]


class TestCompositionsList:
    def test_empty_list(self, client):
        resp = client.get("/compositions")
        assert resp.status_code == 200
        assert resp.get_json() == []


class TestCompositionsGet:
    def test_not_found(self, client):
        resp = client.get("/compositions/nope")
        assert resp.status_code == 404

    @patch("thea.composer.CompositionManager.get")
    def test_found(self, mock_get, client):
        from thea.composer import CompositionResult, CompositionSpec
        spec = CompositionSpec(name="demo", recordings=["a", "b"])
        result = CompositionResult(name="demo", status="complete", output_path="/tmp/demo.mp4")
        mock_get.return_value = (spec, result)

        resp = client.get("/compositions/demo")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["name"] == "demo"
        assert data["status"] == "complete"
        assert data["recordings"] == ["a", "b"]


class TestCompositionsDelete:
    def test_not_found(self, client):
        resp = client.delete("/compositions/nope")
        assert resp.status_code == 404

    @patch("thea.composer.CompositionManager.delete")
    def test_success(self, mock_delete, client):
        mock_delete.return_value = True
        resp = client.delete("/compositions/demo")
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "removed"


class TestCompositionsHighlights:
    def test_add_to_nonexistent(self, client):
        resp = client.post("/compositions/nope/highlights", json={
            "recording": "a", "time": 1.0,
        })
        assert resp.status_code == 404

    def test_missing_fields(self, client):
        resp = client.post("/compositions/demo/highlights", json={
            "recording": "a",
        })
        assert resp.status_code == 400

    @patch("thea.composer.CompositionManager.add_highlight")
    def test_success(self, mock_add, client):
        resp = client.post("/compositions/demo/highlights", json={
            "recording": "a", "time": 3.5, "duration": 2.0,
        })
        assert resp.status_code == 201
        mock_add.assert_called_once()

    def test_list_not_found(self, client):
        resp = client.get("/compositions/nope/highlights")
        assert resp.status_code == 404

    @patch("thea.composer.CompositionManager.get")
    def test_list_success(self, mock_get, client):
        from thea.composer import CompositionResult, CompositionSpec, Highlight
        spec = CompositionSpec(
            name="demo", recordings=["a"],
            highlights=[Highlight("a", 1.0, 2.0)],
        )
        result = CompositionResult(name="demo", status="complete")
        mock_get.return_value = (spec, result)

        resp = client.get("/compositions/demo/highlights")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) == 1
        assert data[0]["recording"] == "a"
        assert data[0]["time"] == 1.0

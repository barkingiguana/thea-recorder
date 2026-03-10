"""Unit tests for the video composition module."""

import json
import os
from unittest.mock import MagicMock, patch

import pytest

from thea.composer import (
    CompositionManager,
    CompositionResult,
    CompositionSpec,
    Highlight,
    _build_filter_complex,
    compute_layout,
    probe_duration,
    probe_resolution,
    render_composition,
    resolve_recording_path,
)


# ── Layout computation ───────────────────────────────────────────────────


class TestComputeLayout:
    def test_single_tile_row(self):
        positions, canvas = compute_layout(1, "row", 640, 360)
        assert positions == [(0, 0)]
        assert canvas == (640, 360)

    def test_two_tiles_row(self):
        positions, canvas = compute_layout(2, "row", 640, 360)
        assert positions == [(0, 0), (640, 0)]
        assert canvas == (1280, 360)

    def test_three_tiles_row(self):
        positions, canvas = compute_layout(3, "row", 640, 360)
        assert positions == [(0, 0), (640, 0), (1280, 0)]
        assert canvas == (1920, 360)

    def test_two_tiles_column(self):
        positions, canvas = compute_layout(2, "column", 640, 360)
        assert positions == [(0, 0), (0, 360)]
        assert canvas == (640, 720)

    def test_four_tiles_grid(self):
        positions, canvas = compute_layout(4, "grid", 640, 360)
        assert positions == [(0, 0), (640, 0), (0, 360), (640, 360)]
        assert canvas == (1280, 720)

    def test_three_tiles_grid(self):
        # ceil(sqrt(3)) = 2 cols, ceil(3/2) = 2 rows
        positions, canvas = compute_layout(3, "grid", 640, 360)
        assert positions == [(0, 0), (640, 0), (0, 360)]
        assert canvas == (1280, 720)

    def test_six_tiles_grid(self):
        # ceil(sqrt(6)) = 3 cols, ceil(6/3) = 2 rows
        positions, canvas = compute_layout(6, "grid", 640, 360)
        assert len(positions) == 6
        assert canvas == (1920, 720)
        # First row
        assert positions[0] == (0, 0)
        assert positions[1] == (640, 0)
        assert positions[2] == (1280, 0)
        # Second row
        assert positions[3] == (0, 360)
        assert positions[4] == (640, 360)
        assert positions[5] == (1280, 360)

    def test_zero_tiles_raises(self):
        with pytest.raises(ValueError, match="at least 1"):
            compute_layout(0, "row", 640, 360)

    def test_unknown_layout_raises(self):
        with pytest.raises(ValueError, match="unknown layout"):
            compute_layout(2, "diagonal", 640, 360)


# ── Probe helpers ────────────────────────────────────────────────────────


class TestProbeDuration:
    @patch("thea.composer.subprocess.run")
    def test_returns_duration(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({"format": {"duration": "12.5"}}),
        )
        assert probe_duration("/tmp/test.mp4") == 12.5

    @patch("thea.composer.subprocess.run")
    def test_failure_raises(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stderr="bad file")
        with pytest.raises(RuntimeError, match="ffprobe failed"):
            probe_duration("/tmp/bad.mp4")


class TestProbeResolution:
    @patch("thea.composer.subprocess.run")
    def test_returns_width_height(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({"streams": [{"width": 1920, "height": 1080}]}),
        )
        assert probe_resolution("/tmp/test.mp4") == (1920, 1080)


# ── Filter construction ──────────────────────────────────────────────────


class TestBuildFilter:
    def _spec(self, **kwargs):
        defaults = {
            "name": "test_comp",
            "recordings": ["a", "b"],
            "layout": "row",
            "labels": False,
            "highlights": [],
        }
        defaults.update(kwargs)
        return CompositionSpec(**defaults)

    def test_basic_two_tile_row(self):
        spec = self._spec()
        filt = _build_filter_complex(
            spec, ["a.mp4", "b.mp4"], 640, 360, "", "", 10.0,
        )
        # Should contain scale, tpad, xstack
        assert "scale=640:360" in filt
        assert "xstack=inputs=2" in filt
        assert "0_0|640_0" in filt
        assert "[out]" in filt

    def test_with_highlights(self):
        spec = self._spec(highlights=[
            Highlight(recording="a", time=2.0, duration=1.5),
        ])
        filt = _build_filter_complex(
            spec, ["a.mp4", "b.mp4"], 640, 360, "", "", 10.0,
        )
        assert "drawbox" in filt
        assert "between(t" in filt
        assert "2.000" in filt
        assert "3.500" in filt  # 2.0 + 1.5

    def test_with_labels(self):
        spec = self._spec(labels=True)
        filt = _build_filter_complex(
            spec, ["a.mp4", "b.mp4"], 640, 360,
            "/usr/share/fonts/test.ttf", "/usr/share/fonts/test-bold.ttf",
            10.0,
        )
        assert "drawtext=text='a'" in filt
        assert "drawtext=text='b'" in filt

    def test_labels_skipped_without_font(self):
        spec = self._spec(labels=True)
        filt = _build_filter_complex(
            spec, ["a.mp4", "b.mp4"], 640, 360, "", "", 10.0,
        )
        assert "drawtext" not in filt

    def test_highlight_on_unknown_recording_ignored(self):
        spec = self._spec(highlights=[
            Highlight(recording="nonexistent", time=1.0, duration=1.0),
        ])
        filt = _build_filter_complex(
            spec, ["a.mp4", "b.mp4"], 640, 360, "", "", 10.0,
        )
        # No drawbox since the recording name doesn't match
        assert "drawbox" not in filt

    def test_column_layout(self):
        spec = self._spec(layout="column")
        filt = _build_filter_complex(
            spec, ["a.mp4", "b.mp4"], 640, 360, "", "", 10.0,
        )
        assert "0_0|0_360" in filt

    def test_grid_layout(self):
        spec = self._spec(recordings=["a", "b", "c", "d"], layout="grid")
        filt = _build_filter_complex(
            spec, ["a.mp4", "b.mp4", "c.mp4", "d.mp4"], 640, 360, "", "", 10.0,
        )
        assert "xstack=inputs=4" in filt
        assert "0_0|640_0|0_360|640_360" in filt


# ── Recording path resolution ────────────────────────────────────────────


class TestResolveRecordingPath:
    def test_existing_file(self, tmp_path):
        mp4 = tmp_path / "test_recording.mp4"
        mp4.write_bytes(b"fake mp4")
        assert resolve_recording_path(str(tmp_path), "test_recording") == str(mp4)

    def test_missing_file(self, tmp_path):
        assert resolve_recording_path(str(tmp_path), "nope") is None


# ── Full render (mocked ffmpeg) ──────────────────────────────────────────


class TestRenderComposition:
    @patch("thea.composer._find_system_fonts", return_value=("font.ttf", "bold.ttf"))
    @patch("thea.composer.probe_duration", return_value=10.0)
    @patch("thea.composer.subprocess.run")
    def test_happy_path(self, mock_run, _dur, _fonts, tmp_path):
        # Create fake source recordings
        for name in ["a", "b"]:
            (tmp_path / f"{name}.mp4").write_bytes(b"fake")

        # ffmpeg "succeeds"
        mock_run.return_value = MagicMock(returncode=0)

        spec = CompositionSpec(
            name="composed",
            recordings=["a", "b"],
            layout="row",
        )
        # Create the output file so we can verify the path
        result = render_composition(spec, str(tmp_path))
        assert result.endswith("composed.mp4")
        assert mock_run.called
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "ffmpeg"
        assert "-filter_complex" in cmd

    @patch("thea.composer._find_system_fonts", return_value=("", ""))
    @patch("thea.composer.probe_duration", return_value=5.0)
    @patch("thea.composer.subprocess.run")
    def test_ffmpeg_failure(self, mock_run, _dur, _fonts, tmp_path):
        for name in ["a", "b"]:
            (tmp_path / f"{name}.mp4").write_bytes(b"fake")

        mock_run.return_value = MagicMock(returncode=1, stderr="encode error")

        spec = CompositionSpec(name="fail", recordings=["a", "b"])
        with pytest.raises(RuntimeError, match="ffmpeg composition failed"):
            render_composition(spec, str(tmp_path))

    def test_missing_recording(self, tmp_path):
        spec = CompositionSpec(name="missing", recordings=["nope"])
        with pytest.raises(FileNotFoundError, match="not found"):
            render_composition(spec, str(tmp_path))


# ── Data types ───────────────────────────────────────────────────────────


class TestDataTypes:
    def test_composition_spec_to_dict(self):
        spec = CompositionSpec(
            name="demo",
            recordings=["a", "b"],
            highlights=[Highlight("a", 1.0, 2.0)],
        )
        d = spec.to_dict()
        assert d["name"] == "demo"
        assert d["recordings"] == ["a", "b"]
        assert len(d["highlights"]) == 1
        assert d["highlights"][0]["recording"] == "a"
        assert d["highlights"][0]["time"] == 1.0
        assert d["highlights"][0]["duration"] == 2.0

    def test_composition_result_to_dict(self):
        r = CompositionResult(name="demo", status="complete", output_path="/tmp/demo.mp4")
        d = r.to_dict()
        assert d["name"] == "demo"
        assert d["status"] == "complete"
        assert d["output_path"] == "/tmp/demo.mp4"

    def test_composition_result_error(self):
        r = CompositionResult(name="demo", status="failed", error="oops")
        d = r.to_dict()
        assert d["error"] == "oops"
        assert "output_path" not in d

    def test_highlight_defaults(self):
        h = Highlight(recording="a", time=5.0)
        assert h.duration == 1.0


# ── CompositionManager ──────────────────────────────────────────────────


class TestCompositionManager:
    def test_list_empty(self):
        mgr = CompositionManager("/tmp")
        assert mgr.list_all() == []

    def test_get_nonexistent(self):
        mgr = CompositionManager("/tmp")
        assert mgr.get("nope") is None

    def test_delete_nonexistent(self):
        mgr = CompositionManager("/tmp")
        assert mgr.delete("nope") is False

    @patch("thea.composer.render_composition")
    def test_create_and_get(self, mock_render, tmp_path):
        mock_render.return_value = str(tmp_path / "out.mp4")

        mgr = CompositionManager(str(tmp_path))
        spec = CompositionSpec(name="test", recordings=["a"])
        result = mgr.create(spec)
        assert result.name == "test"

        # Wait for background thread
        import time
        time.sleep(0.5)

        got = mgr.get("test")
        assert got is not None
        _, result = got
        assert result.status in ("rendering", "complete")

    @patch("thea.composer.render_composition")
    def test_create_duplicate_raises(self, mock_render):
        mock_render.return_value = "/tmp/out.mp4"
        mgr = CompositionManager("/tmp")
        mgr.create(CompositionSpec(name="dup", recordings=["a"]))
        with pytest.raises(ValueError, match="already exists"):
            mgr.create(CompositionSpec(name="dup", recordings=["b"]))

    @patch("thea.composer.render_composition")
    def test_delete(self, mock_render):
        mock_render.return_value = "/tmp/out.mp4"
        mgr = CompositionManager("/tmp")
        mgr.create(CompositionSpec(name="del", recordings=["a"]))
        assert mgr.delete("del") is True
        assert mgr.get("del") is None

    @patch("thea.composer.render_composition")
    def test_list_all(self, mock_render):
        mock_render.return_value = "/tmp/out.mp4"
        mgr = CompositionManager("/tmp")
        mgr.create(CompositionSpec(name="one", recordings=["a"]))
        mgr.create(CompositionSpec(name="two", recordings=["b"]))
        items = mgr.list_all()
        names = {item["name"] for item in items}
        assert "one" in names
        assert "two" in names

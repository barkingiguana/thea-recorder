"""Tests for step tracker context manager."""
import pytest
from unittest.mock import MagicMock, patch

from thea.recorder import Recorder


@pytest.fixture
def rec(tmp_path):
    r = Recorder(output_dir=str(tmp_path), display=99)
    return r


class TestStepTracker:
    def test_step_passed(self, rec):
        rec._recording_start = 100.0
        with patch("thea.recorder.time") as mock_time:
            mock_time.monotonic.return_value = 105.0
            with rec.step("Do something"):
                pass
        assert len(rec._steps) == 1
        assert rec._steps[0]["name"] == "Do something"
        assert rec._steps[0]["status"] == "passed"
        assert rec._steps[0]["keyword"] == "Step"
        assert rec._steps[0]["offset"] == 5.0

    def test_step_failed(self, rec):
        rec._recording_start = 100.0
        with patch("thea.recorder.time") as mock_time:
            mock_time.monotonic.return_value = 105.0
            with pytest.raises(ValueError):
                with rec.step("Fail step"):
                    raise ValueError("boom")
        assert rec._steps[0]["status"] == "failed"

    def test_step_custom_keyword(self, rec):
        rec._recording_start = 100.0
        with patch("thea.recorder.time") as mock_time:
            mock_time.monotonic.return_value = 100.0
            with rec.step("Given something", keyword="Given"):
                pass
        assert rec._steps[0]["keyword"] == "Given"

    def test_multiple_steps(self, rec):
        rec._recording_start = 100.0
        times = iter([101.0, 102.0, 103.0])
        with patch("thea.recorder.time") as mock_time:
            mock_time.monotonic.side_effect = lambda: next(times)
            with rec.step("Step 1"):
                pass
            with rec.step("Step 2"):
                pass
            with rec.step("Step 3"):
                pass
        assert len(rec._steps) == 3
        assert [s["offset"] for s in rec._steps] == [1.0, 2.0, 3.0]

    def test_steps_reset_on_start_recording(self, rec):
        rec._recording_start = 100.0
        with patch("thea.recorder.time") as mock_time:
            mock_time.monotonic.return_value = 101.0
            with rec.step("Old step"):
                pass
        assert len(rec._steps) == 1
        with patch("thea.recorder.subprocess.Popen") as mock_popen:
            mock_popen.return_value = MagicMock()
            with patch("thea.recorder.os.makedirs"):
                rec.start_recording("test")
        assert len(rec._steps) == 0

    def test_last_recording_steps_preserved(self, rec):
        rec._ffmpeg_proc = MagicMock()
        rec._recording_start = 100.0
        with patch("thea.recorder.time") as mock_time:
            mock_time.monotonic.return_value = 101.0
            with rec.step("A step"):
                pass
        # Simulate stop_recording
        rec._ffmpeg_proc.stdin = MagicMock()
        rec._ffmpeg_proc.stderr = MagicMock()
        rec._ffmpeg_proc.stderr.read.return_value = b""
        rec._ffmpeg_proc.returncode = 0
        rec._output_path = "/tmp/test.mp4"
        rec.stop_recording()
        assert len(rec.last_recording_steps) == 1
        assert rec.last_recording_steps[0]["name"] == "A step"

    def test_last_recording_status_passed(self, rec):
        rec._last_recording_steps = [
            {"keyword": "Step", "name": "a", "status": "passed", "offset": 0},
            {"keyword": "Step", "name": "b", "status": "passed", "offset": 1},
        ]
        assert rec.last_recording_status == "passed"

    def test_last_recording_status_failed(self, rec):
        rec._last_recording_steps = [
            {"keyword": "Step", "name": "a", "status": "passed", "offset": 0},
            {"keyword": "Step", "name": "b", "status": "failed", "offset": 1},
        ]
        assert rec.last_recording_status == "failed"

    def test_last_recording_status_no_steps(self, rec):
        assert rec.last_recording_status == "passed"

    def test_step_not_recording(self, rec):
        """Steps work even without an active recording (offset will be 0.0)."""
        with rec.step("No recording"):
            pass
        assert rec._steps[0]["offset"] == 0.0
        assert rec._steps[0]["status"] == "passed"

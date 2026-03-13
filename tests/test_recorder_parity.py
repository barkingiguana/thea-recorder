"""Tests for library-mode parity: keyboard, mouse, and annotations on Recorder."""
import pytest
from unittest.mock import MagicMock, patch, PropertyMock

from thea.recorder import Recorder


@pytest.fixture
def rec(tmp_path):
    r = Recorder(output_dir=str(tmp_path), display=99)
    return r


class TestKeyboardConvenience:
    def test_keyboard_type_delegates(self, rec):
        mock_director = MagicMock()
        rec._director = mock_director
        rec.keyboard_type("hello", wpm=200)
        mock_director.keyboard.type.assert_called_once_with("hello", wpm=200)

    def test_keyboard_press_delegates(self, rec):
        mock_director = MagicMock()
        rec._director = mock_director
        rec.keyboard_press("Return")
        mock_director.keyboard.press.assert_called_once_with("Return")

    def test_keyboard_press_multiple_keys(self, rec):
        mock_director = MagicMock()
        rec._director = mock_director
        rec.keyboard_press("ctrl+l")
        mock_director.keyboard.press.assert_called_once_with("ctrl+l")


class TestMouseConvenience:
    def test_mouse_move_delegates(self, rec):
        mock_director = MagicMock()
        rec._director = mock_director
        rec.mouse_move(100, 200, duration=0.5)
        mock_director.mouse.move.assert_called_once_with(100, 200, duration=0.5)

    def test_mouse_click_delegates(self, rec):
        mock_director = MagicMock()
        rec._director = mock_director
        rec.mouse_click(100, 200, button=1)
        mock_director.mouse.click.assert_called_once_with(100, 200, button=1)


class TestAnnotations:
    def test_add_annotation_requires_recording(self, rec):
        with pytest.raises(RuntimeError, match="Not recording"):
            rec.add_annotation("test")

    def test_add_annotation_auto_time(self, rec):
        rec._ffmpeg_proc = MagicMock()
        rec._recording_start = 100.0
        with patch("thea.recorder.time") as mock_time:
            mock_time.monotonic.return_value = 105.5
            ann = rec.add_annotation("step1")
        assert ann["label"] == "step1"
        assert ann["time"] == 5.5
        assert "details" not in ann

    def test_add_annotation_explicit_time(self, rec):
        rec._ffmpeg_proc = MagicMock()
        rec._recording_start = 100.0
        ann = rec.add_annotation("step1", time=3.0)
        assert ann["time"] == 3.0

    def test_add_annotation_with_details(self, rec):
        rec._ffmpeg_proc = MagicMock()
        rec._recording_start = 100.0
        ann = rec.add_annotation("step1", time=1.0, details="did a thing")
        assert ann["details"] == "did a thing"

    def test_list_annotations(self, rec):
        rec._ffmpeg_proc = MagicMock()
        rec._recording_start = 100.0
        rec.add_annotation("a", time=1.0)
        rec.add_annotation("b", time=2.0)
        anns = rec.list_annotations()
        assert len(anns) == 2
        assert anns[0]["label"] == "a"
        assert anns[1]["label"] == "b"

    def test_annotations_reset_on_start_recording(self, rec, tmp_path):
        rec._ffmpeg_proc = MagicMock()
        rec._recording_start = 100.0
        rec.add_annotation("old", time=1.0)
        assert len(rec._annotations) == 1
        # Simulate start_recording resetting annotations
        with patch("thea.recorder.subprocess.Popen") as mock_popen:
            mock_popen.return_value = MagicMock()
            with patch("thea.recorder.os.makedirs"):
                rec.start_recording("test")
        assert len(rec._annotations) == 0

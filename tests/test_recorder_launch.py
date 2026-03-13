"""Tests for launch_app fill_viewport feature."""
import pytest
from unittest.mock import MagicMock, patch

from thea.recorder import Recorder


@pytest.fixture
def rec(tmp_path):
    r = Recorder(output_dir=str(tmp_path), display=99, display_size="1280x720")
    return r


class TestLaunchAppFillViewport:
    def test_basic_launch_unchanged(self, rec):
        """launch_app without new params works as before."""
        with patch("thea.recorder.subprocess.Popen") as mock_popen:
            mock_popen.return_value = MagicMock(pid=123)
            proc = rec.launch_app(["xterm"])
            mock_popen.assert_called_once()
            assert proc.pid == 123

    def test_fill_viewport_finds_and_resizes(self, rec):
        """fill_viewport=True uses Director to find and resize window."""
        mock_win = MagicMock()
        mock_win.focus.return_value = mock_win
        mock_win.move.return_value = mock_win
        mock_win.resize.return_value = mock_win

        mock_director = MagicMock()
        mock_director.window_by_class.return_value = mock_win
        rec._director = mock_director

        with patch("thea.recorder.subprocess.Popen") as mock_popen:
            mock_popen.return_value = MagicMock(pid=123)
            with patch("thea.recorder.time.sleep"):
                rec.launch_app(["xterm"], window_class="XTerm", fill_viewport=True)

        mock_director.window_by_class.assert_called_once_with("XTerm")
        mock_win.focus.assert_called_once()
        mock_win.move.assert_called_once_with(0, 0)
        mock_win.resize.assert_called_once_with(1280, 720)

    def test_window_class_without_fill_viewport_no_resize(self, rec):
        """window_class alone doesn't trigger resize."""
        with patch("thea.recorder.subprocess.Popen") as mock_popen:
            mock_popen.return_value = MagicMock(pid=123)
            rec.launch_app(["xterm"], window_class="XTerm")
        # Director should not be accessed at all
        assert rec._director is None

    def test_fill_viewport_without_window_class_no_resize(self, rec):
        """fill_viewport without window_class is a no-op."""
        with patch("thea.recorder.subprocess.Popen") as mock_popen:
            mock_popen.return_value = MagicMock(pid=123)
            rec.launch_app(["xterm"], fill_viewport=True)
        assert rec._director is None

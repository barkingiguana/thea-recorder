"""Tests for the Director facade (mocked subprocess/xdotool)."""

from unittest.mock import patch, MagicMock, call
import subprocess

import pytest

from thea_director.director import Director
from thea_director.keyboard import Keyboard
from thea_director.mouse import Mouse
from thea_director.motion import MotionConfig
from thea_director.rhythm import RhythmConfig


class TestDirectorInit:
    @patch("thea_director.director.subprocess.run")
    @patch("thea_director.director.subprocess.Popen")
    @patch("thea_director.director.time.sleep")
    def test_display_string(self, mock_sleep, mock_popen, mock_run):
        # Simulate no WM running.
        mock_run.return_value = MagicMock(stdout="no such atom", returncode=1)
        d = Director(":99")
        assert d.env["DISPLAY"] == ":99"

    @patch("thea_director.director.subprocess.run")
    def test_display_dict(self, mock_run):
        mock_run.return_value = MagicMock(stdout="window id # 0x1", returncode=0)
        env = {"DISPLAY": ":42", "FOO": "bar"}
        d = Director(env, ensure_wm=True)
        assert d.env["DISPLAY"] == ":42"
        assert d.env["FOO"] == "bar"

    @patch("thea_director.director.subprocess.run")
    def test_skip_wm(self, mock_run):
        d = Director(":99", ensure_wm=False)
        mock_run.assert_not_called()

    @patch("thea_director.director.subprocess.run")
    def test_wm_already_running(self, mock_run):
        mock_run.return_value = MagicMock(stdout="window id # 0x12345", returncode=0)
        d = Director(":99")
        # Should not start openbox since WM is detected.
        assert d._wm_proc is None

    @patch("thea_director.director.time.sleep")
    @patch("thea_director.director.subprocess.Popen")
    @patch("thea_director.director.subprocess.run")
    def test_starts_openbox_when_no_wm(self, mock_run, mock_popen, mock_sleep):
        mock_run.return_value = MagicMock(stdout="no such atom", returncode=1)
        mock_popen.return_value = MagicMock()
        d = Director(":99")
        mock_popen.assert_called_once()
        args = mock_popen.call_args[0][0]
        assert args[0] == "openbox"

    @patch("thea_director.director.subprocess.run")
    def test_custom_motion_config(self, mock_run):
        mock_run.return_value = MagicMock(stdout="window id # 0x1", returncode=0)
        config = MotionConfig(min_duration=0.5)
        d = Director(":99", motion=config)
        assert d.mouse.motion.min_duration == 0.5

    @patch("thea_director.director.subprocess.run")
    def test_custom_rhythm_config(self, mock_run):
        mock_run.return_value = MagicMock(stdout="window id # 0x1", returncode=0)
        config = RhythmConfig(wpm=120)
        d = Director(":99", rhythm=config)
        assert d.keyboard.rhythm.wpm == 120


class TestDirectorProperties:
    @patch("thea_director.director.subprocess.run")
    def test_keyboard(self, mock_run):
        mock_run.return_value = MagicMock(stdout="window id # 0x1")
        d = Director(":99")
        assert isinstance(d.keyboard, Keyboard)

    @patch("thea_director.director.subprocess.run")
    def test_mouse(self, mock_run):
        mock_run.return_value = MagicMock(stdout="window id # 0x1")
        d = Director(":99")
        assert isinstance(d.mouse, Mouse)


class TestDirectorWindow:
    @patch("thea_director.director.find_window")
    @patch("thea_director.director.subprocess.run")
    def test_window_delegates(self, mock_run, mock_find):
        mock_run.return_value = MagicMock(stdout="window id # 0x1")
        d = Director(":99")
        d.window("Firefox", timeout=5.0)
        mock_find.assert_called_once_with("Firefox", d.env, timeout=5.0)

    @patch("thea_director.director.find_window_by_class")
    @patch("thea_director.director.subprocess.run")
    def test_window_by_class_delegates(self, mock_run, mock_find):
        mock_run.return_value = MagicMock(stdout="window id # 0x1")
        d = Director(":99")
        d.window_by_class("chromium", timeout=3.0)
        mock_find.assert_called_once_with("chromium", d.env, timeout=3.0)


class TestDirectorTile:
    @patch("thea_director.director.tile")
    @patch("thea_director.director.subprocess.run")
    def test_tile_delegates(self, mock_run, mock_tile):
        mock_run.return_value = MagicMock(stdout="window id # 0x1")
        d = Director(":99")
        windows = [MagicMock(), MagicMock()]
        d.tile(windows, "grid", bounds=(0, 0, 1920, 1080))
        mock_tile.assert_called_once_with(windows, "grid", bounds=(0, 0, 1920, 1080))


class TestDirectorScreenshot:
    @patch("thea_director.director.xdotool.screenshot")
    @patch("thea_director.director.subprocess.run")
    def test_screenshot(self, mock_run, mock_ss):
        mock_run.return_value = MagicMock(stdout="window id # 0x1")
        d = Director(":99")
        d.screenshot("/tmp/shot.png")
        mock_ss.assert_called_once_with("/tmp/shot.png", d.env, region=None)

    @patch("thea_director.director.xdotool.screenshot")
    @patch("thea_director.director.subprocess.run")
    def test_screenshot_with_region(self, mock_run, mock_ss):
        mock_run.return_value = MagicMock(stdout="window id # 0x1")
        d = Director(":99")
        d.screenshot("/tmp/shot.png", region=(10, 20, 100, 200))
        mock_ss.assert_called_once_with("/tmp/shot.png", d.env, region=(10, 20, 100, 200))


class TestDirectorCleanup:
    @patch("thea_director.director.time.sleep")
    @patch("thea_director.director.subprocess.Popen")
    @patch("thea_director.director.subprocess.run")
    def test_cleanup_terminates_wm(self, mock_run, mock_popen, mock_sleep):
        mock_run.return_value = MagicMock(stdout="no such atom", returncode=1)
        proc = MagicMock()
        proc.poll.return_value = None  # Still running.
        mock_popen.return_value = proc
        d = Director(":99")
        d.cleanup()
        proc.terminate.assert_called_once()

    @patch("thea_director.director.subprocess.run")
    def test_cleanup_no_wm(self, mock_run):
        mock_run.return_value = MagicMock(stdout="window id # 0x1")
        d = Director(":99")
        d.cleanup()  # Should not raise.

    @patch("thea_director.director.time.sleep")
    @patch("thea_director.director.subprocess.Popen")
    @patch("thea_director.director.subprocess.run")
    def test_cleanup_force_kill_on_timeout(self, mock_run, mock_popen, mock_sleep):
        mock_run.return_value = MagicMock(stdout="no such atom", returncode=1)
        proc = MagicMock()
        proc.poll.return_value = None
        proc.wait.side_effect = subprocess.TimeoutExpired(cmd="openbox", timeout=5)
        mock_popen.return_value = proc
        d = Director(":99")
        d.cleanup()
        proc.kill.assert_called_once()

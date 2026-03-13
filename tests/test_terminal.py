"""Tests for thea.terminal module."""
import os
import pytest
from unittest.mock import MagicMock, patch, call

from thea.terminal.terminal import Terminal, _strip_ansi


class TestStripAnsi:
    def test_strips_color_codes(self):
        assert _strip_ansi("\x1b[31mred\x1b[0m") == "red"

    def test_strips_osc_sequences(self):
        assert _strip_ansi("\x1b]0;title\x07text") == "text"

    def test_strips_carriage_returns(self):
        assert _strip_ansi("hello\rworld") == "helloworld"

    def test_preserves_plain_text(self):
        assert _strip_ansi("hello world") == "hello world"

    def test_strips_cursor_sequences(self):
        assert _strip_ansi("\x1b[?25hvisible") == "visible"


class TestTerminalInit:
    def test_launches_xterm_with_defaults(self):
        rec = MagicMock()
        rec.launch_app.return_value = MagicMock(pid=123)
        rec.director = MagicMock()

        with patch("thea.terminal.terminal.time"):
            term = Terminal(rec, capture_output=False)

        rec.launch_app.assert_called_once()
        args, kwargs = rec.launch_app.call_args
        cmd = args[0]
        assert cmd[0] == "xterm"
        assert "-fa" in cmd
        assert "DejaVu Sans Mono" in cmd
        assert kwargs["window_class"] == "XTerm"
        assert kwargs["fill_viewport"] is True

    def test_custom_font_and_colors(self):
        rec = MagicMock()
        rec.launch_app.return_value = MagicMock(pid=123)
        rec.director = MagicMock()

        with patch("thea.terminal.terminal.time"):
            term = Terminal(
                rec,
                font="JetBrains Mono",
                font_size=18,
                bg="#1a1a2e",
                fg="#00ff00",
                capture_output=False,
            )

        cmd = rec.launch_app.call_args[0][0]
        assert "JetBrains Mono" in cmd
        assert "18" in cmd
        assert "#1a1a2e" in cmd
        assert "#00ff00" in cmd

    def test_scrollbar_enabled(self):
        rec = MagicMock()
        rec.launch_app.return_value = MagicMock(pid=123)
        rec.director = MagicMock()

        with patch("thea.terminal.terminal.time"):
            term = Terminal(rec, scrollbar=True, capture_output=False)

        cmd = rec.launch_app.call_args[0][0]
        assert "+sb" not in cmd

    def test_capture_output_sets_up_tee(self):
        rec = MagicMock()
        rec.launch_app.return_value = MagicMock(pid=123)
        rec.director = MagicMock()

        with patch("thea.terminal.terminal.time"):
            with patch("thea.terminal.terminal.tempfile") as mock_tmp:
                mock_tmp.mktemp.side_effect = ["/tmp/stdout.log", "/tmp/stderr.log"]
                with patch("builtins.open", MagicMock()):
                    with patch("thea.terminal.terminal.os.path.exists", return_value=True):
                        with patch("thea.terminal.terminal.os.path.getsize", return_value=0):
                            term = Terminal(rec, capture_output=True)

        # Should have typed the tee setup command
        rec.director.keyboard.type.assert_called()
        rec.director.keyboard.press.assert_called()


class TestRunCommand:
    def test_types_command_and_presses_enter(self):
        rec = MagicMock()
        rec.launch_app.return_value = MagicMock(pid=123)
        rec.director = MagicMock()

        with patch("thea.terminal.terminal.time"):
            with patch("thea.terminal.terminal.os.path.exists", return_value=False):
                term = Terminal(rec, capture_output=False)

        with patch("thea.terminal.terminal.time") as mock_time:
            term.run_command("echo hello")

        rec.keyboard_type.assert_called_with("echo hello")
        rec.keyboard_press.assert_called_with("Return")
        mock_time.sleep.assert_called_with(1.5)

    def test_custom_pause_after(self):
        rec = MagicMock()
        rec.launch_app.return_value = MagicMock(pid=123)
        rec.director = MagicMock()

        with patch("thea.terminal.terminal.time"):
            with patch("thea.terminal.terminal.os.path.exists", return_value=False):
                term = Terminal(rec, capture_output=False)

        with patch("thea.terminal.terminal.time") as mock_time:
            term.run_command("slow command", pause_after=5.0)

        mock_time.sleep.assert_called_with(5.0)

    def test_custom_wpm(self):
        rec = MagicMock()
        rec.launch_app.return_value = MagicMock(pid=123)
        rec.director = MagicMock()

        with patch("thea.terminal.terminal.time"):
            with patch("thea.terminal.terminal.os.path.exists", return_value=False):
                term = Terminal(rec, capture_output=False, wpm=200)

        with patch("thea.terminal.terminal.time"):
            term.run_command("fast typing")

        rec.keyboard_type.assert_called_with("fast typing", wpm=200)


class TestClear:
    def test_sends_ctrl_l(self):
        rec = MagicMock()
        rec.launch_app.return_value = MagicMock(pid=123)
        rec.director = MagicMock()

        with patch("thea.terminal.terminal.time"):
            with patch("thea.terminal.terminal.os.path.exists", return_value=False):
                term = Terminal(rec, capture_output=False)

        with patch("thea.terminal.terminal.time"):
            term.clear()

        rec.keyboard_press.assert_called_with("ctrl+l")


class TestClose:
    def test_types_exit(self):
        rec = MagicMock()
        rec.launch_app.return_value = MagicMock(pid=123)
        rec.director = MagicMock()

        with patch("thea.terminal.terminal.time"):
            with patch("thea.terminal.terminal.os.path.exists", return_value=False):
                term = Terminal(rec, capture_output=False)

        with patch("thea.terminal.terminal.time"):
            term.close()

        rec.keyboard_type.assert_called_with("exit")


class TestLatestOutput:
    def test_returns_empty_when_capture_disabled(self):
        rec = MagicMock()
        rec.launch_app.return_value = MagicMock(pid=123)
        rec.director = MagicMock()

        with patch("thea.terminal.terminal.time"):
            with patch("thea.terminal.terminal.os.path.exists", return_value=False):
                term = Terminal(rec, capture_output=False)

        assert term.latest_output() == ""

    def test_reads_from_offset(self, tmp_path):
        rec = MagicMock()
        rec.launch_app.return_value = MagicMock(pid=123)
        rec.director = MagicMock()

        stdout_log = str(tmp_path / "stdout.log")
        stderr_log = str(tmp_path / "stderr.log")

        with patch("thea.terminal.terminal.time"):
            with patch("thea.terminal.terminal.os.path.exists", return_value=False):
                term = Terminal(rec, capture_output=False)

        # Manually set up capture state
        term._capture_output = True
        term._stdout_log = stdout_log
        term._stderr_log = stderr_log

        # Write some content
        with open(stdout_log, "w") as f:
            f.write("old output\nnew output\n")
        with open(stderr_log, "w") as f:
            f.write("")

        # Set offset past "old output\n"
        term._stdout_offset = len("old output\n")
        term._stderr_offset = 0

        result = term.latest_output()
        assert result == "new output\n"

    def test_strips_ansi_from_output(self, tmp_path):
        rec = MagicMock()
        rec.launch_app.return_value = MagicMock(pid=123)
        rec.director = MagicMock()

        stdout_log = str(tmp_path / "stdout.log")
        stderr_log = str(tmp_path / "stderr.log")

        with patch("thea.terminal.terminal.time"):
            with patch("thea.terminal.terminal.os.path.exists", return_value=False):
                term = Terminal(rec, capture_output=False)

        term._capture_output = True
        term._stdout_log = stdout_log
        term._stderr_log = stderr_log
        term._stdout_offset = 0
        term._stderr_offset = 0

        with open(stdout_log, "w") as f:
            f.write("\x1b[32mgreen text\x1b[0m\n")
        with open(stderr_log, "w") as f:
            f.write("")

        result = term.latest_output()
        assert result == "green text\n"


class TestLatestStdoutStderr:
    def test_latest_stdout(self, tmp_path):
        rec = MagicMock()
        rec.launch_app.return_value = MagicMock(pid=123)
        rec.director = MagicMock()

        with patch("thea.terminal.terminal.time"):
            with patch("thea.terminal.terminal.os.path.exists", return_value=False):
                term = Terminal(rec, capture_output=False)

        stdout_log = str(tmp_path / "stdout.log")
        stderr_log = str(tmp_path / "stderr.log")
        term._capture_output = True
        term._stdout_log = stdout_log
        term._stderr_log = stderr_log
        term._stdout_offset = 0
        term._stderr_offset = 0

        with open(stdout_log, "w") as f:
            f.write("stdout content\n")
        with open(stderr_log, "w") as f:
            f.write("stderr content\n")

        assert term.latest_stdout() == "stdout content\n"
        assert term.latest_stderr() == "stderr content\n"
        assert "stdout content" in term.latest_output()
        assert "stderr content" in term.latest_output()

    def test_returns_empty_when_capture_disabled(self):
        rec = MagicMock()
        rec.launch_app.return_value = MagicMock(pid=123)
        rec.director = MagicMock()

        with patch("thea.terminal.terminal.time"):
            with patch("thea.terminal.terminal.os.path.exists", return_value=False):
                term = Terminal(rec, capture_output=False)

        assert term.latest_stdout() == ""
        assert term.latest_stderr() == ""


class TestCleanup:
    def test_removes_log_files(self, tmp_path):
        rec = MagicMock()
        rec.launch_app.return_value = MagicMock(pid=123)
        rec.director = MagicMock()

        stdout_log = str(tmp_path / "stdout.log")
        stderr_log = str(tmp_path / "stderr.log")
        for path in (stdout_log, stderr_log):
            with open(path, "w") as f:
                f.write("test")

        with patch("thea.terminal.terminal.time"):
            with patch("thea.terminal.terminal.os.path.exists", return_value=False):
                term = Terminal(rec, capture_output=False)

        term._stdout_log = stdout_log
        term._stderr_log = stderr_log
        term.cleanup()

        assert not os.path.exists(stdout_log)
        assert not os.path.exists(stderr_log)

    def test_cleanup_missing_files_no_error(self):
        rec = MagicMock()
        rec.launch_app.return_value = MagicMock(pid=123)
        rec.director = MagicMock()

        with patch("thea.terminal.terminal.time"):
            with patch("thea.terminal.terminal.os.path.exists", return_value=False):
                term = Terminal(rec, capture_output=False)

        term._stdout_log = "/tmp/nonexistent-stdout.log"
        term._stderr_log = "/tmp/nonexistent-stderr.log"
        term.cleanup()  # Should not raise

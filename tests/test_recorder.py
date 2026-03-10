import os
from unittest.mock import Mock, patch

import pytest

from thea.recorder import Recorder, PANEL_HEIGHT, LINE_HEIGHT, _find_system_fonts, _FONT_SEARCH


class TestDisplayString:
    def test_default_display(self):
        r = Recorder()
        assert r.display_string == ":99"

    def test_custom_display(self):
        r = Recorder(display=105)
        assert r.display_string == ":105"

    def test_display_zero(self):
        r = Recorder(display=0)
        assert r.display_string == ":0"


class TestFonts:
    def test_custom_font_paths(self):
        r = Recorder(font="/custom/regular.ttf", font_bold="/custom/bold.ttf")
        assert r._font == "/custom/regular.ttf"
        assert r._font_bold == "/custom/bold.ttf"

    @patch("thea.recorder.os.path.exists", return_value=False)
    def test_no_system_fonts_returns_empty(self, _exists):
        regular, bold = _find_system_fonts()
        assert regular == ""
        assert bold == ""

    def test_find_system_fonts_returns_first_match(self, tmp_path):
        font = tmp_path / "Regular.ttf"
        bold = tmp_path / "Bold.ttf"
        font.write_text("")
        bold.write_text("")
        search = [(str(font), str(bold))]
        with patch("thea.recorder._FONT_SEARCH", search):
            r, b = _find_system_fonts()
            assert r == str(font)
            assert b == str(bold)

    def test_defaults_use_system_search(self):
        r = Recorder()
        assert isinstance(r._font, str)
        assert isinstance(r._font_bold, str)

    def test_partial_override_font(self):
        r = Recorder(font="/my/font.ttf")
        assert r._font == "/my/font.ttf"
        assert isinstance(r._font_bold, str)

    def test_partial_override_font_bold(self):
        r = Recorder(font_bold="/my/bold.ttf")
        assert r._font_bold == "/my/bold.ttf"
        assert isinstance(r._font, str)

    def test_find_system_fonts_skips_missing(self, tmp_path):
        missing = ("/no/such/font.ttf", "/no/such/bold.ttf")
        found = tmp_path / "Found.ttf"
        found_bold = tmp_path / "FoundBold.ttf"
        found.write_text("")
        found_bold.write_text("")
        search = [missing, (str(found), str(found_bold))]
        with patch("thea.recorder._FONT_SEARCH", search):
            r, b = _find_system_fonts()
            assert r == str(found)
            assert b == str(found_bold)


class TestStartDisplay:
    @patch("thea.recorder.subprocess.run")
    @patch("thea.recorder.os.path.exists", return_value=True)
    @patch("thea.recorder.subprocess.Popen")
    def test_with_panels_adds_panel_height(self, mock_popen, _exists, _run):
        r = Recorder(display=42, display_size="1920x1080")
        r.add_panel("header", title="Header")
        r.start_display()

        args = mock_popen.call_args[0][0]
        assert args[0] == "Xvfb"
        assert args[1] == ":42"
        expected_h = 1080 + PANEL_HEIGHT
        assert f"1920x{expected_h}x24" in args
        r.cleanup()

    @patch("thea.recorder.subprocess.run")
    @patch("thea.recorder.os.path.exists", return_value=True)
    @patch("thea.recorder.subprocess.Popen")
    def test_without_panels_still_allocates_panel_height(self, mock_popen, _exists, _run):
        r = Recorder(display=42, display_size="1920x1080")
        r.start_display()

        args = mock_popen.call_args[0][0]
        expected_h = 1080 + PANEL_HEIGHT
        assert f"1920x{expected_h}x24" in args

    @patch("thea.recorder.subprocess.run")
    @patch("thea.recorder.os.path.exists", return_value=True)
    @patch("thea.recorder.subprocess.Popen")
    def test_sets_cursor(self, _popen, _exists, mock_run):
        r = Recorder(display=42)
        r.start_display()

        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert "xsetroot" in args
        assert "-cursor_name" in args

    @patch("thea.recorder.subprocess.run")
    @patch("thea.recorder.os.path.exists", return_value=True)
    @patch("thea.recorder.subprocess.Popen")
    def test_stop_display_terminates_xvfb(self, mock_popen, _exists, _run):
        proc = Mock()
        mock_popen.return_value = proc
        r = Recorder()
        r.start_display()
        r.stop_display()

        proc.terminate.assert_called_once()
        proc.wait.assert_called_once()

    def test_stop_display_noop_when_not_started(self):
        r = Recorder()
        r.stop_display()  # Should not raise

    @patch("thea.recorder.subprocess.run")
    @patch("thea.recorder.os.path.exists", return_value=True)
    @patch("thea.recorder.subprocess.Popen")
    def test_custom_resolution(self, mock_popen, _exists, _run):
        r = Recorder(display=1, display_size="1280x720")
        r.start_display()

        args = mock_popen.call_args[0][0]
        expected_h = 720 + PANEL_HEIGHT
        assert f"1280x{expected_h}x24" in args

    @patch("thea.recorder.subprocess.run")
    @patch("thea.recorder.os.path.exists", return_value=True)
    @patch("thea.recorder.subprocess.Popen")
    def test_display_env_passed_to_xsetroot(self, _popen, _exists, mock_run):
        r = Recorder(display=77)
        r.start_display()

        call_kwargs = mock_run.call_args[1]
        assert call_kwargs["env"]["DISPLAY"] == ":77"


class TestPanels:
    def test_add_panel_creates_temp_file(self):
        r = Recorder()
        r.add_panel("metrics", title="Metrics")

        assert "metrics" in r._panels
        assert os.path.exists(r._panels["metrics"]["path"])
        assert r._panels["metrics"]["title"] == "Metrics"
        r.cleanup()

    def test_add_panel_default_empty_title(self):
        r = Recorder()
        r.add_panel("debug")

        assert r._panels["debug"]["title"] == ""
        r.cleanup()

    def test_add_panel_with_fixed_width(self):
        r = Recorder()
        r.add_panel("nav", title="Nav", width=160)

        assert r._panels["nav"]["width"] == 160
        r.cleanup()

    def test_add_panel_default_width_is_none(self):
        r = Recorder()
        r.add_panel("output")

        assert r._panels["output"]["width"] is None
        r.cleanup()

    def test_re_add_panel_replaces_old(self):
        r = Recorder()
        r.add_panel("progress")
        old_path = r._panels["progress"]["path"]
        r.add_panel("progress", title="New", width=200)

        assert not os.path.exists(old_path)
        assert r._panels["progress"]["title"] == "New"
        assert r._panels["progress"]["width"] == 200
        r.cleanup()

    def test_remove_panel_deletes_file(self):
        r = Recorder()
        r.add_panel("alerts")
        path = r._panels["alerts"]["path"]
        assert os.path.exists(path)

        r.remove_panel("alerts")

        assert "alerts" not in r._panels
        assert not os.path.exists(path)

    def test_remove_nonexistent_panel_is_noop(self):
        r = Recorder()
        r.remove_panel("missing")  # Should not raise

    def test_update_panel_writes_content(self):
        r = Recorder()
        r.add_panel("trace", title="Trace")
        r.update_panel("trace", "hello world")

        with open(r._panels["trace"]["path"]) as f:
            assert f.read() == "hello world"
        r.cleanup()

    def test_update_panel_atomic_write(self):
        r = Recorder()
        r.add_panel("log")
        r.update_panel("log", "first")
        r.update_panel("log", "second")

        with open(r._panels["log"]["path"]) as f:
            assert f.read() == "second"
        assert not os.path.exists(r._panels["log"]["path"] + ".tmp")
        r.cleanup()

    def test_update_nonexistent_panel_is_noop(self):
        r = Recorder()
        r.update_panel("missing", "text")  # Should not raise

    def test_multiple_panels_ordered(self):
        r = Recorder()
        r.add_panel("first")
        r.add_panel("second")
        r.add_panel("third")

        assert list(r._panels.keys()) == ["first", "second", "third"]
        r.cleanup()

    def test_panel_file_starts_empty(self):
        r = Recorder()
        r.add_panel("empty_panel")

        with open(r._panels["empty_panel"]["path"]) as f:
            assert f.read() == ""
        r.cleanup()

    def test_update_panel_multiline(self):
        r = Recorder()
        r.add_panel("multi")
        r.update_panel("multi", "line 1\nline 2\nline 3")

        with open(r._panels["multi"]["path"]) as f:
            content = f.read()
        assert content == "line 1\nline 2\nline 3"
        r.cleanup()

    def test_update_panel_unicode(self):
        r = Recorder()
        r.add_panel("uni")
        r.update_panel("uni", "Status: passed")

        with open(r._panels["uni"]["path"]) as f:
            assert f.read() == "Status: passed"
        r.cleanup()


class TestPanelLayout:
    def test_all_auto_width(self):
        r = Recorder(display_size="1920x1080")
        r.add_panel("alpha")
        r.add_panel("bravo")
        r.add_panel("charlie")
        layout = r._panel_layout(1920)

        assert len(layout) == 3
        assert layout[0] == ("alpha", r._panels["alpha"], 0, 640)
        assert layout[1] == ("bravo", r._panels["bravo"], 640, 640)
        assert layout[2] == ("charlie", r._panels["charlie"], 1280, 640)
        r.cleanup()

    def test_mixed_fixed_and_auto(self):
        r = Recorder(display_size="1920x1080")
        r.add_panel("sidebar", width=160)
        r.add_panel("main")
        layout = r._panel_layout(1920)

        assert len(layout) == 2
        assert layout[0] == ("sidebar", r._panels["sidebar"], 0, 160)
        assert layout[1] == ("main", r._panels["main"], 160, 1760)
        r.cleanup()

    def test_multiple_fixed_one_auto(self):
        r = Recorder(display_size="1920x1080")
        r.add_panel("left", width=160)
        r.add_panel("centre")
        r.add_panel("right", width=240)
        layout = r._panel_layout(1920)

        assert layout[0][2:] == (0, 160)       # left at x=0, w=160
        assert layout[1][2:] == (160, 1520)     # centre at x=160, w=1520
        assert layout[2][2:] == (1680, 240)     # right at x=1680, w=240
        r.cleanup()

    def test_all_fixed_width(self):
        r = Recorder()
        r.add_panel("narrow", width=500)
        r.add_panel("wide", width=300)
        layout = r._panel_layout(1920)

        assert layout[0][2:] == (0, 500)
        assert layout[1][2:] == (500, 300)
        r.cleanup()

    def test_single_auto_panel(self):
        r = Recorder()
        r.add_panel("only")
        layout = r._panel_layout(1920)

        assert len(layout) == 1
        assert layout[0][2:] == (0, 1920)
        r.cleanup()

    def test_single_fixed_panel(self):
        r = Recorder()
        r.add_panel("fixed", width=400)
        layout = r._panel_layout(1920)

        assert len(layout) == 1
        assert layout[0][2:] == (0, 400)
        r.cleanup()


class TestRecording:
    @patch("thea.recorder.subprocess.Popen")
    def test_start_recording_creates_output_dir(self, mock_popen, tmp_path):
        out = tmp_path / "videos"
        r = Recorder(output_dir=str(out))
        r.start_recording("test_scenario")

        assert out.exists()

    @patch("thea.recorder.subprocess.Popen")
    def test_with_panels_includes_vf_filter(self, mock_popen, tmp_path):
        r = Recorder(output_dir=str(tmp_path))
        r.add_panel("overlay", title="Overlay")
        r.start_recording("test")

        args = mock_popen.call_args[0][0]
        assert "-vf" in args
        vf_idx = args.index("-vf")
        vf = args[vf_idx + 1]
        assert "drawbox" in vf
        assert "drawtext" in vf
        r.cleanup()

    @patch("thea.recorder.subprocess.Popen")
    def test_without_panels_no_vf_filter(self, mock_popen, tmp_path):
        r = Recorder(output_dir=str(tmp_path))
        r.start_recording("test")

        args = mock_popen.call_args[0][0]
        assert "-vf" not in args

    @patch("thea.recorder.subprocess.Popen")
    def test_with_panels_video_size_includes_panel_height(self, mock_popen, tmp_path):
        r = Recorder(output_dir=str(tmp_path), display_size="1920x1080")
        r.add_panel("banner")
        r.start_recording("test")

        args = mock_popen.call_args[0][0]
        vs_idx = args.index("-video_size")
        assert args[vs_idx + 1] == f"1920x{1080 + PANEL_HEIGHT}"
        r.cleanup()

    @patch("thea.recorder.subprocess.Popen")
    def test_without_panels_video_size_display_only(self, mock_popen, tmp_path):
        r = Recorder(output_dir=str(tmp_path), display_size="1920x1080")
        r.start_recording("test")

        args = mock_popen.call_args[0][0]
        vs_idx = args.index("-video_size")
        assert args[vs_idx + 1] == "1920x1080"

    @patch("thea.recorder.subprocess.Popen")
    def test_start_recording_sanitises_filename(self, mock_popen, tmp_path):
        r = Recorder(output_dir=str(tmp_path))
        r.start_recording("Weird / Name & Stuff!")

        assert r._output_path.endswith(".mp4")
        assert "/" not in os.path.basename(r._output_path)
        assert "&" not in os.path.basename(r._output_path)

    @patch("thea.recorder.subprocess.Popen")
    def test_stop_recording_sends_q(self, mock_popen, tmp_path):
        proc = Mock()
        proc.returncode = 0
        proc.stderr = None
        mock_popen.return_value = proc
        r = Recorder(output_dir=str(tmp_path))
        r.start_recording("test")
        path = r.stop_recording()

        proc.stdin.write.assert_called_with(b"q")
        proc.stdin.flush.assert_called()
        assert path is not None
        assert path.endswith(".mp4")

    def test_stop_recording_noop_when_not_started(self):
        r = Recorder()
        assert r.stop_recording() is None

    @patch("thea.recorder.subprocess.Popen")
    def test_multiple_panels_filter_has_separators(self, mock_popen, tmp_path):
        r = Recorder(output_dir=str(tmp_path), display_size="1920x1080")
        r.add_panel("first", title="First")
        r.add_panel("second", title="Second")
        r.add_panel("third", title="Third")
        r.start_recording("test")

        args = mock_popen.call_args[0][0]
        vf_idx = args.index("-vf")
        vf = args[vf_idx + 1]
        assert "drawbox=x=640:y=1080:w=1" in vf
        assert "drawbox=x=1280:y=1080:w=1" in vf
        r.cleanup()

    @patch("thea.recorder.subprocess.Popen")
    def test_filter_uses_custom_font(self, mock_popen, tmp_path):
        r = Recorder(
            output_dir=str(tmp_path),
            font="/my/font.ttf",
            font_bold="/my/bold.ttf",
        )
        r.add_panel("ticker", title="Ticker")
        r.start_recording("test")

        args = mock_popen.call_args[0][0]
        vf_idx = args.index("-vf")
        vf = args[vf_idx + 1]
        assert "/my/font.ttf" in vf
        assert "/my/bold.ttf" in vf
        r.cleanup()

    @patch("thea.recorder.subprocess.Popen")
    def test_fixed_width_panel_in_filter(self, mock_popen, tmp_path):
        r = Recorder(output_dir=str(tmp_path), display_size="1920x1080")
        r.add_panel("sidebar", title="Sidebar", width=160)
        r.add_panel("detail", title="Detail")
        r.start_recording("test")

        args = mock_popen.call_args[0][0]
        vf_idx = args.index("-vf")
        vf = args[vf_idx + 1]
        assert "drawbox=x=160:y=1080:w=1" in vf
        r.cleanup()

    @patch("thea.recorder.subprocess.Popen")
    def test_filename_truncated_to_120_chars(self, mock_popen, tmp_path):
        r = Recorder(output_dir=str(tmp_path))
        long_name = "a" * 200
        r.start_recording(long_name)

        basename = os.path.basename(r._output_path).replace(".mp4", "")
        assert len(basename) <= 120

    @patch("thea.recorder.subprocess.Popen")
    def test_ffmpeg_uses_libx264(self, mock_popen, tmp_path):
        r = Recorder(output_dir=str(tmp_path))
        r.start_recording("test")

        args = mock_popen.call_args[0][0]
        assert "libx264" in args

    @patch("thea.recorder.subprocess.Popen")
    def test_ffmpeg_uses_configured_framerate(self, mock_popen, tmp_path):
        r = Recorder(output_dir=str(tmp_path), framerate=30)
        r.start_recording("test")

        args = mock_popen.call_args[0][0]
        fr_idx = args.index("-framerate")
        assert args[fr_idx + 1] == "30"

    @patch("thea.recorder.subprocess.Popen")
    def test_filter_includes_clock(self, mock_popen, tmp_path):
        r = Recorder(output_dir=str(tmp_path))
        r.add_panel("status")
        r.start_recording("test")

        args = mock_popen.call_args[0][0]
        vf_idx = args.index("-vf")
        vf = args[vf_idx + 1]
        assert "localtime" in vf
        r.cleanup()

    @patch("thea.recorder.subprocess.Popen")
    def test_filter_includes_rec_indicator(self, mock_popen, tmp_path):
        r = Recorder(output_dir=str(tmp_path))
        r.add_panel("status")
        r.start_recording("test")

        args = mock_popen.call_args[0][0]
        vf_idx = args.index("-vf")
        vf = args[vf_idx + 1]
        assert "REC" in vf
        r.cleanup()

    @patch("thea.recorder.subprocess.Popen")
    def test_panel_title_with_colon_escaped(self, mock_popen, tmp_path):
        r = Recorder(output_dir=str(tmp_path))
        r.add_panel("info", title="Status: OK")
        r.start_recording("test")

        args = mock_popen.call_args[0][0]
        vf_idx = args.index("-vf")
        vf = args[vf_idx + 1]
        assert "Status\\: OK" in vf
        r.cleanup()


class TestRecordingElapsed:
    @patch("thea.recorder.subprocess.Popen")
    def test_elapsed_increases_after_start(self, mock_popen, tmp_path):
        r = Recorder(output_dir=str(tmp_path))
        assert r.recording_elapsed == 0.0

        r.start_recording("test")
        assert r.recording_elapsed > 0.0

    @patch("thea.recorder.subprocess.Popen")
    def test_elapsed_resets_after_stop(self, mock_popen, tmp_path):
        r = Recorder(output_dir=str(tmp_path))
        r.start_recording("test")
        r.stop_recording()

        assert r.recording_elapsed == 0.0

    def test_elapsed_zero_when_never_started(self):
        r = Recorder()
        assert r.recording_elapsed == 0.0


class TestCleanup:
    @patch("thea.recorder.subprocess.run")
    @patch("thea.recorder.os.path.exists", return_value=True)
    @patch("thea.recorder.subprocess.Popen")
    def test_cleanup_stops_everything(self, mock_popen, _exists, _run, tmp_path):
        ffmpeg_proc = Mock()
        ffmpeg_proc.returncode = 0
        ffmpeg_proc.stderr = None
        xvfb_proc = Mock()
        mock_popen.side_effect = [xvfb_proc, ffmpeg_proc]

        r = Recorder(output_dir=str(tmp_path))
        r.add_panel("timer")
        r.start_display()
        r.start_recording("test")

        r.cleanup()

        ffmpeg_proc.stdin.write.assert_called_with(b"q")
        xvfb_proc.terminate.assert_called_once()

    def test_cleanup_removes_panel_files(self):
        r = Recorder()
        r.add_panel("upper")
        r.add_panel("lower")
        path_upper = r._panels["upper"]["path"]
        path_lower = r._panels["lower"]["path"]

        assert os.path.exists(path_upper)
        assert os.path.exists(path_lower)

        r.cleanup()

        assert not os.path.exists(path_upper)
        assert not os.path.exists(path_lower)
        assert not r._panels

    def test_cleanup_idempotent(self):
        r = Recorder()
        r.add_panel("test")
        r.cleanup()
        r.cleanup()  # Should not raise

    def test_cleanup_on_fresh_recorder(self):
        r = Recorder()
        r.cleanup()  # Should not raise


class TestPanelScrolling:
    """Tests for the scrolling/windowing behaviour of update_panel."""

    VISIBLE = (PANEL_HEIGHT - 28) // LINE_HEIGHT  # 15 with default constants

    def _read_panel(self, recorder, name):
        with open(recorder._panels[name]["path"]) as f:
            return f.read()

    def test_short_text_no_scrolling(self):
        r = Recorder()
        r.add_panel("info")
        text = "\n".join(f"line {i}" for i in range(self.VISIBLE))
        r.update_panel("info", text)

        assert self._read_panel(r, "info") == text
        r.cleanup()

    def test_long_text_default_focus_shows_end(self):
        r = Recorder()
        r.add_panel("log")
        lines = [f"line {i}" for i in range(30)]
        r.update_panel("log", "\n".join(lines))

        content = self._read_panel(r, "log")
        output_lines = content.split("\n")
        assert output_lines[-1] == "line 29"
        assert "more above" in output_lines[0]
        assert not any("more below" in l for l in output_lines)
        r.cleanup()

    def test_long_text_focus_middle(self):
        r = Recorder()
        r.add_panel("mid")
        lines = [f"line {i}" for i in range(30)]
        r.update_panel("mid", "\n".join(lines), focus_line=15)

        content = self._read_panel(r, "mid")
        output_lines = content.split("\n")
        assert "line 15" in content
        assert "more above" in output_lines[0]
        assert "more below" in output_lines[-1]
        r.cleanup()

    def test_long_text_focus_near_start(self):
        r = Recorder()
        r.add_panel("top")
        lines = [f"line {i}" for i in range(30)]
        r.update_panel("top", "\n".join(lines), focus_line=2)

        content = self._read_panel(r, "top")
        output_lines = content.split("\n")
        assert output_lines[0] == "line 0"
        assert not any("more above" in l for l in output_lines)
        assert "more below" in output_lines[-1]
        r.cleanup()

    def test_long_text_focus_near_end(self):
        r = Recorder()
        r.add_panel("bot")
        lines = [f"line {i}" for i in range(30)]
        r.update_panel("bot", "\n".join(lines), focus_line=28)

        content = self._read_panel(r, "bot")
        output_lines = content.split("\n")
        assert output_lines[-1] == "line 29"
        assert "more above" in output_lines[0]
        assert not any("more below" in l for l in output_lines)
        r.cleanup()

    def test_more_above_below_markers(self):
        r = Recorder()
        r.add_panel("marks")
        lines = [f"line {i}" for i in range(30)]
        r.update_panel("marks", "\n".join(lines), focus_line=15)

        content = self._read_panel(r, "marks")
        output_lines = content.split("\n")

        above_marker = output_lines[0]
        below_marker = output_lines[-1]
        above_count = int(above_marker.strip().split()[1])
        below_count = int(below_marker.strip().split()[1])
        assert above_count > 0
        assert below_count > 0
        assert f"... {above_count} more above" in above_marker
        assert f"... {below_count} more below" in below_marker
        visible_content = output_lines[1:-1]
        assert above_count + len(visible_content) + below_count == 30
        r.cleanup()

    def test_focus_line_zero(self):
        r = Recorder()
        r.add_panel("zero")
        lines = [f"line {i}" for i in range(30)]
        r.update_panel("zero", "\n".join(lines), focus_line=0)

        content = self._read_panel(r, "zero")
        output_lines = content.split("\n")
        assert output_lines[0] == "line 0"
        assert not any("more above" in l for l in output_lines)
        assert "more below" in output_lines[-1]
        r.cleanup()

    def test_exact_visible_lines_no_scrolling(self):
        r = Recorder()
        r.add_panel("exact")
        text = "\n".join(f"line {i}" for i in range(self.VISIBLE))
        r.update_panel("exact", text)

        content = self._read_panel(r, "exact")
        assert content == text
        assert "more" not in content
        r.cleanup()

    def test_one_over_visible_lines_triggers_scrolling(self):
        r = Recorder()
        r.add_panel("over")
        lines = [f"line {i}" for i in range(self.VISIBLE + 1)]
        r.update_panel("over", "\n".join(lines))

        content = self._read_panel(r, "over")
        assert "more above" in content
        r.cleanup()

    def test_single_line_no_scrolling(self):
        r = Recorder()
        r.add_panel("single")
        r.update_panel("single", "just one line")

        content = self._read_panel(r, "single")
        assert content == "just one line"
        r.cleanup()

    def test_empty_text_no_scrolling(self):
        r = Recorder()
        r.add_panel("empty")
        r.update_panel("empty", "")

        content = self._read_panel(r, "empty")
        assert content == ""
        r.cleanup()


class TestPanelHeight:
    def test_add_panel_with_height(self):
        r = Recorder()
        r.add_panel("short", height=100)
        assert r._panels["short"]["height"] == 100
        r.cleanup()

    def test_add_panel_default_height_is_none(self):
        r = Recorder()
        r.add_panel("default")
        assert r._panels["default"]["height"] is None
        r.cleanup()

    def test_panel_bar_height_no_panels(self):
        r = Recorder()
        assert r.panel_bar_height == 0

    def test_panel_bar_height_default_panels(self):
        r = Recorder()
        r.add_panel("a")
        r.add_panel("b")
        assert r.panel_bar_height == PANEL_HEIGHT
        r.cleanup()

    def test_panel_bar_height_explicit_heights(self):
        r = Recorder()
        r.add_panel("small", height=100)
        r.add_panel("big", height=500)
        assert r.panel_bar_height == 500
        r.cleanup()

    def test_panel_bar_height_mixed(self):
        r = Recorder()
        r.add_panel("default_h")  # None -> PANEL_HEIGHT
        r.add_panel("short", height=50)
        assert r.panel_bar_height == PANEL_HEIGHT
        r.cleanup()

    def test_panel_bar_height_tall_overrides_default(self):
        r = Recorder()
        r.add_panel("default_h")  # None -> PANEL_HEIGHT
        r.add_panel("tall", height=500)
        assert r.panel_bar_height == 500
        r.cleanup()

    def test_short_panel_fewer_visible_lines(self):
        r = Recorder()
        r.add_panel("short", height=60)
        # With height=60, visible_lines = (60-28)//18 = 1
        lines = [f"line {i}" for i in range(10)]
        r.update_panel("short", "\n".join(lines))
        with open(r._panels["short"]["path"]) as f:
            content = f.read()
        # Should have scrolling indicators
        assert "more above" in content
        r.cleanup()


class TestValidateLayout:
    def test_no_panels_valid(self):
        r = Recorder(display_size="1920x1080")
        assert r.validate_layout() == []

    def test_valid_layout_with_panels(self):
        r = Recorder(display_size="1920x1080")
        r.add_panel("status", width=120)
        r.add_panel("log")
        warnings = r.validate_layout()
        assert warnings == []
        r.cleanup()

    def test_overallocated_bar_warns(self):
        r = Recorder(display_size="1920x1080")
        r.add_panel("huge", height=500)
        warnings = r.validate_layout()
        assert any("allocated" in w for w in warnings)
        r.cleanup()

    def test_add_panel_returns_warnings(self):
        r = Recorder(display_size="1920x1080")
        warnings = r.add_panel("huge", height=500)
        assert isinstance(warnings, list)
        assert any("allocated" in w for w in warnings)
        r.cleanup()

    def test_fixed_width_panels_exceeding_canvas(self):
        r = Recorder(display_size="800x600")
        r.add_panel("a", width=500)
        r.add_panel("b", width=500)
        warnings = r.validate_layout()
        assert any("beyond canvas width" in w for w in warnings)
        r.cleanup()


class TestGenerateTestcard:
    def test_returns_svg(self):
        r = Recorder(display_size="1920x1080")
        svg = r.generate_testcard()
        assert svg.startswith("<svg")
        assert "</svg>" in svg

    def test_contains_viewport(self):
        r = Recorder(display_size="1920x1080")
        svg = r.generate_testcard()
        assert "viewport" in svg

    def test_contains_panel_names(self):
        r = Recorder(display_size="1920x1080")
        r.add_panel("status", title="Status", width=120)
        r.add_panel("log", title="Log")
        svg = r.generate_testcard()
        assert "status" in svg
        assert "log" in svg
        r.cleanup()

    def test_includes_warnings(self):
        r = Recorder(display_size="1920x1080")
        r.add_panel("huge", height=500)
        svg = r.generate_testcard()
        assert "Warnings" in svg
        r.cleanup()

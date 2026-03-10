"""Integration-style tests that verify the recorder and report work together.

These don't require Xvfb or ffmpeg — they test the data flow and API surface
that a BDD framework integration would use.
"""

import os
from unittest.mock import patch, Mock

from recorder import Recorder, generate_report


class TestRecordingLifecycle:
    """Simulates the full lifecycle: setup -> record scenarios -> report."""

    @patch("recorder.recorder.subprocess.Popen")
    def test_full_lifecycle(self, mock_popen, tmp_path):
        proc = Mock()
        proc.returncode = 0
        proc.stderr = None
        mock_popen.return_value = proc
        out = str(tmp_path / "recordings")

        # 1. Create recorder and add panels
        r = Recorder(output_dir=out, display=42)
        r.add_panel("status", title="Status", width=120)
        r.add_panel("scenario", title="Scenario")

        # 2. Record first scenario
        r.start_recording("login_success")
        r.update_panel("status", "Running")
        r.update_panel("scenario", "  Given a user\n* When I log in\n  Then I see home")

        elapsed = r.recording_elapsed
        assert elapsed > 0.0

        video1 = r.stop_recording()
        assert video1.endswith(".mp4")
        assert "login_success" in video1

        # 3. Record second scenario
        r.start_recording("login_failure")
        r.update_panel("status", "Running")
        r.update_panel("scenario", "  Given a user\n* When I enter wrong password\n  Then I see error")

        video2 = r.stop_recording()
        assert video2.endswith(".mp4")

        # 4. Generate report
        videos = [
            {
                "feature": "Authentication",
                "scenario": "Successful login",
                "status": "passed",
                "video": video1,
                "steps": [
                    {"keyword": "Given", "name": "a user", "status": "passed", "offset": 0.0},
                    {"keyword": "When", "name": "I log in", "status": "passed", "offset": 1.5},
                    {"keyword": "Then", "name": "I see home", "status": "passed", "offset": 3.0},
                ],
            },
            {
                "feature": "Authentication",
                "scenario": "Login failure",
                "status": "failed",
                "video": video2,
                "steps": [
                    {"keyword": "Given", "name": "a user", "status": "passed", "offset": 0.0},
                    {"keyword": "When", "name": "I enter wrong password", "status": "passed", "offset": 1.5},
                    {"keyword": "Then", "name": "I see error", "status": "failed", "offset": 3.0},
                ],
            },
        ]
        report_path = generate_report(videos, output_dir=out, title="My App")

        assert os.path.exists(report_path)
        with open(report_path) as f:
            html = f.read()
        assert "Authentication" in html
        assert "Successful login" in html
        assert "Login failure" in html
        assert "My App" in html

        # 5. Cleanup
        r.cleanup()
        assert not r._panels

    @patch("recorder.recorder.subprocess.Popen")
    def test_dynamic_panels(self, mock_popen, tmp_path):
        """Panels can be added/removed between scenarios."""
        proc = Mock()
        proc.returncode = 0
        proc.stderr = None
        mock_popen.return_value = proc
        r = Recorder(output_dir=str(tmp_path))
        r.add_panel("status", title="Status", width=120)
        r.add_panel("scenario", title="Scenario")

        # Scenario 1: no extra panels
        r.start_recording("scenario_1")
        assert len(r._panels) == 2
        r.stop_recording()

        # Scenario 2: add CLI panel
        r.add_panel("cli", title="CLI Output", width=400)
        r.start_recording("scenario_2")
        assert len(r._panels) == 3
        r.update_panel("cli", "$ my-tool --version\nv1.2.3")
        r.stop_recording()

        # Scenario 3: remove CLI panel
        r.remove_panel("cli")
        r.start_recording("scenario_3")
        assert len(r._panels) == 2
        r.stop_recording()

        r.cleanup()

    @patch("recorder.recorder.subprocess.Popen")
    def test_panel_scrolling_during_scenario(self, mock_popen, tmp_path):
        """Panel content scrolls as steps execute."""
        proc = Mock()
        proc.returncode = 0
        proc.stderr = None
        mock_popen.return_value = proc
        r = Recorder(output_dir=str(tmp_path))
        r.add_panel("steps", title="Steps")

        r.start_recording("long_scenario")

        # Simulate 20 steps executing one by one
        step_lines = []
        for i in range(20):
            step_lines.append(f"{'*' if True else ' '} Step {i}: do something")
            r.update_panel("steps", "\n".join(step_lines), focus_line=i)

        # Verify the panel has scrolled content
        with open(r._panels["steps"]["path"]) as f:
            content = f.read()
        assert "Step 19" in content
        assert "more above" in content

        r.stop_recording()
        r.cleanup()


class TestRecorderDefaults:
    def test_default_output_dir(self):
        r = Recorder()
        assert r._output_dir == "/tmp/recordings"

    def test_default_display(self):
        r = Recorder()
        assert r._display == 99

    def test_default_display_size(self):
        r = Recorder()
        assert r._display_size == "1920x1080"

    def test_default_framerate(self):
        r = Recorder()
        assert r._framerate == 15

    def test_all_custom(self):
        r = Recorder(
            output_dir="/my/videos",
            display=5,
            display_size="1280x720",
            framerate=30,
            font="/f.ttf",
            font_bold="/b.ttf",
        )
        assert r._output_dir == "/my/videos"
        assert r._display == 5
        assert r._display_size == "1280x720"
        assert r._framerate == 30
        assert r._font == "/f.ttf"
        assert r._font_bold == "/b.ttf"


class TestReportEdgeCases:
    def test_all_passed(self, tmp_path):
        videos = [
            {"feature": "F", "scenario": f"S{i}", "status": "passed", "video": f"/v{i}.mp4"}
            for i in range(5)
        ]
        path = generate_report(videos, output_dir=str(tmp_path))

        with open(path) as f:
            html = f.read()
        assert 'class="stat-value pass">5<' in html
        assert 'class="stat-value fail">0<' in html

    def test_all_failed(self, tmp_path):
        videos = [
            {"feature": "F", "scenario": f"S{i}", "status": "failed", "video": f"/v{i}.mp4"}
            for i in range(3)
        ]
        path = generate_report(videos, output_dir=str(tmp_path))

        with open(path) as f:
            html = f.read()
        assert 'class="stat-value pass">0<' in html
        assert 'class="stat-value fail">3<' in html

    def test_multiple_features(self, tmp_path):
        videos = [
            {"feature": f"Feature {i}", "scenario": "S", "status": "passed", "video": f"/v{i}.mp4"}
            for i in range(4)
        ]
        path = generate_report(videos, output_dir=str(tmp_path))

        with open(path) as f:
            html = f.read()
        for i in range(4):
            assert f"Feature {i}" in html

    def test_long_step_names(self, tmp_path):
        videos = [
            {
                "feature": "F",
                "scenario": "S",
                "status": "passed",
                "video": "/v.mp4",
                "steps": [
                    {
                        "keyword": "Given",
                        "name": "a very long step name " * 10,
                        "status": "passed",
                        "offset": 0.0,
                    },
                ],
            },
        ]
        path = generate_report(videos, output_dir=str(tmp_path))
        assert os.path.exists(path)

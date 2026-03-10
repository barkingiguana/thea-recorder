import os

from thea.report import generate_report, _escape, _step_table_html


class TestEscape:
    def test_ampersand(self):
        assert _escape("a & b") == "a &amp; b"

    def test_angle_brackets(self):
        assert _escape("<b>bold</b>") == "&lt;b&gt;bold&lt;/b&gt;"

    def test_quotes(self):
        assert _escape('"hello"') == "&quot;hello&quot;"

    def test_no_special_chars(self):
        assert _escape("plain text") == "plain text"

    def test_combined(self):
        assert _escape('<a href="x">&') == '&lt;a href=&quot;x&quot;&gt;&amp;'

    def test_empty_string(self):
        assert _escape("") == ""


class TestStepTableHtml:
    def test_empty_table(self):
        assert _step_table_html(None) == ""
        assert _step_table_html([]) == ""

    def test_single_row(self):
        table = [{"Name": "Alice", "Role": "Admin"}]
        html = _step_table_html(table)
        assert "<th>Name</th>" in html
        assert "<th>Role</th>" in html
        assert "<td>Alice</td>" in html
        assert "<td>Admin</td>" in html

    def test_multiple_rows(self):
        table = [
            {"Col": "A"},
            {"Col": "B"},
            {"Col": "C"},
        ]
        html = _step_table_html(table)
        assert html.count("<tr>") == 4  # 1 header + 3 data rows

    def test_escapes_content(self):
        table = [{"Value": "<script>alert(1)</script>"}]
        html = _step_table_html(table)
        assert "<script>" not in html
        assert "&lt;script&gt;" in html


class TestGenerateReport:
    def _make_videos(self):
        return [
            {
                "feature": "Login",
                "scenario": "Successful login",
                "status": "passed",
                "video": "/tmp/recordings/login_success.mp4",
                "steps": [
                    {"keyword": "Given", "name": "a registered user", "status": "passed", "offset": 0.0},
                    {"keyword": "When", "name": "I enter my credentials", "status": "passed", "offset": 2.5},
                    {"keyword": "Then", "name": "I see the dashboard", "status": "passed", "offset": 5.1},
                ],
            },
            {
                "feature": "Login",
                "scenario": "Invalid password",
                "status": "failed",
                "video": "/tmp/recordings/login_invalid.mp4",
                "steps": [
                    {"keyword": "Given", "name": "a registered user", "status": "passed", "offset": 0.0},
                    {"keyword": "When", "name": "I enter a wrong password", "status": "passed", "offset": 1.8},
                    {"keyword": "Then", "name": "I see an error", "status": "failed", "offset": 3.2},
                ],
            },
            {
                "feature": "Dashboard",
                "scenario": "View summary",
                "status": "passed",
                "video": "/tmp/recordings/dashboard_summary.mp4",
                "steps": [],
            },
        ]

    def test_creates_report_file(self, tmp_path):
        videos = self._make_videos()
        path = generate_report(videos, output_dir=str(tmp_path))

        assert os.path.exists(path)
        assert path.endswith("report.html")

    def test_report_contains_feature_names(self, tmp_path):
        videos = self._make_videos()
        path = generate_report(videos, output_dir=str(tmp_path))

        with open(path) as f:
            html = f.read()
        assert "Login" in html
        assert "Dashboard" in html

    def test_report_contains_scenario_names(self, tmp_path):
        videos = self._make_videos()
        path = generate_report(videos, output_dir=str(tmp_path))

        with open(path) as f:
            html = f.read()
        assert "Successful login" in html
        assert "Invalid password" in html
        assert "View summary" in html

    def test_report_contains_video_elements(self, tmp_path):
        videos = self._make_videos()
        path = generate_report(videos, output_dir=str(tmp_path))

        with open(path) as f:
            html = f.read()
        assert "<video" in html
        assert "login_success.mp4" in html
        assert "login_invalid.mp4" in html

    def test_report_contains_step_keywords(self, tmp_path):
        videos = self._make_videos()
        path = generate_report(videos, output_dir=str(tmp_path))

        with open(path) as f:
            html = f.read()
        assert "Given" in html
        assert "When" in html
        assert "Then" in html

    def test_report_contains_timestamps(self, tmp_path):
        videos = self._make_videos()
        path = generate_report(videos, output_dir=str(tmp_path))

        with open(path) as f:
            html = f.read()
        assert "0:00" in html
        assert "0:02" in html
        assert "0:05" in html

    def test_report_contains_seekto_js(self, tmp_path):
        videos = self._make_videos()
        path = generate_report(videos, output_dir=str(tmp_path))

        with open(path) as f:
            html = f.read()
        assert "seekTo" in html
        assert "timeupdate" in html

    def test_report_summary_counts(self, tmp_path):
        videos = self._make_videos()
        path = generate_report(videos, output_dir=str(tmp_path))

        with open(path) as f:
            html = f.read()
        # 3 total, 2 passed, 1 failed
        assert 'class="stat-value total">3<' in html
        assert 'class="stat-value pass">2<' in html
        assert 'class="stat-value fail">1<' in html

    def test_report_pass_fail_badges(self, tmp_path):
        videos = self._make_videos()
        path = generate_report(videos, output_dir=str(tmp_path))

        with open(path) as f:
            html = f.read()
        assert "PASSED" in html
        assert "FAILED" in html

    def test_report_creates_output_dir(self, tmp_path):
        out = tmp_path / "nested" / "dir"
        videos = [
            {"feature": "F", "scenario": "S", "status": "passed", "video": "/v.mp4"},
        ]
        path = generate_report(videos, output_dir=str(out))

        assert os.path.exists(path)

    def test_custom_title_and_subtitle(self, tmp_path):
        videos = [
            {"feature": "F", "scenario": "S", "status": "passed", "video": "/v.mp4"},
        ]
        path = generate_report(
            videos,
            output_dir=str(tmp_path),
            title="My App Tests",
            subtitle="Nightly run",
            logo_text="M",
        )

        with open(path) as f:
            html = f.read()
        assert "My App Tests" in html
        assert "Nightly run" in html

    def test_report_with_step_tables(self, tmp_path):
        videos = [
            {
                "feature": "Forms",
                "scenario": "Fill form",
                "status": "passed",
                "video": "/v.mp4",
                "steps": [
                    {
                        "keyword": "When",
                        "name": "I fill in the form",
                        "status": "passed",
                        "offset": 1.0,
                        "table": [
                            {"Field": "Name", "Value": "Alice"},
                            {"Field": "Email", "Value": "alice@example.com"},
                        ],
                    },
                ],
            },
        ]
        path = generate_report(videos, output_dir=str(tmp_path))

        with open(path) as f:
            html = f.read()
        assert "step-table" in html
        assert "Alice" in html
        assert "alice@example.com" in html

    def test_empty_videos_list(self, tmp_path):
        path = generate_report([], output_dir=str(tmp_path))

        assert os.path.exists(path)
        with open(path) as f:
            html = f.read()
        assert "0" in html

    def test_report_is_valid_html(self, tmp_path):
        videos = self._make_videos()
        path = generate_report(videos, output_dir=str(tmp_path))

        with open(path) as f:
            html = f.read()
        assert html.startswith("<!DOCTYPE html>")
        assert "</html>" in html

    def test_feature_grouping(self, tmp_path):
        videos = self._make_videos()
        path = generate_report(videos, output_dir=str(tmp_path))

        with open(path) as f:
            html = f.read()
        # Login feature should show 1 pass, 1 fail
        # Dashboard should show 1 pass, 0 fail
        assert html.count('class="feature"') == 2

    def test_scenario_with_no_steps(self, tmp_path):
        videos = [
            {"feature": "F", "scenario": "S", "status": "passed", "video": "/v.mp4"},
        ]
        path = generate_report(videos, output_dir=str(tmp_path))

        with open(path) as f:
            html = f.read()
        assert "S" in html

    def test_xss_prevention_in_names(self, tmp_path):
        videos = [
            {
                "feature": '<script>alert("xss")</script>',
                "scenario": '<img onerror="alert(1)">',
                "status": "passed",
                "video": "/v.mp4",
            },
        ]
        path = generate_report(videos, output_dir=str(tmp_path))

        with open(path) as f:
            html = f.read()
        assert "<script>alert" not in html
        assert 'onerror="alert' not in html

    def test_video_offsets_in_data_attribute(self, tmp_path):
        videos = [
            {
                "feature": "F",
                "scenario": "S",
                "status": "passed",
                "video": "/v.mp4",
                "steps": [
                    {"keyword": "Given", "name": "setup", "status": "passed", "offset": 0.0},
                    {"keyword": "Then", "name": "check", "status": "passed", "offset": 3.75},
                ],
            },
        ]
        path = generate_report(videos, output_dir=str(tmp_path))

        with open(path) as f:
            html = f.read()
        assert "data-offsets=" in html
        assert "0.00" in html
        assert "3.75" in html

    def test_responsive_css_included(self, tmp_path):
        videos = self._make_videos()
        path = generate_report(videos, output_dir=str(tmp_path))

        with open(path) as f:
            html = f.read()
        assert "@media" in html
        assert "max-width: 900px" in html

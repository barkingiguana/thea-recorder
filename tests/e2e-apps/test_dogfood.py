"""E2E test: dogfooding — Thea records its own test suite running in xterm.

This test uses Thea to record a terminal showing Thea's unit tests
being run. The recording includes panels showing test progress, and
generates an HTML report at the end.

This is the meta-test: Thea proving it can record anything by
recording itself.
"""

import os
import subprocess
import tempfile
import time

from thea import Recorder, generate_report

from conftest import OUTPUT_DIR


def test_dogfood_record_own_tests(output_dir):
    """Record Thea's unit tests running in xterm, then generate a report."""
    rec = Recorder(
        output_dir=output_dir,
        display=98,  # Different display to avoid conflict with fixture
        display_size="1280x720",
        framerate=15,
    )
    rec.start_display()
    rec.add_panel("status", title="Dogfood Test", width=250)
    rec.add_panel("progress", title="Test Progress")

    log_fd, log_path = tempfile.mkstemp(suffix=".log", prefix="thea_dogfood_")
    os.close(log_fd)

    try:
        # Launch xterm showing test output
        xterm = rec.launch_app(
            [
                "xterm",
                "-geometry", "120x40+0+0",
                "-fa", "DejaVu Sans Mono",
                "-fs", "14",
                "-b", "0",
                "-e", "tail", "-f", log_path,
            ],
        )
        time.sleep(1)

        rec.start_recording("dogfood-thea-tests")
        rec.update_panel("status", "Running Thea's\nown unit tests...")

        # Run Thea's unit tests, piping output to the log file
        with open(log_path, "w") as log:
            log.write("=" * 60 + "\n")
            log.write("  Thea recording its own test suite\n")
            log.write("=" * 60 + "\n\n")
            log.flush()
            time.sleep(1)

            result = subprocess.run(
                [
                    "python3", "-m", "pytest",
                    "tests/test_recorder.py",
                    "tests/test_layout.py",
                    "-v", "--tb=short", "--no-header",
                ],
                stdout=log,
                stderr=subprocess.STDOUT,
                cwd="/app",
                env={
                    **os.environ,
                    "COLUMNS": "120",
                    "LINES": "40",
                },
                timeout=120,
            )

        rec.update_panel("status", "Tests finished!")
        rec.update_panel(
            "progress",
            f"Exit code: {result.returncode}\n"
            f"{'PASSED' if result.returncode == 0 else 'FAILED'}"
        )
        time.sleep(2)

        video_path = rec.stop_recording()

    finally:
        rec.cleanup()
        try:
            os.unlink(log_path)
        except OSError:
            pass

    # Verify recording
    assert video_path is not None
    assert os.path.exists(video_path)
    assert os.path.getsize(video_path) > 0

    # Generate an HTML report including this recording
    videos = [
        {
            "feature": "Dogfooding",
            "scenario": "Record Thea's own test suite",
            "status": "passed" if result.returncode == 0 else "failed",
            "video": video_path,
            "steps": [
                {"keyword": "Given", "name": "a Thea recorder with xterm", "status": "passed", "offset": 0.0},
                {"keyword": "When", "name": "the unit tests are run", "status": "passed", "offset": 2.0},
                {"keyword": "Then", "name": "the recording captures the output", "status": "passed", "offset": 5.0},
            ],
        },
    ]
    report_path = generate_report(videos, output_dir=output_dir, title="Thea Dogfood Report")

    assert os.path.exists(report_path)
    print(f"Dogfood recording: {video_path} ({os.path.getsize(video_path)} bytes)")
    print(f"Dogfood report: {report_path}")

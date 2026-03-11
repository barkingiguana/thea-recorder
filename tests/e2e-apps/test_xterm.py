"""E2E test: record terminal output via xterm.

Demonstrates recording CLI output by launching xterm on Thea's Xvfb
display. The test pipes text to xterm via a temp file and tail -f,
which is the standard pattern for making stdout visible in a recording.

Everything runs in one container — Thea, Xvfb, xterm, and the process
producing output must all be co-located because Thea records a local
virtual display.
"""

import os
import subprocess
import tempfile
import time


def test_record_xterm_output(recorder, output_dir):
    """Record CLI output displayed in an xterm window."""
    recorder.add_panel("test", title="Terminal Test", width=300)
    recorder.add_panel("info", title="Info")

    recorder.update_panel("test", "Launching xterm...")

    # Create a temp file to pipe output through
    log_fd, log_path = tempfile.mkstemp(suffix=".log", prefix="thea_xterm_")
    os.close(log_fd)

    try:
        # Launch xterm on Thea's display, tailing the log file.
        # -geometry COLSxROWS+X+Y sizes and positions the window.
        # -fa/-fs set the font. -b 0 removes internal border.
        xterm_proc = recorder.launch_app(
            [
                "xterm",
                "-geometry", "120x40+0+0",
                "-fa", "DejaVu Sans Mono",
                "-fs", "14",
                "-b", "0",
                "-e", "tail", "-f", log_path,
            ],
        )
        time.sleep(1)  # Let xterm start and render

        recorder.start_recording("xterm-terminal")
        recorder.update_panel("test", "xterm running\nWriting output...")

        # Simulate a CLI tool producing output
        lines = [
            "$ thea --version",
            "thea-recorder 0.6.0",
            "",
            "$ echo 'Recording terminal output with Thea'",
            "Recording terminal output with Thea",
            "",
            "$ seq 1 10",
        ]
        for i in range(1, 11):
            lines.append(str(i))

        lines.extend([
            "",
            "$ echo 'All done!'",
            "All done!",
        ])

        # Write lines to the log file one at a time (xterm sees them via tail -f)
        with open(log_path, "a") as log:
            for i, line in enumerate(lines):
                log.write(line + "\n")
                log.flush()
                time.sleep(0.15)
                recorder.update_panel("info", f"Line {i + 1}/{len(lines)}\n{line}")

        recorder.update_panel("test", "Output complete\nWaiting for render...")
        time.sleep(1)

        video_path = recorder.stop_recording()

    finally:
        # xterm is tracked by launch_app(), so cleanup() will kill it,
        # but we can also stop it explicitly here
        if xterm_proc.poll() is None:
            xterm_proc.terminate()
        os.unlink(log_path)

    assert video_path is not None
    assert os.path.exists(video_path)
    assert os.path.getsize(video_path) > 0
    print(f"xterm recording saved: {video_path} ({os.path.getsize(video_path)} bytes)")

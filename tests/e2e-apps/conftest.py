"""Shared fixtures for E2E application recording tests.

All tests in this directory require Xvfb, ffmpeg, and the relevant
application to be installed. They are designed to run inside the
Docker container defined by the adjacent Dockerfile.
"""

import os
import subprocess
import time

import pytest

from thea import Recorder


OUTPUT_DIR = os.environ.get("TEST_OUTPUT_DIR", "/app/test-output")
FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


@pytest.fixture
def output_dir():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    return OUTPUT_DIR


@pytest.fixture
def recorder(output_dir):
    """A Recorder instance with display started, window manager running."""
    rec = Recorder(
        output_dir=output_dir,
        display=99,
        display_size="1280x720",
        framerate=15,
    )
    rec.start_display()

    # Start a lightweight window manager so that window focus,
    # activation, and resizing work properly with xdotool.
    rec.launch_app(
        ["openbox", "--config-file", "/dev/null"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(0.5)

    yield rec
    rec.cleanup()

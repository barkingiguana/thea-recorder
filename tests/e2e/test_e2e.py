"""E2E test for the Python SDK against a live recorder server."""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
from thea.client import RecorderClient


def main():
    url = os.environ.get("THEA_URL", "http://localhost:9123")
    client = RecorderClient(url)

    print("[python] Waiting for server...")
    client.wait_until_ready(timeout=30)

    print("[python] Starting display...")
    client.start_display()

    print("[python] Health check...")
    health = client.health()
    assert health["status"] == "ok", f"expected ok, got {health['status']}"
    print(f"[python] Health: status={health['status']} display={health.get('display')}")

    print("[python] Adding panel...")
    client.add_panel("editor", "Code Editor", 80)

    print("[python] Updating panel...")
    client.update_panel("editor", "print('hello from Python')", focus_line=1)

    print("[python] Listing panels...")
    panels = client.list_panels()
    assert len(panels) == 1, f"expected 1 panel, got {len(panels)}"
    assert panels[0]["name"] == "editor"

    print("[python] Starting recording...")
    client.start_recording("python-e2e-test")

    time.sleep(2)

    print("[python] Checking recording status...")
    status = client.recording_status()
    assert status["recording"] is True, f"expected recording=True"

    print("[python] Stopping recording...")
    result = client.stop_recording()
    assert result["path"], "expected non-empty path"
    print(f"[python] Recording saved: {result['path']} ({result['elapsed']:.1f}s)")

    print("[python] Removing panel...")
    client.remove_panel("editor")

    print("[python] Listing recordings...")
    recordings = client.list_recordings()
    assert len(recordings) >= 1, f"expected >= 1 recording"

    print("[python] Stopping display...")
    client.stop_display()

    print("[python] Cleanup...")
    client.cleanup()

    print("[python] ALL PASSED")


if __name__ == "__main__":
    main()

"""Simplest composition: two recordings side by side.

Record two things (sequentially), then compose them into a single
video with both playing at the same time.

Prerequisites:
  thea serve --port 9123 --output-dir ./recordings
"""

import time

from thea import RecorderClient

client = RecorderClient("http://localhost:9123")
client.start_display()
client.add_panel("status", title="Status", width=200)

# ── Record the first session ──────────────────────────────────────────────

with client.recording("left_side"):
    client.update_panel("status", "Recording: left side")
    time.sleep(3)
    # ... your first application runs here ...

# ── Record the second session ─────────────────────────────────────────────

with client.recording("right_side"):
    client.update_panel("status", "Recording: right side")
    time.sleep(3)
    # ... your second application runs here ...

# ── Compose them side by side ─────────────────────────────────────────────

client.create_composition("side_by_side", recordings=["left_side", "right_side"])
result = client.wait_for_composition("side_by_side")

print(f"Composed video: {result['output_path']}")

client.cleanup()

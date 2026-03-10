"""Composition using the context manager for automatic highlight timing.

Instead of calculating timestamps manually, use `composed_recording()`
which tracks elapsed time for you.  Just call `comp.highlight("name")`
whenever you want to draw attention to a session.

Prerequisites:
  thea serve --port 9123 --output-dir ./recordings
"""

import threading
import time

from thea import RecorderClient

THEA_URL = "http://localhost:9123"
client = RecorderClient(THEA_URL)


# ── Record two sessions in parallel ───────────────────────────────────────

def record_session(session_name: str, steps: list[str]):
    c = RecorderClient(THEA_URL)
    c.create_session(session_name)
    try:
        c.use_session(session_name)
        c.start_display()
        c.add_panel("status", title="Status")
        with c.recording(f"rec_{session_name}"):
            for step in steps:
                c.update_panel("status", step)
                time.sleep(2)
    finally:
        c.delete_session(session_name)


alice = threading.Thread(target=record_session, args=("alice", ["Login", "Browse", "Buy"]))
bob   = threading.Thread(target=record_session, args=("bob",   ["Login", "Search", "Save"]))
alice.start(); bob.start()
alice.join();  bob.join()


# ── Compose with automatic highlight tracking ─────────────────────────────

# The context manager calls create_composition + wait_for_composition
# automatically when the block exits.
with client.composed_recording("auto_demo", ["rec_alice", "rec_bob"]) as comp:
    # These timestamps are recorded automatically based on elapsed time
    comp.highlight("rec_alice", duration=2.0)
    time.sleep(3)

    comp.highlight("rec_bob", duration=2.0)
    time.sleep(3)

    comp.highlight("rec_alice", duration=1.5)
    time.sleep(2)

# comp.result is set after the context manager exits
print(f"Composed video: {comp.result['output_path']}")

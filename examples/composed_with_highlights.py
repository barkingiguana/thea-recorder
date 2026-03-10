"""Composition with highlight borders showing where the action is.

Records two parallel user sessions, then composes them into a single
video where a glowing border highlights whichever session is active.

Prerequisites:
  thea serve --port 9123 --output-dir ./recordings
"""

import threading
import time

from thea import RecorderClient

THEA_URL = "http://localhost:9123"


# ── Per-user session ──────────────────────────────────────────────────────

def user_session(session_name: str, steps: list[str]):
    """Run a series of steps in an isolated recording session."""
    client = RecorderClient(THEA_URL)
    client.create_session(session_name)

    try:
        client.use_session(session_name)
        client.start_display()
        client.add_panel("user",   title="User",   width=160)
        client.add_panel("status", title="Status")
        client.update_panel("user", session_name)

        with client.recording(f"rec_{session_name}"):
            for step in steps:
                client.update_panel("status", step)
                time.sleep(2)
    finally:
        client.delete_session(session_name)


# ── Record both users in parallel ─────────────────────────────────────────

alice = threading.Thread(
    target=user_session,
    args=("alice", ["Logging in", "Browsing products", "Adding to cart", "Checking out"]),
)
bob = threading.Thread(
    target=user_session,
    args=("bob", ["Logging in", "Searching", "Reading reviews", "Adding to wishlist"]),
)

alice.start()
bob.start()
alice.join()
bob.join()


# ── Compose with highlights ───────────────────────────────────────────────

client = RecorderClient(THEA_URL)

client.create_composition(
    "multi_user_highlights",
    recordings=["rec_alice", "rec_bob"],
    highlights=[
        # Alice logs in first (0–2s)
        {"recording": "rec_alice", "time": 0.0, "duration": 2.0},
        # Bob logs in next (2–4s)
        {"recording": "rec_bob",   "time": 2.0, "duration": 2.0},
        # Alice browses (4–6s)
        {"recording": "rec_alice", "time": 4.0, "duration": 2.0},
        # Bob searches (4–6s) — both highlighted at the same time!
        {"recording": "rec_bob",   "time": 4.0, "duration": 2.0},
        # Alice checks out (6–8s)
        {"recording": "rec_alice", "time": 6.0, "duration": 2.0},
    ],
)

result = client.wait_for_composition("multi_user_highlights")
print(f"Composed video: {result['output_path']}")
